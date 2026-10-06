"""Per-company view of the radar: lift and velocity against peers. No AI.

For each selected company and radar month, every cluster where the company has at
least MIN_COMPLAINTS complaints in the recent window gets:
- lift: the company's share of the cluster divided by its share of the cluster's
  product, the same definition emergence uses;
- company velocity: the emergence velocity formula over the company's own counts;
- peer velocity: the same formula over everyone else in the cluster.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from radar.emergence import SMOOTHING
from radar.schemas import CompanyListItem, EmergenceResult, LensCluster, LensFile
from radar.taxonomy import cluster_id, slugify

TOP_BY_VOLUME = 15
MIN_COMPLAINTS = 10
# A company that leads a briefed cluster by lift is added to the picker when it has at
# least this many recent complaints there, so the companies a brief names can be lensed.
MIN_LEADER_COMPLAINTS = 20


def monthly_counts(df: pd.DataFrame) -> pd.Series:
    """Complaints per (month, company, product, issue); computed once for every month."""
    return df.groupby(["month", "company", "product", "issue"], observed=True).size()


def _window(counts: pd.Series, months: Iterable[str]) -> pd.Series:
    wanted = counts[counts.index.get_level_values("month").isin(list(months))]
    return wanted.groupby(level=["company", "product", "issue"], observed=True).sum()


def _velocity(recent_total: float, baseline_total: float, recent_n: int, baseline_n: int) -> float:
    return (recent_total / recent_n + SMOOTHING) / (baseline_total / baseline_n + SMOOTHING)


def pick_companies(
    counts: pd.Series, analysis: EmergenceResult, briefed: set[str]
) -> list[CompanyListItem]:
    """The TOP_BY_VOLUME companies by recent complaints, plus briefed-cluster leaders."""
    recent = _window(counts, analysis.recent_months).groupby(level="company").sum()
    by_volume = recent.sort_values(ascending=False).head(TOP_BY_VOLUME)
    chosen = {str(name): "most complaints" for name in by_volume.index}
    leaders = [
        max(c.top_companies, key=lambda t: t.lift)
        for c in analysis.clusters
        if c.id in briefed and c.top_companies
    ]
    for leader in leaders:
        if leader.count >= MIN_LEADER_COMPLAINTS and leader.name not in chosen:
            chosen[leader.name] = "leads a briefed cluster by lift"
    return [
        CompanyListItem(name=name, slug=slugify(name), complaints=int(recent.get(name, 0)),
                        reason=reason)
        for name, reason in chosen.items()
    ]


def lens_clusters(counts: pd.Series, result: EmergenceResult, company: str) -> list[LensCluster]:
    """The company's clusters in one month, highest lift first."""
    recent = _window(counts, result.recent_months)
    baseline = _window(counts, result.baseline_months)
    if company not in recent.index.get_level_values("company"):
        return []
    mine_recent = recent.xs(company, level="company")
    mine_baseline = (
        baseline.xs(company, level="company")
        if company in baseline.index.get_level_values("company") else pd.Series(dtype="int64")
    )
    cluster_recent = recent.groupby(level=["product", "issue"]).sum()
    cluster_baseline = baseline.groupby(level=["product", "issue"]).sum()
    product_total = cluster_recent.groupby(level="product").sum()
    mine_product = mine_recent.groupby(level="product").sum()
    n_recent, n_base = len(result.recent_months), max(1, len(result.baseline_months))

    rows = []
    for c in result.clusters:
        key = (c.product, c.issue)
        mine = int(mine_recent.get(key, 0))
        if mine < MIN_COMPLAINTS:
            continue
        mine_base = int(mine_baseline.get(key, 0))
        total, total_base = int(cluster_recent[key]), int(cluster_baseline.get(key, 0))
        share_of_product = mine_product[c.product] / product_total[c.product]
        rows.append(LensCluster(
            id=cluster_id(c.product, c.issue),
            product=c.product,
            issue=c.issue,
            product_family=c.product_family,
            complaints=mine,
            lift=round((mine / total) / share_of_product, 3),
            company_velocity=round(_velocity(mine, mine_base, n_recent, n_base), 4),
            peer_velocity=round(_velocity(total - mine, total_base - mine_base, n_recent, n_base), 4),
        ))
    return sorted(rows, key=lambda r: r.lift, reverse=True)


def build(
    counts: pd.Series, results: list[EmergenceResult], companies: list[CompanyListItem]
) -> dict[str, LensFile]:
    """One lens file per company, keyed by slug, covering every radar month."""
    return {
        item.slug: LensFile(
            company=item.name,
            slug=item.slug,
            months={r.month: lens_clusters(counts, r, item.name) for r in results},
        )
        for item in companies
    }
