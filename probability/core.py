from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

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
