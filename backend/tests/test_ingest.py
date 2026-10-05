from __future__ import annotations

import pandas as pd

from radar import ingest
from tests import fixtures


def test_canonical_map_handles_csv_and_api_headers() -> None:
    csv_style = ingest.canonical_map(["Date received", "Consumer complaint narrative", "Timely response?"])
    api_style = ingest.canonical_map(["date_received", "complaint_what_happened", "timely"])
    assert csv_style == {
        "Date received": "date_received",
        "Consumer complaint narrative": "narrative",
        "Timely response?": "timely",
    }
    assert api_style == {
        "date_received": "date_received",
        "complaint_what_happened": "narrative",
        "timely": "timely",
    }


def test_canonical_map_ignores_unknown_columns() -> None:
    assert ingest.canonical_map(["Consumer consent provided?", "Product"]) == {"Product": "product"}


def test_load_normalizes_both_zips(complaints: pd.DataFrame) -> None:
    assert list(complaints.columns) == [*ingest.COLUMNS, "month"]
    assert complaints["narrative"].ne("").mean() > 0.5
    assert pd.api.types.is_datetime64_any_dtype(complaints["date_received"])


def test_dedupe_removes_overlap(complaints: pd.DataFrame) -> None:
    expected = len(fixtures.generate_rows())
    assert len(complaints) == expected
    assert complaints["complaint_id"].is_unique


def test_dedupe_prefers_row_with_narrative() -> None:
    df = ingest.normalize(pd.DataFrame({
        "complaint_id": ["1", "1"],
        "date_received": ["2026-01-02", "2026-01-02"],
        "narrative": ["", "money was taken"],
    }))
    assert ingest.dedupe(df)["narrative"].tolist() == ["money was taken"]


def test_complete_months_drops_partial_final_month(complaints: pd.DataFrame) -> None:
    months = ingest.complete_months(complaints)
    assert months[0] == "2025-09"
    assert months[-1] == "2026-07"
    assert "2026-08" not in months


def test_complete_months_drops_partial_first_month() -> None:
    df = ingest.normalize(pd.DataFrame({
        "complaint_id": ["1", "2", "3"],
        "date_received": ["2026-01-15", "2026-02-01", "2026-02-28"],
    }))
    assert ingest.complete_months(df) == ["2026-02"]


def test_select_exports() -> None:
    assert ingest.select_exports("recent")[0] == "2026-08"
    assert len(ingest.select_exports("all")) == len(ingest.EXPORTS)
    assert ingest.select_exports("2026-07,2026-06") == ["2026-07", "2026-06"]
