from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from radar import evaluate
from radar.schemas import Extraction, SkepticReview, ThemeOut
from tests.fakes import EXTRACTION, REVIEW


def test_review_sheet_pairs_extractions_with_narratives(complaints: pd.DataFrame, tmp_path: Path) -> None:
    ids = complaints.loc[complaints["narrative"].ne(""), "complaint_id"].head(80).tolist()
    cache = {cid: Extraction.model_validate(EXTRACTION) for cid in ids}
    rows = evaluate.review_rows(complaints, cache)
    assert len(rows) == evaluate.SHEET_SIZE
    assert all(r["narrative"] and r["rating"] == "" for r in rows)
    assert rows == evaluate.review_rows(complaints, cache)  # seeded
    sheet = tmp_path / "sheet.csv"
    evaluate.write_sheet(sheet, rows)
    score = evaluate.score_sheet(sheet)
    assert score.total == evaluate.SHEET_SIZE and score.rated == 0 and score.accuracy is None


def _sheet(tmp_path: Path, ratings: list[str]) -> Path:
    path = tmp_path / "rated.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=evaluate.SHEET_FIELDS)
        writer.writeheader()
        writer.writerows({"complaint_id": str(i), "rating": r} for i, r in enumerate(ratings))
    return path


def test_score_counts_only_rated_rows(tmp_path: Path) -> None:
    score = evaluate.score_sheet(_sheet(tmp_path, ["accurate", "Accurate ", "partially", "wrong", ""]))
    assert (score.rated, score.accurate, score.partially, score.wrong) == (4, 2, 1, 1)
    assert score.accuracy == 0.5 and score.accurate_or_partial == 0.75


def test_score_rejects_unknown_ratings(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate.score_sheet(_sheet(tmp_path, ["mostly"]))


def test_skeptic_stats_counts_failed_checks() -> None:
    kept = SkepticReview.model_validate(REVIEW)
    failed = [{**c, "result": "fail"} if c["name"] in ("seasonality", "templating") else c
              for c in REVIEW["checks"]]
    rejected = SkepticReview.model_validate({**REVIEW, "verdict": "rejected", "checks": failed})
    stats = evaluate.skeptic_stats([kept, rejected, rejected])
    assert (stats.kept, stats.rejected) == (1, 2)
    assert stats.failed_checks == {"templating": 2, "seasonality": 2}


def theme(label: str, ids: list[str]) -> ThemeOut:
    return ThemeOut(label=label, description="d", complaint_ids=ids)


def test_identical_runs_are_fully_stable() -> None:
    run = [theme("Refusal to honor ACH revocation", ["1", "2"]), theme("Fees after payoff", ["3", "4"])]
    result = evaluate.stability("c", "m", run, run)
    assert result.label_overlap == 1.0 and result.pair_agreement == 1.0


def test_relabelled_but_same_grouping() -> None:
    first = [theme("Refusal to honor ACH revocation", ["1", "2"]), theme("Fees after payoff", ["3", "4"])]
    second = [theme("Lenders ignore ACH revocation", ["1", "2"]), theme("Charges after loan payoff", ["3", "4"])]
    result = evaluate.stability("c", "m", first, second)
    assert 0 < result.label_overlap < 1
    assert result.pair_agreement == 1.0


def test_regrouping_lowers_pair_agreement() -> None:
    first = [theme("a", ["1", "2"]), theme("b", ["3", "4"])]
    second = [theme("a", ["1", "3"]), theme("b", ["2", "4"])]
    assert evaluate.pair_agreement(first, second) < 1.0
