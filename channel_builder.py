from __future__ import annotations

import sys
from itertools import product
from pathlib import Path
from typing import List, Set, Tuple

from core_models import StationChannel
from config_loader import PlotConfig


class ChannelBuilder:
    def __init__(self, cfg: PlotConfig):
        self.cfg = cfg

    def _load_active_hhz_stations(self) -> List[Tuple[str, str]]:
        '''Return (station, location) pairs for all active HHZ in BK.channel.summary.day.
        "active" channel: End time starts with "3000/01/01,00:00:00"
        '''
        summary_path = Path("/work/dc6/ftp/pub/doc/BK.info/BK.channel.summary.day")
        stations: Set[Tuple[str, str]] = set()

        if not summary_path.exists():
            print(f"Warning: Summary file not found at {summary_path}. Skipping active filter.")
            return []

        try:
            with summary_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip() or line.startswith("Stat ") or set(line.strip()) == {"-"}:
                        continue
                    parts = line.split()
                    if len(parts) < 7:
                        continue
                    stat, net, cha, loc = parts[0], parts[1], parts[2], parts[3]
                    end_time = parts[6]

                    if net != self.cfg.network:
                        continue
                    if not cha.startswith("HHZ"):
                        continue
                    if not end_time.startswith("3000/01/01,00:00:00"):
                        continue
                    stations.add((stat, loc))
        except OSError as exc:
            print(f"COULDN'T READ: {summary_path}: {exc}", file=sys.stderr)
            return []

        return sorted(list(stations))

    def build_channels(self) -> List[StationChannel]:
        active_pairs = self._load_active_hhz_stations()

        selected_pairs: List[Tuple[str, str]] = []

        if self.cfg.stations:
            wanted = set(self.cfg.stations)

            if active_pairs:
                for sta, loc in active_pairs:
                    if sta in wanted:
                        selected_pairs.append((sta, loc))

                found_stats = {s[0] for s in active_pairs}
                missing = wanted - found_stats
                if missing:
                    print(f"Warning: stations not found in active list: {sorted(missing)}")
            else:
                for sta in sorted(wanted):
                    selected_pairs.append((sta, self.cfg.location))
        else:
            selected_pairs = active_pairs

        if not selected_pairs:
            print("No stations selected.", file=sys.stderr)
            return []

        combos = product(selected_pairs, self.cfg.components)
        channels: List[StationChannel] = [
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
