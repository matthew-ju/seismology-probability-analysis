from __future__ import annotations
from typing import Protocol, List, Iterable, Mapping, Sequence
from pathlib import Path
from csv import writer
from core import PdfRecord, LineParser, DefaultLineParser

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

def write_percentiles_csv(
    out_path: str | Path,
    per_period: Mapping[float, Mapping[float, float]],
    percentiles: Sequence[float],
    total_files: int = 0,
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
    
    header.append("total_files")

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
                row.append(str(total_files))
                csv_writer.writerow(row)
                p_idx += 1
    except OSError as exc:
        print(f"[ERROR] Cannot write CSV to {path}: {exc}")
