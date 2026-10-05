"""Download, load, and normalize CFPB complaint archive exports."""

from __future__ import annotations

import re
import sys
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "https://files.consumerfinance.gov/f/documents/"

# Ported from data_spike/spike.py. From the CFPB narratives archive page
# (complaints received through Aug 14, 2026). Keys are the months each export covers.
EXPORTS: dict[str, str] = {
    "2026-08": "CCDB_Export_21_August_2026.zip",
    "2026-07": "CCDB_Export_20_July_2026.zip",
    "2026-06": "CCDB_Export_19_June_2026.zip",
    "2026-05": "CCDB_Export_18_May_2026.zip",
    "2026-04": "CCDB_Export_17_April_2026.zip",
    "2026-03": "CCDB_Export_16_March_2026.zip",
    "2026-01_02": "CCDB_Export_15_January_2026_through_February_2026.zip",
    "2025-11_12": "CCDB_Export_14_November_2025_through_December_2025.zip",
    "2025-09_10": "CCDB_Export_13_September_2025_through_October_2025.zip",
    "2025-07_08": "CCDB_Export_12_July_2025_through_August_2025.zip",
    "2025-05_06": "CCDB_Export_11_May_2025_through_June_2025.zip",
    "2025-03_04": "CCDB_Export_10_March_2025_through_April_2025.zip",
    "2025-01_02": "CCDB_Export_9_January_2025_through_February_2025.zip",
    "2024-11_12": "CCDB_Export_8_November_2024_through_December_2024.zip",
    "2024-08_10": "CCDB_Export_7_August_2024_through_October_2024.zip",
    "2024-04_07": "CCDB_Export_6_April_2024_through_July_2024.zip",
    "2023-09_2024-03": "CCDB_Export_5_September_2023_through_March_2024.zip",
    "2022-11_2023-08": "CCDB_Export_4_November_2022_through_August_2023.zip",
    "2021-05_2022-10": "CCDB_Export_3_May_2021_through_October_2022.zip",
    "2018-05_2021-04": "CCDB_Export_2_May_2018_through_April_2021.zip",
    "2011-12_2018-04": "CCDB_Export_1_December_2011_through_April_2018.zip",
}
# September 2025 through August 2026.
RECENT: list[str] = [
    "2026-08", "2026-07", "2026-06", "2026-05", "2026-04", "2026-03",
    "2026-01_02", "2025-11_12", "2025-09_10",
]

# Canonical column names, with the variants we might meet (compared after snake()).
# Ported from data_spike/spike.py, plus zip_code.
COLUMNS: dict[str, list[str]] = {
    "complaint_id": ["complaint_id"],
    "date_received": ["date_received"],
    "product": ["product"],
    "sub_product": ["sub_product"],
    "issue": ["issue"],
    "sub_issue": ["sub_issue"],
    "narrative": ["consumer_complaint_narrative", "complaint_what_happened", "narrative"],
    "company": ["company"],
    "state": ["state"],
    "zip_code": ["zip_code"],
    "tags": ["tags"],
    "submitted_via": ["submitted_via"],
    "company_response": ["company_response_to_consumer", "company_response"],
    "timely": ["timely_response", "timely"],
}

CHUNK_ROWS = 200_000


def snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def canonical_map(columns: list[str]) -> dict[str, str]:
    """Map source column -> canonical name, taking the first variant present."""
    lookup = {snake(c): c for c in columns}
    return {
        lookup[hits[0]]: canon
        for canon, variants in COLUMNS.items()
        if (hits := [v for v in variants if v in lookup])
    }


def export_url(file_name: str) -> str:
    return f"{BASE_URL}{file_name}"


