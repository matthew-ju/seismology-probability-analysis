#!/usr/bin/env python3
'''
PSD scatter plot generator using the probability engine.

Usage:
    python main.py config.yml
'''
from __future__ import annotations

import sys
from pathlib import Path

from config_loader import load_config, ConfigError
from channel_builder import ChannelBuilder
from data_integration import ProbabilityRunner, CSVReader
from plotter import ComponentPlotter


def main() -> None:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yml")

    if not cfg_path.exists():
        print(f"Config file not found: {cfg_path}")
        sys.exit(1)

    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    print(f"Config loaded: {len(cfg.stations)} stations, stat={cfg.stat}")
    print(f"Time range: {cfg.start_year}.{cfg.start_day} – {cfg.end_year}.{cfg.end_day}")
    print(f"Periods: {cfg.period_x}s vs {cfg.period_y}s")

    # Step 1: Build channel list
    builder = ChannelBuilder(cfg)
    channels = builder.build_channels()

    if not channels:
        print("No valid channels found. Exiting.")
        sys.exit(0)

    unique_stations = sorted({ch.station for ch in channels})
    print(f"Active stations: {len(unique_stations)}")

    # Step 2: Run probability engine (generates CSVs)
    runner = ProbabilityRunner(cfg)
    runner.run(unique_stations)

    # Step 3: Read CSVs -> PSDPoints
    reader = CSVReader(cfg)
    points = reader.build_points(channels)

    if not points:
        print("No PSD points generated. Check probability output.")
        sys.exit(0)

    print(f"\nGenerated {len(points)} PSD points")

    # Step 4: Plot and save
    plotter = ComponentPlotter(cfg)
    plotter.plot(points)
    plotter.save_excel(points)

    print("\nDone. Results saved to psd_results/")


if __name__ == "__main__":
    main()
