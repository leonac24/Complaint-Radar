"""Statistical acceleration detection over (product, issue) clusters. No AI."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from radar.ingest import complete_months
from radar.schemas import ClusterStats, EmergenceResult, MonthCount, TopCompany
from radar.taxonomy import cluster_id, product_family

SMOOTHING = 5.0
RECENT_MONTHS = 3
BASELINE_MONTHS = 6
MIN_RECENT_AVG = 30.0
TOP_COMPANIES = 10


def velocity(recent: Sequence[float], baseline: Sequence[float]) -> float:
    """(mean of recent + 5) / (mean of baseline + 5)."""
    recent_mean = sum(recent) / len(recent)
    baseline_mean = sum(baseline) / len(baseline)
    return (recent_mean + SMOOTHING) / (baseline_mean + SMOOTHING)


def filter_as_of(df: pd.DataFrame, as_of: str | None) -> pd.DataFrame:
    """Drop everything received after the as-of month."""
    if as_of is None:
        return df
    return df[df["month"] <= as_of]


def lift(company_count: int, cluster_total: int, company_share_overall: float) -> float:
    """Company share of the cluster divided by its share of all complaints."""
    if cluster_total == 0 or company_share_overall == 0:
        return 0.0
    return (company_count / cluster_total) / company_share_overall


def split_window(months: list[str], month: str) -> tuple[list[str], list[str]]:
    """Return (recent, baseline) month lists ending at `month`."""
    if month not in months:
        raise ValueError(f"{month} is not a complete month in the data ({months[0]}..{months[-1]})")
    idx = months.index(month)
    if idx < RECENT_MONTHS:
        raise ValueError(f"{month} needs at least {RECENT_MONTHS + 1} complete months of history")
    recent = months[idx - RECENT_MONTHS + 1 : idx + 1]
    baseline = months[max(0, idx - RECENT_MONTHS - BASELINE_MONTHS + 1) : idx - RECENT_MONTHS + 1]
    return recent, baseline


def compute(
    df: pd.DataFrame,
    month: str | None = None,
    as_of: str | None = None,
    min_recent_avg: float = MIN_RECENT_AVG,
) -> EmergenceResult:
    data = filter_as_of(df, as_of)
    months = complete_months(data)
    if not months:
        raise ValueError("no complete months in the data; run `ingest` first")
    target = month or as_of or months[-1]
    recent, baseline = split_window(months, target)
    window = months[: months.index(target) + 1]

    in_window = data[data["month"].isin(window)]
    counts = (
        in_window.groupby(["product", "issue", "month"]).size().unstack("month", fill_value=0)
    ).reindex(columns=window, fill_value=0)
    recent_avg = counts[recent].mean(axis=1)
    baseline_avg = counts[baseline].mean(axis=1)
    speed = (recent_avg + SMOOTHING) / (baseline_avg + SMOOTHING)

    keep = recent_avg[recent_avg >= min_recent_avg].index
    ranked = (
        pd.DataFrame({"velocity": speed[keep], "recent": recent_avg[keep]})
        .sort_values(["velocity", "recent"], ascending=False)
        .index
    )

    recent_rows = data[data["month"].isin(recent)]
    overall_share = recent_rows["company"].value_counts(normalize=True)
    by_cluster = dict(list(recent_rows.groupby(["product", "issue"])))

    clusters = [
        _cluster_stats(
            rank=i + 1,
            key=key,
            rows=by_cluster[key],
            series=counts.loc[key],
            velocity_value=float(speed[key]),
            recent_value=float(recent_avg[key]),
            baseline_value=float(baseline_avg[key]),
            baseline_len=len(baseline),
            overall_share=overall_share,
        )
        for i, key in enumerate(ranked)
    ]
    return EmergenceResult(
        month=target,
        as_of=as_of,
        recent_months=recent,
        baseline_months=baseline,
        window_months=window,
        total_recent_complaints=len(recent_rows),
        clusters=clusters,
    )


def _cluster_stats(
    *,
    rank: int,
    key: tuple[str, str],
    rows: pd.DataFrame,
    series: pd.Series,
    velocity_value: float,
    recent_value: float,
    baseline_value: float,
    baseline_len: int,
    overall_share: pd.Series,
) -> ClusterStats:
    product, issue = key
    company_counts = rows["company"].value_counts().head(TOP_COMPANIES)
    states = rows.loc[rows["state"].ne(""), "state"].value_counts()
    return ClusterStats(
        id=cluster_id(product, issue),
        product=product,
        issue=issue,
        product_family=product_family(product),
        rank=rank,
        velocity=round(velocity_value, 4),
        recent_monthly_avg=round(recent_value, 2),
        baseline_monthly_avg=round(baseline_value, 2),
        baseline_months=baseline_len,
        narrative_count=int(rows["narrative"].ne("").sum()),
        months=[MonthCount(month=m, count=int(c)) for m, c in series.items()],
        states={str(s): int(c) for s, c in states.items()},
        top_companies=[
            TopCompany(
                name=str(name),
                count=int(count),
                lift=round(lift(int(count), len(rows), float(overall_share[name])), 3),
            )
            for name, count in company_counts.items()
        ],
    )
