'''
Runs the probability engine (as a subprocess) for the configured stations/components,
then reads the output CSV files to extract PSD values at target periods.
'''
from __future__ import annotations

import csv
import subprocess
import sys
import numpy as np
from pathlib import Path
from typing import List, Optional

from core_models import PSDPoint, StationChannel
from config_loader import PlotConfig


PROBABILITY_DIR = Path(__file__).resolve().parent / "probability"


class ProbabilityRunner:
    '''Runs probability/main.py as a subprocess to generate percentile CSVs.'''

    def __init__(self, cfg: PlotConfig):
        self.cfg = cfg
        self.prob_main = PROBABILITY_DIR / "main.py"

    def run(self, stations: List[str]) -> None:
        if not self.prob_main.exists():
            print(f"ERROR: probability/main.py not found at {self.prob_main}")
            sys.exit(1)

        pct_args = [str(p) for p in self.cfg.percentiles]

        cmd = [
            sys.executable, str(self.prob_main),
            "--root", str(self.cfg.base_dir),
            "--network", self.cfg.network,
            "--location", self.cfg.location,
            "--stations", *stations,
            "--components", *self.cfg.components,
            "--start-year", str(self.cfg.start_year),
            "--start-day", str(self.cfg.start_day),
            "--end-year", str(self.cfg.end_year),
            "--end-day", str(self.cfg.end_day),
            "--percentiles", *pct_args,
        ]

        print(f"Running probability engine for {len(stations)} stations...")
        print(f"  Command: {' '.join(cmd[:6])} ...")

        result = subprocess.run(
            cmd,
            cwd=str(PROBABILITY_DIR),
            capture_output=False,
        )

        if result.returncode != 0:
            print(f"WARNING: probability engine exited with code {result.returncode}")


class CSVReader:
    '''Reads percentile CSV files produced by the probability engine.'''

    def __init__(self, cfg: PlotConfig):
        self.cfg = cfg
        self.stat_column = self._resolve_stat_column(cfg.stat)

    def _resolve_stat_column(self, stat: str) -> str:
        '''Convert stat name to CSV column name.
        "p99" -> "p99", "p1" -> "p1", "mode" -> "p50" (fallback)
        '''
        if stat.lower().startswith("p") and stat[1:].isdigit():
            return stat.lower()
        # Fallback mapping for legacy stat names
        fallback = {
            "mode": "p50",
            "mean": "p50",
            "min": "p1",
            "max": "p100",
            "q_low": "p25",
            "q_high": "p75",
        }
        mapped = fallback.get(stat.lower())
        if mapped:
            print(f"  Mapping legacy stat '{stat}' -> CSV column '{mapped}'")
            return mapped
        print(f"  Warning: Unknown stat '{stat}', defaulting to 'p50'")
        return "p50"

    def _find_csv(self, station: str, component: str) -> Optional[Path]:
        '''Find the percentile CSV for a station+component.'''
        station_dir = PROBABILITY_DIR / station
        if not station_dir.is_dir():
            return None

        time_tag = f"{self.cfg.start_year}.{self.cfg.start_day}-{self.cfg.end_year}.{self.cfg.end_day}"
        expected = f"percentiles.{station}.{component}.{time_tag}.csv"
        csv_path = station_dir / expected

        if csv_path.exists():
            return csv_path

        # Fallback: find any matching CSV
        pattern = f"percentiles.{station}.{component}.*.csv"
        matches = sorted(station_dir.glob(pattern))
        if matches:
            return matches[-1]  # most recent
        return None

    def _read_data_from_csv(self, csv_path: Path, target_period: float) -> tuple[float, int]:
        '''Read the stat column value at the row closest to target_period, and file count.'''
        target_log = np.log10(target_period)

        periods_log = []
        values = []
        file_count = 0

        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            if self.stat_column not in fieldnames:
                print(f"  Warning: column '{self.stat_column}' not in {csv_path.name}. Available: {fieldnames}")
                return float("nan"), 0

            for row in reader:
                try:
                    p_log = float(row["period_log10"])
                    val = float(row[self.stat_column])
                    periods_log.append(p_log)
                    values.append(val)
                    # total_files is the same for all rows in this CSV
                    if "total_files" in row:
                        file_count = int(row["total_files"])
                except (ValueError, KeyError):
                    continue

        if not periods_log:
            return float("nan"), 0

        arr = np.array(periods_log)
        idx = int(np.argmin(np.abs(arr - target_log)))
        return values[idx], file_count

    def build_points(self, channels: List[StationChannel]) -> List[PSDPoint]:
        points: List[PSDPoint] = []

        for ch in channels:
            csv_path = self._find_csv(ch.station, ch.component)
            if csv_path is None:
                print(f"  No CSV found for {ch.station}.{ch.component}, skipping")
                continue

            val_x, files_x = self._read_data_from_csv(csv_path, self.cfg.period_x)
            val_y, files_y = self._read_data_from_csv(csv_path, self.cfg.period_y)

            if np.isnan(val_x) or np.isnan(val_y):
                print(f"  Warning: NaN value for {ch.station}.{ch.component}, skipping")
                continue

            points.append(PSDPoint(
                component=ch.component,
                station=ch.station,
                psd_x=val_x,
                psd_y=val_y,
                file_count=files_x # Assuming x and y have same file count from same CSV
            ))

        return points
