'''
Generates PSD scatter plots from STS files (PDFanalysis.sts)
based on a YAML configuration.

Good for multiple stations and generates 3 visualizations (HHZ, HHN, HHE).
'''

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal, Protocol, Tuple

import sys

import matplotlib.pyplot as plt
import numpy as np
import yaml
from adjustText import adjust_text
import pandas as pd

StatName = Literal["min", "mean", "q_low", "q_high", "max", "mode"]



# ============ Exceptions ============

class STSReadError(Exception):
    ''' when a PDFanalysis.sts file cannot be parsed or does not exist '''

class STSStatError(Exception):
    ''' when a statistic is invalid '''

class ConfigError(Exception):
    ''' when the configuration from YAML is invalid '''



# ===================== PSD provider protocol =====================

class PSDProvider(Protocol):
    def psd_at(self, period: int, stat: StatName) -> Tuple[int, int]:
        ''' Return (period_used, psd_value) for the requested period and statistic.
        '''


@dataclass
class STSData:
    period: np.ndarray
    min: np.ndarray
    mean: np.ndarray
    q_low: np.ndarray
    q_high: np.ndarray
    max: np.ndarray
    mode: np.ndarray

# abstract base for STS-type PSD sources
class STSBase(ABC):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: STSData | None = None

    @abstractmethod
    def load(self) -> None:
        ''' load underlying data into memory'''

    @property
    def data(self) -> STSData:
        if self._data is None:
            raise STSReadError("No STS data loaded")
        return self._data

    def _select_array(self, stat: StatName) -> np.ndarray:
        try:
            return getattr(self.data, stat)
        except AttributeError as exc:
            raise STSStatError(f"Invalid statistic: {stat}, choose either min, mean, q_low, q_high, max, or mode.") from exc

    def psd_at(self, period: int, stat: StatName) -> Tuple[int, int]:
    # nearest neighbor in log10(period) space.
        arr_period = self.data.period
        if arr_period.size == 0:
            raise STSReadError("Empty period array in STS data")
        if np.any(arr_period <= 0.0):
            raise STSReadError("Negative period in STS data")

        log_p = np.log10(arr_period)
        log_target = np.log10(period)
        idx = int(np.argmin(np.abs(log_p - log_target)))

        period_used = int(arr_period[idx])
        psd_val = int(self._select_array(stat)[idx])
        return period_used, psd_val

# STS provider that reads PDFanalysis.sts from disk
class FileSTS(STSBase, PSDProvider):
    def load(self) -> None:
        if not self.path.exists():
            raise STSReadError(f"STS file not found: {self.path}")

        try:
            raw = np.loadtxt(self.path)
        except OSError as exc:
            raise STSReadError(f"Error reading STS file: {exc}") from exc
        except ValueError as exc:
            raise STSReadError(f"Malformed STS file: {exc}") from exc

        if raw.ndim != 2 or raw.shape[1] != 7:
            raise STSReadError(
                f"Expecting 7 columns in {self.path}, found shape {raw.shape!r}"
            )

        period = raw[:, 0]
        if not np.all(np.diff(period) > 0):
            raise STSReadError("Period column doesn't increase")

        self._data = STSData(
            period=period,
            min=raw[:, 1],
            mean=raw[:, 2],
            q_low=raw[:, 3],
            q_high=raw[:, 4],
            max=raw[:, 5],
            mode=raw[:, 6],
        )



# ===================== Station/channel model =====================

@dataclass(frozen=True)
class StationChannel:
    network: str
    station: str
    location: str
    component: str
    base_dir: Path

    @property
    def sts_path(self) -> Path:
    # build PDFanalysis.sts path: /ref/dc14/PDF/STATS/BK.BKS.00/HHZ/wrk/PDFanalysis.sts
        folder = f"{self.network}.{self.station}.{self.location}"
        return self.base_dir / folder / self.component / "wrk" / "PDFanalysis.sts"

    @property
    def label(self) -> str:
        return self.station


@dataclass(frozen=True)
class PSDPoint:
    component: str
    station: str
    psd_x: int
    psd_y: int


@dataclass(frozen=True)
class PlotConfig:
    base_dir: Path
    network: str
    stations: list[str]
    location: str
    components: list[str]
    period_x: int
    period_y: int
    stat: StatName
    out_dir: Path


