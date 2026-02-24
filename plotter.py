from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import pandas as pd
from adjustText import adjust_text

from core_models import PSDPoint
from config_loader import PlotConfig


RESULTS_DIR = Path(__file__).resolve().parent / "psd_results"


class ComponentPlotter:
    def __init__(self, cfg: PlotConfig) -> None:
        self.cfg = cfg
        self.output_dir = RESULTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot(self, points: List[PSDPoint]) -> None:
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
            file_counts = [p.file_count for p in comp_points]

            # Create custom colormap
            colors = ['magenta', 'blue', 'cyan', 'lime', 'yellow', 'orange', 'red']
            cmap = mcolors.LinearSegmentedColormap.from_list("completeness", colors)
            
            min_files = min(file_counts) if file_counts else 0
            max_files = max(file_counts) if file_counts else 0
            norm = mcolors.Normalize(vmin=min_files, vmax=max_files)

            fig, ax = plt.subplots(figsize=(10, 8))
            scatter = ax.scatter(x_vals, y_vals, s=80, edgecolors='black',
                                 linewidths=0.5, alpha=0.9, 
                                 c=file_counts, cmap=cmap, norm=norm)

            # Add colorbar
            cbar = fig.colorbar(scatter, ax=ax)
            cbar.set_label('Data Completeness (File Count)')
            
            # Set specific ticks for min, mid, and max
            mid_files = (min_files + max_files) / 2
            cbar.set_ticks([min_files, mid_files, max_files])
            cbar.set_ticklabels([f"{min_files} (Min)", f"{mid_files:.1f} (Mid)", f"{max_files} (Max)"])

            texts = []
            for x, y, label in zip(x_vals, y_vals, labels):
                txt = ax.text(x, y, label, fontsize=8, ha="left", va="center")
                texts.append(txt)

            adjust_text(
                texts,
                ax=ax,
                only_move={"points": "y", "text": "xy"},
                arrowprops=dict(arrowstyle="-", color='gray', lw=0.5),
            )

            ax.set_xlabel(
                f"Power [10log(m²/sec⁴/Hz)] (dB) at {int(self.cfg.period_x)} s",
                fontsize=12,
            )
            ax.set_ylabel(
                f"Power [10log(m²/sec⁴/Hz)] (dB) at {int(self.cfg.period_y)} s",
                fontsize=12,
            )
            ax.set_title(
                f"Network: {self.cfg.network}, Component: {comp}\n"
                f"Stat: {self.cfg.stat}  |  {self.cfg.start_year}.{self.cfg.start_day:03d} - {self.cfg.end_year}.{self.cfg.end_day:03d}",
                fontsize=14,
            )
            ax.grid(True, linestyle='--', alpha=0.6)

            out_name = (
                f"{self.cfg.network}_{comp}_"
                f"{int(self.cfg.period_x)}vs{int(self.cfg.period_y)}_"
                f"{self.cfg.stat}.png"
            )
            out_path = self.output_dir / out_name
            try:
                fig.savefig(out_path, dpi=200, bbox_inches='tight')
                print(f"Saved plot: {out_path}")
            except OSError as exc:
                print(f"Could not save {out_path}: {exc}")
            finally:
                plt.close(fig)

    def save_excel(self, points: List[PSDPoint]) -> None:
        if not points:
            print("No PSD points for Excel.")
            return

        by_comp: dict[str, list[PSDPoint]] = {}
        for p in points:
            by_comp.setdefault(p.component, []).append(p)

        out_name = (
            f"{self.cfg.network}_PSD_"
            f"{int(self.cfg.period_x)}vs{int(self.cfg.period_y)}_"
            f"{self.cfg.stat}.xlsx"
        )
        out_path = self.output_dir / out_name

        try:
            with pd.ExcelWriter(out_path) as writer:
                for comp, comp_points in sorted(by_comp.items()):
                    if not comp_points:
                        continue
                    df = pd.DataFrame(
                        {
                            "Station": [p.station for p in comp_points],
                            f"Power_{int(self.cfg.period_x)}s": [p.psd_x for p in comp_points],
                            f"Power_{int(self.cfg.period_y)}s": [p.psd_y for p in comp_points],
                        }
                    )
                    sheet_name = comp[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"Saved Excel: {out_path}")
        except Exception as e:
            print(f"Failed to save Excel: {e}")
