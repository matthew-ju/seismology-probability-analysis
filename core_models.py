from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StationChannel:
    network: str
    station: str
    location: str
    component: str
    base_dir: Path

    @property
    def label(self) -> str:
        return self.station


@dataclass(frozen=True)
class PSDPoint:
    component: str
    station: str
    psd_x: float
    psd_y: float
    file_count: int
