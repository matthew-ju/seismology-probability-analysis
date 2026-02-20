#!/usr/bin/env python3
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Protocol, Sequence, Any
from csv import writer
import argparse

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe
import numpy as np

# ============================== Configuration ============================



DEFAULT_ROOT = "/ref/dc14/PDF/STATS"
DEFAULT_NETWORK = "BK"
DEFAULT_LOCATION = "00"

DEFAULT_STATIONS = ("BKS", "THOM")   # e.g. ("BKS", "AASB")
DEFAULT_COMPONENTS = ("HHE", "HHN", "HHZ", "HNE", "HNN", "HNZ")     # e.g. ("HHZ", "HHN", "HHE")

# None => accept any year/day
DEFAULT_START_YEAR = 2025           # e.g. 2026 for 2026.*
DEFAULT_START_DAY = 1      # e.g. 5  for 2026.005

DEFAULT_END_YEAR = 2025
DEFAULT_END_DAY = 366        # e.g. 334 for 2026.334

# e.g. [0.05, 0.10, 0.25] for 5th, 10th, and 25th percentiles
DEFAULT_PERCENTILES = [0.01, 0.05, 0.1, 0.15, 0.25, 0.50, 0.75, 0.9, 0.95, 0.99, 1.0]  



# =========================================================================




# ============================== core ==============================

@dataclass(frozen=True)
class PdfRecord:
    period_log10: float
    power_db: float
    probability: float

class LineParser(Protocol):
    def parse(self, line: str) -> PdfRecord | None:
        ...

class DefaultLineParser:
    def parse(self, line: str) -> PdfRecord | None:
        parts = line.split()
        if len(parts) < 3:
            return None
        try:
            period = float(parts[0])
            power = float(parts[1])
            prob = float(parts[2])
        except ValueError:
            return None
        return PdfRecord(period, power, prob)



# ============================== file/directory reader ==============================
class DirectoryResolver(Protocol):
    def get_station_path(self, root: Path, net: str, sta: str, loc: str, comp: str, year: int) -> Path:
        ...


class SeismicPathResolver:
    """Handles directory naming conventions based on the year."""
    def resolve(self, root: str | Path, net: str, sta: str, loc: str, comp: str, year: int) -> Path:
        # 2026 uses 'wrk', others use 'wrkYYYY'
        suffix = "wrk" if year == 2026 else f"wrk{year}"
        target = Path(root) / f"{net}.{sta}.{loc}" / comp / suffix
        
        if not target.is_dir():
            raise FileNotFoundError(f"Directory not found for year {year}: {target}")
        return target
    

