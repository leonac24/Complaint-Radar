"""Writes the static JSON the frontend serves from public_data/.

Every number comes from data/work/. AI fields (themes, severity, brief, skeptic) exist
only for the analysis month the AI steps ran on; other months carry statistics only
and leave those fields null rather than borrowing the analysis month's output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from radar import emergence, templating
from radar.agents.evidence import severity_mean, vulnerable_share
from radar.ingest import complete_months
from radar.schemas import (
    Brief,
    BriefSummary,
    ClusterDetail,
    ClusterStats,
    EmergenceResult,
    ExampleSummary,
    Extraction,
    Meta,
    ModelIds,
    RadarCluster,
    RadarFile,
    SkepticReview,
    SkepticSummary,
    ThemeDetail,
    ThemeOut,
    ThemeShare,
)

SOURCE = "CFPB Consumer Complaint Database narratives archive"
SOURCE_URL = (
    "https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/"
    "cfpb-consumer-complaint-database-narratives-archive/"
)
CLUSTER_EXAMPLES = 5
THEME_EXAMPLES = 3
SIZE_LIMIT_BYTES = 20 * 1024 * 1024
# Written by later steps (lens, backtest, evaluate); listed in meta when present.
OPTIONAL_FILES = {"companies": "companies.json", "backtests": "backtests.json",
                  "evaluation": "evaluation.json"}
GENERATED_PATTERNS = ("radar_*.json", "cluster_*.json")


@dataclass(frozen=True)
class AIOutputs:
    """Outputs of the AI steps for the analysis month, keyed by cluster id."""

    themes: dict[str, list[ThemeOut]] = field(default_factory=dict)
    briefs: dict[str, Brief] = field(default_factory=dict)
    reviews: dict[str, SkepticReview] = field(default_factory=dict)
    # cluster id -> {complaint id: extraction}, in sample order
    samples: dict[str, dict[str, Extraction]] = field(default_factory=dict)


NO_AI = AIOutputs()


def radar_months(df: pd.DataFrame) -> list[str]:
    """Complete months with enough history before them to compute velocity."""
    return complete_months(df)[emergence.RECENT_MONTHS:]


def _shares(themes: list[ThemeOut]) -> list[float]:
    themed = sum(len(t.complaint_ids) for t in themes)
    return [round(len(t.complaint_ids) / themed, 3) if themed else 0.0 for t in themes]


def _examples(ids: list[str], sample: dict[str, Extraction], limit: int) -> list[ExampleSummary]:
    found = [cid for cid in ids if cid in sample][:limit]
    return [ExampleSummary(complaint_id=cid, summary=sample[cid].summary) for cid in found]


def _common(c: ClusterStats, templated: float | None, ai: AIOutputs) -> dict:
    sample = list(ai.samples.get(c.id, {}).values())
    return {
        "id": c.id,
        "product": c.product,
        "issue": c.issue,
        "product_family": c.product_family,
        "velocity": c.velocity,
        "recent_monthly_avg": c.recent_monthly_avg,
        "baseline_monthly_avg": c.baseline_monthly_avg,
        "severity": severity_mean(sample),
        "templated_share": templated,
        "vulnerable_share": vulnerable_share(sample),
        "narrative_count": c.narrative_count,
        "top_companies": c.top_companies,
        "states": c.states,
        "months": c.months,
    }


def radar_cluster(c: ClusterStats, templated: float | None, ai: AIOutputs) -> RadarCluster:
    themes = ai.themes.get(c.id, [])
    brief = ai.briefs.get(c.id)
    review = ai.reviews.get(c.id)
    return RadarCluster(
        **_common(c, templated, ai),
        themes=[ThemeShare(label=t.label, description=t.description, share=s)
                for t, s in zip(themes, _shares(themes), strict=True)],
        brief=BriefSummary(headline=brief.headline, confidence=brief.confidence) if brief else None,
        skeptic=SkepticSummary(verdict=review.verdict, note=review.note) if review else None,
    )


def cluster_detail(c: ClusterStats, month: str, templated: float | None,
                   ai: AIOutputs) -> ClusterDetail:
    themes = ai.themes.get(c.id, [])
    sample = ai.samples.get(c.id, {})
    return ClusterDetail(
        **_common(c, templated, ai),
        month=month,
        themes=[
            ThemeDetail(label=t.label, description=t.description, share=s,
                        complaint_ids=t.complaint_ids,
                        examples=_examples(t.complaint_ids, sample, THEME_EXAMPLES))
            for t, s in zip(themes, _shares(themes), strict=True)
        ],
        brief=ai.briefs.get(c.id),
        skeptic=ai.reviews.get(c.id),
        examples=_examples(list(sample), sample, CLUSTER_EXAMPLES),
    )


def radar_file(result: EmergenceResult, templated: dict[str, float], ai: AIOutputs) -> RadarFile:
    return RadarFile(
        month=result.month,
        clusters=[radar_cluster(c, templated.get(c.id), ai) for c in result.clusters],
    )


def build(
    df: pd.DataFrame,
    marked: pd.DataFrame,
    analysis: EmergenceResult,
    analysis_templated: dict[str, float],
    ai: AIOutputs,
    models: ModelIds,
    available: list[str],
) -> dict[str, BaseModel]:
    """Every public file, keyed by file name. Pure: reads nothing from disk."""
    months = radar_months(df)
    files: dict[str, BaseModel] = {}
    for month in months:
        is_analysis = month == analysis.month
        result = analysis if is_analysis else emergence.compute(df, month=month)
        shares = analysis_templated if is_analysis else templating.templated_shares(marked, result)
        files[f"radar_{month}.json"] = radar_file(result, shares, ai if is_analysis else NO_AI)
    for c in analysis.clusters:
        files[f"cluster_{c.id}.json"] = cluster_detail(
            c, analysis.month, analysis_templated.get(c.id), ai
        )
    window = complete_months(df)
    files["meta.json"] = Meta(
        source=SOURCE,
        source_url=SOURCE_URL,
        window_start=window[0],
        window_end=window[-1],
        radar_months=months,
        analysis_month=analysis.month,
        total_complaints=len(df),
        clusters_with_briefs=len(ai.briefs),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        models=models,
        available=available,
    )
    return files


def available_optional(public_dir: Path) -> list[str]:
    return [name for name, file in OPTIONAL_FILES.items() if (public_dir / file).exists()]


def write(public_dir: Path, files: dict[str, BaseModel]) -> int:
    """Replace generated files in public_dir and return the total bytes written.

    Old radar and cluster files are removed first so a cluster that dropped out of the
    analysis does not linger. Files from later steps (lens, backtests) are left alone.
    """
    public_dir.mkdir(parents=True, exist_ok=True)
    stale = [p for pattern in GENERATED_PATTERNS for p in public_dir.glob(pattern)]
    for path in stale:
        path.unlink()
    sizes = [_write_one(public_dir / name, model) for name, model in files.items()]
    return sum(sizes)


def _write_one(path: Path, model: BaseModel) -> int:
    text = json.dumps(model.model_dump(mode="json"), separators=(",", ":"))
    path.write_text(text)
    return len(text.encode("utf-8"))
