from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml


class ConfigError(Exception):
    '''when the configuration from YAML is invalid'''


@dataclass(frozen=True)
class PlotConfig:
    base_dir: Path
    network: str
    stations: List[str]
    location: str
    components: List[str]
    period_x: float
    period_y: float
    stat: str                        # e.g. "p99", "p50", "mode"
    out_dir: Path
    start_year: int
    end_year: int
    start_day: int
    end_day: int
    percentiles: List[float]         # e.g. [0.01, 0.05, 0.50, 0.99]


def _parse_stations(raw_val: Any) -> List[str]:
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
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Error reading YAML file: {exc}") from exc

    required_keys = {"base_dir", "network", "stations", "location",
                     "period_x", "period_y", "stat", "out_dir"}
    missing = required_keys - raw.keys()
    if missing:
        raise ConfigError(f"missing config keys: {', '.join(sorted(missing))}")

    stat_val = str(raw["stat"])

    components_raw = raw.get("components", ["HHZ", "HHN", "HHE"])
    if isinstance(components_raw, list):
        components = [str(c).strip() for c in components_raw if str(c).strip()]
    else:
        raise ConfigError("components must be a list of strings")

    stations = _parse_stations(raw["stations"])

    # Percentile defaults matching probability/config.py
    default_pcts = [0.05, 0.10]
    percentiles_raw = raw.get("percentiles", default_pcts)
    percentiles = [float(p) for p in percentiles_raw]

    return PlotConfig(
        base_dir=Path(str(raw["base_dir"])),
        network=str(raw["network"]),
        stations=stations,
        location=str(raw["location"]),
        components=components,
        period_x=float(raw["period_x"]),
        period_y=float(raw["period_y"]),
        stat=stat_val,
        out_dir=Path(str(raw["out_dir"])),
        start_year=int(raw.get("start_year", 2025)),
        end_year=int(raw.get("end_year", 2025)),
        start_day=int(raw.get("start_day", 1)),
        end_day=int(raw.get("end_day", 366)),
        percentiles=percentiles,
    )