class PdfDirectoryReader:
    """
    reads PDFanalysis.*.pdf files from a directory and yields PdfRecord objects
    """
    def __init__(
        self,
        root: str | Path,
        pattern: str = "PDFanalysis.*.pdf",
        parser: LineParser | None = None,
        year: int | None = None,
        start_day: int | None = None,
        end_day: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.pattern = pattern
        self.parser: LineParser = parser or DefaultLineParser()
        self.year = year
        self.start_day = start_day
        self.end_day = end_day
        all_files = sorted(self.root.glob(self.pattern))
        self._files: List[Path] = []
        idx = 0
        n = len(all_files)
        while idx < n:
            path = all_files[idx]
            if self._accept_file(path):
                self._files.append(path)
            idx += 1
        self.file_count: int = len(self._files)

    def _accept_file(self, path: Path) -> bool:
        if self.year is None and self.start_day is None and self.end_day is None:
            return True
        name = path.name  # e.g. PDFanalysis.2025.005.pdf
        parts = name.split(".")
        if len(parts) < 4:
            return False
        try:
            file_year = int(parts[1])
            file_day = int(parts[2])
        except ValueError:
            return False
        if self.year is not None and file_year != self.year:
            return False
        if self.start_day is not None and file_day < self.start_day:
            return False
        if self.end_day is not None and file_day > self.end_day:
            return False
        return True



    # ============================== public API ============================== 
    def iter_records(self) -> Iterable[PdfRecord]:
        idx = 0
        while idx < self.file_count:
            path = self._files[idx]
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for raw in handle:
                        rec = self.parser.parse(raw)
                        if rec is not None:
                            yield rec
            except OSError as exc:
                print(f"[ERROR] Unable to read {path}: {exc}")
            idx += 1



# ============================== aggregators ==============================
class Aggregator(ABC):
    @abstractmethod
    def add_record(self, record: PdfRecord) -> None:
        ...

    @abstractmethod
    def finalize(self, num_files: int) -> None:
        """
        num_files is used to average probabilities across files after all added
        """
        ...

class PeriodPowerAggregator(Aggregator):
    def __init__(self) -> None:
        self.sums: Dict[float, Dict[float, float]] = {}   # sums[period][power] = sum of probabilities over all files
        self.probs: Dict[float, Dict[float, float]] = {}   # probs[period][power] = averaged + normalized probability

    def add_record(self, record: PdfRecord) -> None:
        period_map = self.sums.get(record.period_log10)
        if period_map is None:
            period_map = {}
            self.sums[record.period_log10] = period_map
        prev = period_map.get(record.power_db, 0.0)
        period_map[record.power_db] = prev + record.probability

    def finalize(self, num_files: int) -> None:
        if num_files <= 0:
            raise ValueError("num_files must be positive")
        periods = list(self.sums.keys())
        p_idx = 0
        while p_idx < len(periods):
            period = periods[p_idx]
            power_map = self.sums[period]
            avg_map: Dict[float, float] = {}
            powers = list(power_map.keys())
            pw_idx = 0
            while pw_idx < len(powers):
                power = powers[pw_idx]
                avg_map[power] = power_map[power] / float(num_files)
                pw_idx += 1

            # renormalization per period (robust to rounding)
            total_prob = sum(avg_map.values())
            if total_prob > 0.0:
                scale = 1.0 / total_prob
                powers = list(avg_map.keys())
                pw_idx = 0
                while pw_idx < len(powers):
                    power = powers[pw_idx]
                    avg_map[power] *= scale
                    pw_idx += 1
            self.probs[period] = avg_map
            p_idx += 1



    # ============================== Percentile ==============================

    def percentiles_for_period(
        self,
        period: float,
        percentiles: Sequence[float],
    ) -> Dict[float, float]:
        """
        For a single period, compute power_dB at requested percentiles
        percentiles should be in [0, 1], e.g. [0.05, 0.10, 0.25]
        returns mapping percentile -> power_dB
        """
        power_map = self.probs.get(period)
        if not power_map:
            raise KeyError(f"No data available for {period}")

        valid_items = [
            (pwr, prb) for pwr, prb in power_map.items() 
            if prb > 1e-9
        ]      # remove bins without entries (e.g, 0.00000000)
        
        items = sorted(valid_items, key=lambda kv: kv[0])
        
        targets = sorted(percentiles)
        res: Dict[float, float] = {}
        t_idx = 0
        cumulative = 0.0
        n_items = len(items)

        for i in range(n_items):
            power, prob = items[i]
            cumulative += prob
            # print("period: ", period)
            # print("power: ", power)
            # print("prob: ", prob)
            # print("cumulative: ", cumulative)
            # print()
            if i == n_items - 1:
                cumulative = 1.0000001      #  avoid rounding error

            while t_idx < len(targets) and cumulative >= targets[t_idx]:
                res[targets[t_idx]] = power
                t_idx += 1
        return res
        # t_idx = 0
        # cumulative = 0.0
        # i = 0
        # n_items = len(items)
        # while i < n_items and t_idx < len(targets):
        #     power, prob = items[i]
        #     cumulative += prob
        #     while t_idx < len(targets) and cumulative >= targets[t_idx]:
        #         res[targets[t_idx]] = power
        #         t_idx += 1
        #     i += 1
        # return res

    def percentiles_all_periods(self, percentiles: Sequence[float],) -> Dict[float, Dict[float, float]]:
        result: Dict[float, Dict[float, float]] = {}
        periods = sorted(self.probs.keys())
        idx = 0
        while idx < len(periods):
            period = periods[idx]
            result[period] = self.percentiles_for_period(period, percentiles)
            idx += 1
        return result



# ============================== csv file ============================
def write_percentiles_csv(
    out_path: str | Path,
    per_period: Mapping[float, Mapping[float, float]],
    percentiles: Sequence[float],
    year: int | None = None,
    start_day: int | None = None,
    end_day: int | None = None,
) -> None:
    header: List[str] = ["period_log10"]
    pct_labels: List[str] = []
    idx = 0
    while idx < len(percentiles):
        pct = int(round(percentiles[idx] * 100))
        label = f"p{pct}"
        pct_labels.append(label)
        header.append(label)
        idx += 1

    path = Path(out_path)
    try:
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv_writer = writer(fh)
            csv_writer.writerow(header)
            periods = sorted(per_period.keys())
            p_idx = 0
            while p_idx < len(periods):
                period = periods[p_idx]
                row: List[float | str] = [f"{period:.6f}"]
                pct_map = per_period[period]
                c_idx = 0
                while c_idx < len(percentiles):
                    pct = percentiles[c_idx]
                    power = pct_map.get(pct, float("nan"))
                    row.append(f"{power:.3f}")
                    c_idx += 1
                csv_writer.writerow(row)
                p_idx += 1
    except OSError as exc:
        print(f"[ERROR] Cannot write CSV to {path}: {exc}")





# ========================== Plotting ==========================

class Visualizer(Protocol):
    """Protocol for result visualization components."""
    def render(self) -> None: ...
    def save(self, path: str) -> None: ...

class BasePlotter:
    """Base class providing common plotting utilities."""
    def __init__(self, title: str):
        self.title = title
        self.fig, self.ax = plt.subplots(figsize=(12, 8))
        self._setup_style()

    def _setup_style(self) -> None:
        self.ax.set_title(self.title)
        self.ax.set_xlabel(r"Period ($\log_{10} s$)")
        self.ax.set_ylabel(r"Power ($dB$)")
        self.ax.grid(True, which='both', linestyle='--', alpha=0.5)

    def save(self, path: str) -> None:
        try:
            self.fig.tight_layout()
            self.fig.savefig(path)
            plt.close(self.fig)
        except OSError as e:
            print(f"[ERROR] Failed to save plot to {path}: {e}")

class PdfVisualizer(BasePlotter):
    """Inherits from BasePlotter to handle PDF-specific mesh and percentile plotting."""
    def __init__(self, title: str, aggregator: PeriodPowerAggregator):
        super().__init__(title)
        self.aggregator = aggregator
        self.rainbow = mcolors.LinearSegmentedColormap.from_list(
            "pdf_rainbow", 
            ['white', 'magenta', 'blue', 'cyan', 'lime', 'yellow', 'orange', 'red']
        )

    def render(self, percentiles: Sequence[float], limits: Dict[str, float]) -> None:
        """Generates the pcolormesh background and overlays percentile lines."""
        try:
            periods = sorted(self.aggregator.probs.keys())
            if not periods:
                return
            all_powers = set()
            p_idx = 0
            while p_idx < len(periods):
                all_powers.update(self.aggregator.probs[periods[p_idx]].keys())
                p_idx += 1
            powers = sorted(list(all_powers))

            z_matrix = np.zeros((len(powers), len(periods)))
            j = 0
            while j < len(periods):
                p_map = self.aggregator.probs[periods[j]]
                i = 0
                while i < len(powers):
                    z_matrix[i, j] = p_map.get(powers[i], 0.0)
                    i += 1
                j += 1

            mesh = self.ax.pcolormesh(
                periods, powers, z_matrix, 
                cmap=self.rainbow, vmin=0, vmax=0.30, shading='auto'
            )
            self.fig.colorbar(mesh, ax=self.ax, label="Probability")
            self._plot_percentile_lines(percentiles)
            self.ax.axis([limits['xlow'], limits['xhigh'], limits['ylow'], limits['yhigh']])
            
        except Exception as e:
            print(f"[ERROR] during rendering: {e}")

    def _plot_percentile_lines(self, percentiles: Sequence[float]) -> None:
        """Calculates and draws lines for each requested percentile."""
        results = self.aggregator.percentiles_all_periods(percentiles)
        periods = sorted(results.keys())
        
        pct_idx = 0
        while pct_idx < len(percentiles):
            pct = percentiles[pct_idx]
            y_values = []
            p_idx = 0
            while p_idx < len(periods):
                y_values.append(results[periods[p_idx]].get(pct, np.nan))
                p_idx += 1
            
            label = f"p{int(pct*100)}"
            line, = self.ax.plot(
                periods, 
                y_values, 
                label=label, 
                linestyle='--', 
                linewidth=2.0
            )
            line.set_path_effects([
                pe.Stroke(linewidth=4, foreground='black'),
                pe.Normal()
            ])
            pct_idx += 1
        self.ax.legend(loc='upper right')





# ============================== Main ==============================
def main() -> None:
    """
    Run percentile aggregation for one or more stations/components.

    Directories are constructed as: {root}/{network}.{station}.{location}/{component}/wrk
    Example:                        /ref/dc14/PDF/STATS/BK.BKS.00/HHZ/wrk
    """

    parser = argparse.ArgumentParser(description="Aggregate PDFanalysis probabilities and compute noise percentiles.")
    parser.add_argument(
        "--root",
        type=str,
        default=DEFAULT_ROOT,
        help="Root path to PDF/STATS (default: DEFAULT_ROOT).",
    )
    parser.add_argument(
        "--network",
        type=str,
        default=DEFAULT_NETWORK,
        help="Network code (default: BK).",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=DEFAULT_LOCATION,
        help="Location code (default: 00).",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        default=list(DEFAULT_STATIONS),
        help="List of stations (e.g. THOM BKS).",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        default=list(DEFAULT_COMPONENTS),
        help="List of components (e.g. HHZ HHN).",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help="Start year (inclusive).",
    )
    parser.add_argument(
        "--start-day",
        type=int,
        default=DEFAULT_START_DAY,
        help="Start Julian day.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
        help="End year (inclusive).",
    )
    parser.add_argument(
        "--end-day",
        type=int,
        default=DEFAULT_END_DAY,
        help="End Julian day.",
    )
    parser.add_argument(
        "--percentiles",
        nargs="+",
        type=float,
        default=DEFAULT_PERCENTILES,
        help="Percentiles as fractions (default: 0.05 0.10 0.25).",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="percentiles",
        help="Prefix for output CSVs. "
        "{prefix}.{station}.{component}.csv",
    )

    args = parser.parse_args()
    resolver = SeismicPathResolver()
    s_idx = 0
    stations = args.stations
    while s_idx < len(stations):
        station = stations[s_idx]
        station_out_dir = Path(station)
        try:
            station_out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] Could not create directory {station_out_dir}: {e}")
            s_idx += 1
            continue

        c_idx = 0
        components = args.components
        while c_idx < len(components):
            component = components[c_idx]
            
            aggregator = PeriodPowerAggregator()
            total_files_processed = 0

            current_year = args.start_year
            while current_year <= args.end_year:
                curr_min_day = args.start_day if current_year == args.start_year else 1
                curr_max_day = args.end_day if current_year == args.end_year else 366

                try:
                    station_dir = resolver.resolve(
                        args.root, args.network, station, args.location, component, current_year
                    )
                except FileNotFoundError:
                    current_year += 1
                    continue

                reader = PdfDirectoryReader(
                    station_dir,
                    year=current_year,
                    start_day=curr_min_day,
                    end_day=curr_max_day,
                )

                if reader.file_count > 0:
                    for rec in reader.iter_records():
                        aggregator.add_record(rec)
                    total_files_processed += reader.file_count
                
                current_year += 1

            if total_files_processed == 0:
                print(f"[WARN] No data found for {station}.{component} across {args.start_year}-{args.end_year}")
                c_idx += 1
                continue

            aggregator.finalize(total_files_processed)
            per_period = aggregator.percentiles_all_periods(args.percentiles)
            base_name = f"{args.output_prefix}.{station}.{component}"
            time_tag = f"{args.start_year}.{args.start_day}-{args.end_year}.{args.end_day}"
            filename = f"{base_name}.{time_tag}.csv"
            out_path = station_out_dir / filename
            
            plot_limits = {
                "xlow": -1.698970, "xhigh": 2.0, 
                "ylow": -200.0, "yhigh": -50.0
            }
            title = (f"PSD PDF: {DEFAULT_NETWORK}.{station}.{component} "
                     f"({args.start_year}.{args.start_day} - {args.end_year}.{args.end_day})")
            
            viz = PdfVisualizer(title, aggregator)
            viz.render(args.percentiles, plot_limits)
            
            image_name = out_path.with_suffix(".png")
            viz.save(str(image_name))
            write_percentiles_csv(
                out_path,
                per_period,
                args.percentiles
            )

            print(f"Processed {station}.{component}: {total_files_processed} files. Saved to {station_out_dir}")
            
            c_idx += 1
        s_idx += 1



if __name__ == "__main__":
    main()





