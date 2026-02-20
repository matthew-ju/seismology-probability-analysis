from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Sequence
from core import PdfRecord

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
            if i == n_items - 1:
                cumulative = 1.0000001      #  avoid rounding error

            while t_idx < len(targets) and cumulative >= targets[t_idx]:
                res[targets[t_idx]] = power
                t_idx += 1
        return res

    def percentiles_all_periods(self, percentiles: Sequence[float],) -> Dict[float, Dict[float, float]]:
        result: Dict[float, Dict[float, float]] = {}
        periods = sorted(self.probs.keys())
        idx = 0
        while idx < len(periods):
            period = periods[idx]
            result[period] = self.percentiles_for_period(period, percentiles)
            idx += 1
        return result