def _parse_stations(raw_val: Any) -> list[str]:
    if isinstance(raw_val, list):
        return [str(s).strip() for s in raw_val if str(s).strip()]
    if isinstance(raw_val, str):
        return [s.strip() for s in raw_val.split(",") if s.strip()]
    raise ConfigError("stations must be a list or comma-separated string")


def load_config(path: Path) -> PlotConfig:
    if not path.exists():
        raise ConfigError(f"YAML file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
    except OSError as exc:
        raise ConfigError(f"Error reading YAML file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Error reading YAML file: {exc}") from exc

    required_keys = {"base_dir", "network", "stations", "location",
                "period_x", "period_y", "stat", "out_dir"}
    missing = required_keys - raw.keys()
    if missing:
        raise ConfigError(f"missing following config keys: {', '.join(sorted(missing))}")
    stat_val = raw["stat"]
    if stat_val not in {"min", "mean", "q_low", "q_high", "max", "mode"}:
        raise ConfigError(f"Invalid 'stat' value: {stat_val}")
    components_raw = raw.get("components", ["HHZ", "HHN", "HHE"])
    if isinstance(components_raw, list):
        components = [str(c).strip() for c in components_raw if str(c).strip()]
    else:
        raise ConfigError("components must be a list of strings")

    stations = _parse_stations(raw["stations"])

    return PlotConfig(
        base_dir=Path(str(raw["base_dir"])),
        network=str(raw["network"]),
        stations=stations,
        location=str(raw["location"]),
        components=components,
        period_x=int(raw["period_x"]),
        period_y=int(raw["period_y"]),
        stat=stat_val,  # type: ignore[arg-type]
        out_dir=Path(str(raw["out_dir"])),
    )



# ===================== Aggregation =====================

class PSDMatrixBuilder:
    # Build PSD points for all station+component channels

    def __init__(self, cfg: PlotConfig) -> None:
        self.cfg = cfg
        self.channels = self._build_channels()

    def _load_active_hhz_stations(self) -> list[tuple[str, str]]:
        '''Return (station, location) pairs for all active HHZ in BK.channel.summary.day.
        "active" channel: End time starts with "3000/01/01,00:00:00"
        Empty list is returned if summary file cannot be read
        '''
        summary_path = Path("/work/dc6/ftp/pub/doc/BK.info/BK.channel.summary.day")
        stations: set[tuple[str, str]] = set()

        try:
            with summary_path.open("r") as f:
                for line in f:
                    if not line.strip() or line.startswith("Stat ") or set(line.strip()) == {"-"}:
                        continue
                    parts = line.split()
                    if len(parts) < 7:
                        continue
                    stat, net, cha, loc = parts[0], parts[1], parts[2], parts[3]
                    end_time = parts[6]
                    
                    # only keep HHZ for the active channels
                    if net != self.cfg.network:
                        continue
                    if not cha.startswith("HHZ"):
                        continue
                    if not end_time.startswith("3000/01/01,00:00:00"):
                        continue
                    stations.add((stat, loc))
        except OSError as exc:
            print(
                f"COULDN'T READ: {summary_path}: {exc}",
                file=sys.stderr,
            )
            return []

        return sorted(stations)


    def _build_channels(self) -> list[StationChannel]:
        active_pairs = self._load_active_hhz_stations()
        active_station_names = {sta for sta, _ in active_pairs}

        selected_pairs: list[tuple[str, str]]

        if self.cfg.stations:
            # if a station list was provided in the config, intersect with active HHZ
            wanted = set(self.cfg.stations)
            selected_pairs = []
            for sta, loc in active_pairs:
                if sta in wanted:
                    selected_pairs.append((sta, loc))

            # Warn about any requested stations that are not active
            inactive_requested = wanted - {sta for sta, _ in selected_pairs}
            for sta in sorted(inactive_requested):
                print(
                    f"STATION {sta} REQUESTED BUT NOT ACTIVE IN HHZ "
                    f"entry in BK.channel.summary.day; skipping",
                    file=sys.stderr,
                )
        else:
            selected_pairs = list(active_pairs)

        if not selected_pairs:
            print(
                "NO STATISTATIONSNOS FOUND AFTER APPLYING FILTER; no psd",
                file=sys.stderr,
            )
        combos = product(selected_pairs, self.cfg.components)
        channels: list[StationChannel] = [
            StationChannel(
                network=self.cfg.network,
                station=sta,
                location=loc,
                component=comp,
                base_dir=self.cfg.base_dir,
            )
            for (sta, loc), comp in combos
        ]
        return channels

    def build_points(self) -> list[PSDPoint]:
        points: list[PSDPoint] = []

        for ch in self.channels:
            provider = FileSTS(ch.sts_path)
            try:
                provider.load()
                _, psd_x = provider.psd_at(self.cfg.period_x, self.cfg.stat)
                _, psd_y = provider.psd_at(self.cfg.period_y, self.cfg.stat)
            except (STSReadError, STSStatError) as exc:
                print(f"WARNING: SKIPPING: {ch.sts_path}: {exc}")
                continue

            points.append(
                PSDPoint(
                    component=ch.component,
                    station=ch.station,
                    psd_x=psd_x,
                    psd_y=psd_y,
                )
            )

        return points
    
    

# ===================== Outputs =====================

def excel(points: list[PSDPoint], cfg: PlotConfig) -> None:
    if not points:
        print("NO PSD POINTS (SKIPPING EXCEL)")
        return
    
    by_comp: dict[str, list[PSDPoint]] = {}
    for p in points:
        by_comp.setdefault(p.component, []).append(p)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    out_name = (
        f"{cfg.network}_PSD_"
        f"{int(cfg.period_x)}vs{int(cfg.period_y)}_"
        f"{cfg.stat}.xlsx"
    )
    out_path = cfg.out_dir / out_name

    with pd.ExcelWriter(out_path) as writer:
        for comp, comp_points in sorted(by_comp.items()):
            if not comp_points:
                continue
            df = pd.DataFrame(
                {
                    "Station": [p.station for p in comp_points],
                    f"Power_{cfg.period_x}s": [p.psd_x for p in comp_points],
                    f"Power_{cfg.period_y}s": [p.psd_y for p in comp_points],
                }
            )
            sheet_name = comp[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Saved {out_path}")
    
    

class ComponentPlotter:
    def __init__(self, cfg: PlotConfig) -> None:
        self.cfg = cfg
        self.cfg.out_dir.mkdir(parents=True, exist_ok=True)

    def plot(self, points: list[PSDPoint]) -> None:
        if not points:
            print("NO PSD POINTS TO PLOT")
            return
        components = sorted({p.component for p in points})

        for comp in components:
            comp_points = [p for p in points if p.component == comp]
            if not comp_points:
                continue

            x_vals = [p.psd_x for p in comp_points]
            y_vals = [p.psd_y for p in comp_points]
            labels = [p.station for p in comp_points]
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.scatter(x_vals, y_vals, s=40, edgecolors='black',linewidths=0.3,alpha=0.8)

            texts = []
            for x, y, label in zip(x_vals, y_vals, labels):
                txt = ax.text(
                    x,
                    y,
                    label,
                    fontsize=7,
                    ha="left",
                    va="center",
                )
                texts.append(txt)

            adjust_text(
                texts,
                ax=ax,
                only_move={"points": "y", "text": "xy"},  # intelligently spreads labels
            )

            ax.set_xlabel(f"Power [10log(m^2/sec^4/Hz)] (dB) at {self.cfg.period_x} s", fontsize=10)
            ax.set_ylabel(f"Power [10log(m^2/sec^4/Hz)] (dB) at {self.cfg.period_y} s", fontsize=10)
            ax.set_title(f"Component: {comp}, Network: {self.cfg.network}, stat: {self.cfg.stat}", fontsize=10)
            ax.grid(False)

            out_name = (
                f"{self.cfg.network}_{comp}_"
                f"{int(self.cfg.period_x)}vs{int(self.cfg.period_y)}_"
                f"{self.cfg.stat}.png"
            )
            out_path = self.cfg.out_dir / out_name
            try:
                fig.savefig(out_path, dpi=200)
            except OSError as exc:
                print(f"Could not save {out_path}: {exc}")
            else:
                print(f"Saved {out_path}")
            finally:
                plt.close(fig)



# =========================== main ===========================

def main() -> None:
    if len(sys.argv) > 1:
        cfg_path = Path(sys.argv[1])
    else:
        cfg_path = Path("config.yml")
    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        print(f"config error: {exc}")
        sys.exit(1)
    builder = PSDMatrixBuilder(cfg)
    points = builder.build_points()
    excel(points, cfg)
    plotter = ComponentPlotter(cfg)
    plotter.plot(points)

if __name__ == "__main__":
    main()




