"""The evidence package both agents see. Every number here comes from the pipeline."""

from __future__ import annotations

import json
from typing import Any

from radar.schemas import ClusterStats, EmergenceResult, Extraction, ThemeOut

MAX_SUMMARIES = 15
TOP_STATES = 8


def severity_mean(extractions: list[Extraction]) -> float | None:
    return round(sum(e.severity for e in extractions) / len(extractions), 2) if extractions else None


def vulnerable_share(extractions: list[Extraction]) -> float | None:
    if not extractions:
        return None
    return round(sum(e.vulnerable_consumer for e in extractions) / len(extractions), 3)


def build(
    cluster: ClusterStats,
    emergence: EmergenceResult,
    templated_share: float | None,
    themes: list[ThemeOut] | None,
    extractions: dict[str, Extraction],
) -> dict[str, Any]:
    sampled = list(extractions.values())
    total_states = sum(cluster.states.values())
    themed = sum(len(t.complaint_ids) for t in themes or [])
    return {
        "cluster": f"{cluster.product} / {cluster.issue}",
        "analysis_month": emergence.month,
        "recent_months": emergence.recent_months,
        "baseline_months": emergence.baseline_months,
        "velocity": cluster.velocity,
        "velocity_rank": f"{cluster.rank} of {len(emergence.clusters)}",
        "recent_monthly_avg": cluster.recent_monthly_avg,
        "baseline_monthly_avg": cluster.baseline_monthly_avg,
        "monthly_counts": {m.month: m.count for m in cluster.months},
        "narratives_in_recent_months": cluster.narrative_count,
        "templated_share_of_recent_narratives": templated_share,
        "top_companies": [
            {"name": c.name, "complaints": c.count, "lift": c.lift} for c in cluster.top_companies
        ],
        "top_states_share": {
            s: round(n / total_states, 3) for s, n in list(cluster.states.items())[:TOP_STATES]
        } if total_states else {},
        "ai_sample_size": len(sampled),
        "ai_mean_severity_1_to_5": severity_mean(sampled),
        "ai_vulnerable_consumer_share": vulnerable_share(sampled),
        "ai_themes": [
            {"label": t.label, "description": t.description,
             "share_of_sample": round(len(t.complaint_ids) / themed, 3) if themed else 0}
            for t in themes or []
        ],
        "ai_sample_summaries": [
            {"complaint_id": cid, "summary": e.summary, "root_cause": e.root_cause}
            for cid, e in list(extractions.items())[:MAX_SUMMARIES]
        ],
    }


def render(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, indent=1)
