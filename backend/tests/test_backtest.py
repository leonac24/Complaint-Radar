from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from radar import backtest, emergence
from radar.schemas import BacktestCase, Extraction
from radar.taxonomy import cluster_label
from tests import fixtures
from tests.fakes import REVIEW, FakeLLM

MODELS = ("fast", "writer", "reasoning")
ACCEL = cluster_label(*fixtures.ACCELERATING)


def case(cluster: str, as_of: str = "2026-06") -> BacktestCase:
    return BacktestCase(name="t", public_date="2026-08-01", as_of=as_of, cluster=cluster,
                        source_url="https://example.org")


def run(c: BacktestCase, complaints: pd.DataFrame, llm: FakeLLM | None = None):
    saved: dict[str, Extraction] = {}
    result = backtest.run_case(c, complaints, llm or FakeLLM(), MODELS, {},
                               lambda fresh, model: saved.update(fresh))
    return result, saved


def test_accelerating_cluster_is_flagged_as_of_june(complaints: pd.DataFrame) -> None:
    llm = FakeLLM()
    result, saved = run(case(ACCEL), complaints, llm)
    assert result.found and result.rank == 1 and result.flagged
    assert result.verdict == "kept"
    assert "flagged" in result.outcome
    assert saved  # extractions were handed back to be cached
    assert result.target_id in {b.id for b in result.scope}


def test_replay_never_sees_later_data(complaints: pd.DataFrame) -> None:
    _, saved = run(case(ACCEL, as_of="2026-05"), complaints)
    month_of = complaints.set_index("complaint_id")["month"]
    assert saved
    assert (month_of.loc[list(saved)] <= "2026-05").all()


def test_rejected_brief_is_a_miss(complaints: pd.DataFrame) -> None:
    rejected = {**REVIEW, "checks": [{**REVIEW["checks"][0], "result": "fail"}, *REVIEW["checks"][1:]]}

    def respond(call):
        from tests.fakes import default
        return rejected if call.output.__name__ == "SkepticReview" else default(call)

    result, _ = run(case(ACCEL), complaints, FakeLLM(responder=respond))
    assert not result.flagged and result.verdict == "rejected"
    assert "rejected" in result.outcome


def test_unknown_cluster_is_reported_without_spending(complaints: pd.DataFrame) -> None:
    llm = FakeLLM()
    result, _ = run(case("No such product / No such issue"), complaints, llm)
    assert not result.found and result.rank is None and not result.flagged
    assert "below the volume floor" in result.outcome
    assert llm.calls == []


def test_outside_briefed_cut_is_a_miss(complaints: pd.DataFrame, monkeypatch) -> None:
    monkeypatch.setattr(backtest, "BRIEFED", 0)
    llm = FakeLLM()
    result, _ = run(case(ACCEL), complaints, llm)
    assert result.rank == 1 and not result.flagged
    assert "outside the top 0" in result.outcome
    assert llm.calls == []


def test_shipped_cases_are_complete_and_sourced() -> None:
    for c in backtest.load_cases():
        assert c.source_url.startswith("https://")
        assert c.as_of < c.public_date[:7]  # the replay only sees data before the event
        assert " / " in c.cluster


def test_load_cases_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(f'- name: a\n  public_date: "2026-08-01"\n  as_of: "2026-06"\n'
                    f'  cluster: "{ACCEL}"\n  source_url: "https://example.org"\n')
    assert backtest.load_cases(path)[0].as_of == "2026-06"


def test_planned_calls_counts_uncached_work(complaints: pd.DataFrame) -> None:
    calls = backtest.planned_calls(case(ACCEL), complaints, {})
    assert calls == backtest.PER_CLUSTER + 2
    result = emergence.compute(complaints, as_of="2026-06")
    assert backtest.find_cluster(result, ACCEL.upper()) is not None
