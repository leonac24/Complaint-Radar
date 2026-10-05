from __future__ import annotations

import pandas as pd
import pytest

from radar import emergence
from radar.taxonomy import cluster_id, product_family
from tests import fixtures


def test_velocity_formula() -> None:
    assert emergence.velocity([30, 30, 30], [10] * 6) == pytest.approx(35 / 15)
    assert emergence.velocity([0, 0, 0], [0] * 6) == 1.0


def test_lift() -> None:
    # 50% of the cluster but 10% of all complaints -> 5x overrepresented.
    assert emergence.lift(50, 100, 0.10) == pytest.approx(5.0)
    assert emergence.lift(0, 0, 0.1) == 0.0


def test_split_window() -> None:
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    recent, baseline = emergence.split_window(months, "2025-12")
    assert recent == ["2025-10", "2025-11", "2025-12"]
    assert baseline == ["2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09"]
    recent, baseline = emergence.split_window(months, "2025-05")
    assert baseline == ["2025-01", "2025-02"]
    with pytest.raises(ValueError):
        emergence.split_window(months, "2025-03")


def test_accelerating_cluster_ranks_first(complaints: pd.DataFrame) -> None:
    result = emergence.compute(complaints)
    assert result.month == "2026-07"
    top = result.clusters[0]
    assert (top.product, top.issue) == fixtures.ACCELERATING
    assert top.velocity > 3
    assert top.product_family == "payments"


def test_accelerating_cluster_lift_flags_small_company(complaints: pd.DataFrame) -> None:
    top = emergence.compute(complaints).clusters[0]
    leader = top.top_companies[0]
    assert leader.name == fixtures.ACCEL_COMPANY
    assert leader.lift > 2


def test_volume_floor_drops_small_clusters(complaints: pd.DataFrame) -> None:
    ids = {c.id for c in emergence.compute(complaints).clusters}
    assert cluster_id("Vehicle loan or lease", "Struggling to pay your loan") not in ids


def test_monthly_series_matches_raw_counts(complaints: pd.DataFrame) -> None:
    result = emergence.compute(complaints)
    top = result.clusters[0]
    product, issue = fixtures.ACCELERATING
    raw = complaints[(complaints["product"] == product) & (complaints["issue"] == issue)]
    expected = raw.groupby("month").size()
    assert {m.month: m.count for m in top.months} == {m: int(expected[m]) for m in result.window_months}


def test_as_of_ignores_later_data(complaints: pd.DataFrame) -> None:
    early = emergence.compute(complaints, as_of="2026-02")
    assert early.month == "2026-02"
    assert early.window_months[-1] == "2026-02"
    accel = next(c for c in early.clusters if (c.product, c.issue) == fixtures.ACCELERATING)
    assert accel.velocity < 1.5
    assert all(m.month <= "2026-02" for m in accel.months)


def test_as_of_matches_truncated_input(complaints: pd.DataFrame) -> None:
    truncated = complaints[complaints["month"] <= "2026-04"]
    assert emergence.compute(complaints, as_of="2026-04") == emergence.compute(truncated, as_of="2026-04")


def test_product_family_mapping() -> None:
    assert product_family("Checking or savings account") == "banking"
    assert product_family("Credit card or prepaid card") == "cards"
    assert product_family("Prepaid card") == "payments"
    assert product_family("Credit reporting, credit repair services, or other personal consumer reports") == "credit_reporting"
    assert product_family("Payday loan, title loan, or personal loan") == "lending"
    assert product_family("Debt or credit management") == "other"
