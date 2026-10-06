from __future__ import annotations

import pandas as pd
import pytest

from radar import emergence, lens
from radar.taxonomy import cluster_id
from tests import fixtures


@pytest.fixture(scope="module")
def counts(complaints: pd.DataFrame) -> pd.Series:
    return lens.monthly_counts(complaints)


def test_planted_company_is_overrepresented_and_faster_than_peers(counts, analysis) -> None:
    rows = lens.lens_clusters(counts, analysis, fixtures.ACCEL_COMPANY)
    accel = next(r for r in rows if r.id == cluster_id(*fixtures.ACCELERATING))
    assert accel.lift > 2
    assert accel.company_velocity > accel.peer_velocity
    assert rows[0].id == accel.id  # sorted by lift


def test_lens_lift_matches_emergence_lift(counts, analysis) -> None:
    top = analysis.clusters[0]
    leader = top.top_companies[0]
    row = next(r for r in lens.lens_clusters(counts, analysis, leader.name) if r.id == top.id)
    assert row.lift == pytest.approx(leader.lift, abs=0.01)
    assert row.complaints == leader.count


def test_small_presences_are_left_out(counts, analysis) -> None:
    rows = lens.lens_clusters(counts, analysis, fixtures.ACCEL_COMPANY)
    assert all(r.complaints >= lens.MIN_COMPLAINTS for r in rows)
    assert lens.lens_clusters(counts, analysis, "Nobody At All LLC") == []


def test_picker_adds_leaders_of_briefed_clusters(counts, analysis) -> None:
    top = analysis.clusters[0]
    plain = lens.pick_companies(counts, analysis, briefed=set())
    with_leaders = lens.pick_companies(counts, analysis, briefed={top.id})
    assert len(plain) <= lens.TOP_BY_VOLUME
    names = {c.name: c.reason for c in with_leaders}
    assert fixtures.ACCEL_COMPANY in names


def test_build_covers_every_month(counts, analysis, complaints) -> None:
    earlier = emergence.compute(complaints, month="2026-04")
    companies = lens.pick_companies(counts, analysis, briefed=set())
    files = lens.build(counts, [earlier, analysis], companies)
    assert set(files) == {c.slug for c in companies}
    assert all(set(f.months) == {"2026-04", analysis.month} for f in files.values())
