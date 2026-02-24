from __future__ import annotations
from typing import Protocol, Sequence, Dict
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe
import numpy as np

from processing import PeriodPowerAggregator

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
        self.ax.set_xlabel(r"Period (s)")
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

            # convert periods (log10 seconds) to regular seconds
            periods_seconds = [10**p for p in periods]
            
            mesh = self.ax.pcolormesh(
                periods_seconds, powers, z_matrix, 
                cmap=self.rainbow, vmin=0, vmax=0.30, shading='auto'
            )
            self.ax.set_xscale('log')
            self.fig.colorbar(mesh, ax=self.ax, label="Probability")
            self._plot_percentile_lines(periods, percentiles)
            self.ax.axis([limits['xlow'], limits['xhigh'], limits['ylow'], limits['yhigh']])
            
        except Exception as e:
            print(f"[ERROR] during rendering: {e}")

    def _plot_percentile_lines(self, periods: Sequence[float], percentiles: Sequence[float]) -> None:
        """Calculates and draws lines for each requested percentile."""
        # aggregator uses log10 periods
        results = self.aggregator.percentiles_all_periods(percentiles)
        periods_seconds = [10**p for p in periods]
        
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
                periods_seconds, 
                y_values, 
                label=label, 
                linestyle=':', 
                linewidth=1.0
            )
            line.set_path_effects([
                pe.Stroke(linewidth=2.0, foreground='black'),
                pe.Normal()
            ])
            pct_idx += 1
        self.ax.legend(loc='upper right')