def download(names: Iterable[str], raw_dir: Path) -> list[Path]:
    """Stream each export zip to raw_dir, skipping files already present."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    return [_download_one(EXPORTS[name], raw_dir) for name in names]


def _download_one(file_name: str, raw_dir: Path) -> Path:
    target = raw_dir / file_name
    if target.exists():
        print(f"  have {file_name}")
        return target
    partial = target.with_suffix(".part")
    with httpx.stream("GET", export_url(file_name), follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with partial.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                fh.write(chunk)
                done += len(chunk)
                _progress(file_name, done, total)
    partial.rename(target)
    sys.stdout.write("\n")
    return target


def _progress(name: str, done: int, total: int) -> None:
    mb = done / 1e6
    pct = f" {100 * done / total:5.1f}%" if total else ""
    sys.stdout.write(f"\r  {name}: {mb:8.1f} MB{pct}")
    sys.stdout.flush()


def _read_csv_chunks(handle: object) -> Iterator[pd.DataFrame]:
    return pd.read_csv(handle, dtype=str, chunksize=CHUNK_ROWS, keep_default_na=False)


def read_tables(path: Path) -> Iterator[pd.DataFrame]:
    """Yield chunks from every CSV inside a zip (or a bare CSV)."""
    if path.suffix.lower() == ".csv":
        yield from _read_csv_chunks(path)
        return
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        if not members:
            print(f"  warning: no CSV inside {path.name}: {archive.namelist()[:5]}")
        for member in members:
            with archive.open(member) as handle:
                yield from _read_csv_chunks(handle)


def read_export(path: Path) -> pd.DataFrame:
    """Read one export into canonical columns."""
    frames = [_select(chunk) for chunk in read_tables(path)]
    return normalize(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


def _select(chunk: pd.DataFrame) -> pd.DataFrame:
    mapping = canonical_map(list(chunk.columns))
    return chunk[list(mapping)].rename(columns=mapping)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename aliased columns, fill missing ones, and parse types."""
    out = _select(df).reindex(columns=list(COLUMNS), fill_value="")
    out = out.fillna("")
    for col in out.columns:
        out[col] = out[col].astype(str).str.strip()
    out["date_received"] = pd.to_datetime(out["date_received"], errors="coerce")
    out = out[out["complaint_id"].ne("") & out["date_received"].notna()]
    out["month"] = out["date_received"].dt.strftime("%Y-%m")
    return out.reset_index(drop=True)


def load(paths: Iterable[Path]) -> pd.DataFrame:
    """Load and concatenate exports, deduplicating on complaint_id."""
    frames = [read_export(p) for p in paths]
    if not frames:
        return normalize(pd.DataFrame(columns=list(COLUMNS)))
    return dedupe(pd.concat(frames, ignore_index=True))


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per complaint_id, preferring the row with a narrative."""
    ranked = df.assign(_has_text=df["narrative"].ne("")).sort_values(
        ["_has_text", "date_received"], ascending=[False, False], kind="stable"
    )
    kept = ranked.drop_duplicates("complaint_id", keep="first").drop(columns="_has_text")
    return kept.sort_values(["date_received", "complaint_id"]).reset_index(drop=True)


def complete_months(df: pd.DataFrame) -> list[str]:
    """Months fully covered by the data: drops a partial first or last month.

    A day of slack at each edge tolerates a quiet first or last day.
    """
    if df.empty:
        return []
    months = sorted(df["month"].unique())
    first_day = df["date_received"].min()
    last_day = df["date_received"].max()
    drop_first = first_day.day > 2
    drop_last = last_day.day < last_day.days_in_month - 1
    end = len(months) - 1 if drop_last else len(months)
    return months[int(drop_first) : end]


def select_exports(choice: str) -> list[str]:
    """'recent', 'all', or comma-separated EXPORTS keys such as '2026-07,2026-06'."""
    if choice == "recent":
        return RECENT
    if choice == "all":
        return list(EXPORTS)
    names = [n.strip() for n in choice.split(",") if n.strip()]
    unknown = [n for n in names if n not in EXPORTS]
    if unknown:
        raise ValueError(f"unknown exports {unknown}; choose from {list(EXPORTS)}")
    return names
