"""As-of replay: would the radar have flagged a cluster before a public event?

For each case the radar reruns with only data up to `as_of`: emergence, extract (cached
by complaint ID), analyst, and skeptic. A case counts as flagged only when the cluster
ranks inside the briefed top clusters and the skeptic keeps its brief. Misses are
reported the same way as hits. Cases live in backtest_cases.yaml and are chosen and
verified by a person, never by this code.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import yaml

from radar import emergence, extract, templating
from radar.agents import analyst, evidence, skeptic
from radar.llm import LLM
from radar.schemas import (
    BacktestCase,
    BacktestResult,
    ClusterStats,
    EmergenceResult,
    Extraction,
    MiniBlip,
    ModelIds,
)
from radar.taxonomy import cluster_label

CASES_PATH = Path(__file__).with_name("backtest_cases.yaml")
BRIEFED = 25  # the pipeline writes briefs for this many clusters per month
PER_CLUSTER = 40


def load_cases(path: Path = CASES_PATH) -> list[BacktestCase]:
    raw = yaml.safe_load(path.read_text()) if path.exists() else None
    return [BacktestCase.model_validate(item) for item in raw or []]


def find_cluster(result: EmergenceResult, label: str) -> ClusterStats | None:
    wanted = label.strip().lower()
    return next(
        (c for c in result.clusters if cluster_label(c.product, c.issue).lower() == wanted), None
    )


def mini_scope(result: EmergenceResult) -> list[MiniBlip]:
    return [
        MiniBlip(id=c.id, product_family=c.product_family, velocity=c.velocity,
                 recent_monthly_avg=c.recent_monthly_avg)
        for c in result.clusters
    ]


def describe(result: BacktestResult) -> str:
    """One plain sentence stating what happened, hit or miss."""
    month = result.as_of
    if result.rank is None:
        return f"Not on the radar as of {month}: the cluster was below the volume floor."
    place = f"Ranked {result.rank} of {result.clusters_ranked} by velocity as of {month}"
    if result.rank > BRIEFED:
        return f"{place}, outside the top {BRIEFED} that get briefs, so it was not flagged."
    if result.verdict == "kept":
        return f"{place}; the skeptic kept the brief, so it was flagged."
    if result.verdict == "rejected":
        return f"{place}, but the skeptic rejected the brief, so it was not flagged."
    return f"{place}; no brief could be written (no narratives in the window)."


def run_case(
    case: BacktestCase,
    df: pd.DataFrame,
    llm: LLM,
    models: ModelIds,
    cache: dict[str, Extraction],
    save_extractions: Callable[[dict[str, Extraction], str], None],
) -> BacktestResult:
    """Replay one case with only data up to its as_of month."""
    data = emergence.filter_as_of(df, case.as_of)
    result = emergence.compute(data, as_of=case.as_of)
    target = find_cluster(result, case.cluster)
    base = BacktestResult(
        **case.model_dump(),
        found=target is not None,
        rank=target.rank if target else None,
        clusters_ranked=len(result.clusters),
        velocity=target.velocity if target else None,
        scope=mini_scope(result),
        target_id=target.id if target else None,
    )
    if target is None or target.rank > BRIEFED:
        return base.model_copy(update={"outcome": describe(base)})

    narrowed = result.model_copy(update={"clusters": [target]})
    sampled = extract.sample(data, narrowed, 1, PER_CLUSTER)
    work = extract.plan(sampled, cache, None)
    fresh, _failed = extract.run(llm, models.fast, work.to_call, use_batch=False)
    save_extractions(fresh, models.fast)
    known = {**cache, **fresh}
    items = {s.complaint_id: known[s.complaint_id] for s in sampled if s.complaint_id in known}
    if not items:
        return base.model_copy(update={"outcome": describe(base)})

    shares = templating.templated_shares(templating.mark_templated(data), narrowed)
    package = evidence.build(target, result, shares.get(target.id), None, items)
    brief = analyst.write_brief(llm, models.writer, package)
    review = skeptic.review_brief(llm, models.reasoning, brief, package)
    done = base.model_copy(update={
        "headline": brief.headline, "verdict": review.verdict, "note": review.note,
        "flagged": review.verdict == "kept",
    })
    return done.model_copy(update={"outcome": describe(done)})


def planned_calls(case: BacktestCase, df: pd.DataFrame, cache: dict[str, Extraction]) -> int:
    """API calls a case would make: uncached extractions plus analyst and skeptic."""
    data = emergence.filter_as_of(df, case.as_of)
    result = emergence.compute(data, as_of=case.as_of)
    target = find_cluster(result, case.cluster)
    if target is None or target.rank > BRIEFED:
        return 0
    narrowed = result.model_copy(update={"clusters": [target]})
    sampled = extract.sample(data, narrowed, 1, PER_CLUSTER)
    return len(extract.plan(sampled, cache, None).to_call) + 2
