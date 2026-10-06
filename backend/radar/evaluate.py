"""Honest evaluation of the AI layer.

- Extraction: a person rates 50 random extractions against their narratives in a CSV
  review sheet (accurate, partially, wrong); this module scores the filled sheet.
- Skeptic: kept and rejected counts and the most common failed checks.
- Stability: themes run twice on the same cluster; overlap of the two runs.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd

from radar.schemas import (
    Extraction,
    ExtractionScore,
    SkepticReview,
    SkepticStats,
    StabilityResult,
    ThemeOut,
)

SHEET_SIZE = 50
SEED = 7
RATINGS = ("accurate", "partially", "wrong")
SHEET_NARRATIVE_CHARS = 4000
SHEET_FIELDS = [
    "complaint_id", "product", "issue", "narrative", "summary", "root_cause",
    "root_cause_family", "journey_stage", "harm", "money_at_stake_usd", "severity",
    "vulnerable_consumer", "looks_templated", "rating", "notes",
]


# ---------- extraction review sheet ----------


def review_rows(df: pd.DataFrame, cache: dict[str, Extraction], size: int = SHEET_SIZE) -> list[dict]:
    """A seeded random sample of cached extractions, each next to its narrative."""
    narratives = df.loc[df["complaint_id"].isin(list(cache)) & df["narrative"].ne(""),
                        ["complaint_id", "product", "issue", "narrative"]]
    chosen = narratives.sample(min(size, len(narratives)), random_state=SEED)
    return [
        {
            "complaint_id": r.complaint_id,
            "product": r.product,
            "issue": r.issue,
            "narrative": r.narrative[:SHEET_NARRATIVE_CHARS],
            **{k: v for k, v in cache[r.complaint_id].model_dump().items()},
            "rating": "",
            "notes": "",
        }
        for r in chosen.itertuples(index=False)
    ]


def write_sheet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHEET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def score_sheet(path: Path) -> ExtractionScore:
    """Score a review sheet. Unrated rows are counted but not scored."""
    with path.open(newline="") as fh:
        ratings = [row.get("rating", "").strip().lower() for row in csv.DictReader(fh)]
    unknown = sorted({r for r in ratings if r and r not in RATINGS})
    if unknown:
        raise ValueError(f"unknown ratings {unknown}; use one of {', '.join(RATINGS)}")
    counts = Counter(r for r in ratings if r)
    rated = sum(counts.values())
    return ExtractionScore(
        total=len(ratings),
        rated=rated,
        accurate=counts["accurate"],
        partially=counts["partially"],
        wrong=counts["wrong"],
        accuracy=round(counts["accurate"] / rated, 3) if rated else None,
        accurate_or_partial=round((counts["accurate"] + counts["partially"]) / rated, 3) if rated else None,
    )


# ---------- skeptic ----------


def skeptic_stats(reviews: list[SkepticReview]) -> SkepticStats:
    fails = Counter(c.name for r in reviews for c in r.checks if c.result == "fail")
    return SkepticStats(
        kept=sum(r.verdict == "kept" for r in reviews),
        rejected=sum(r.verdict == "rejected" for r in reviews),
        failed_checks=dict(fails.most_common()),
    )


# ---------- theme stability ----------


def _words(label: str) -> set[str]:
    return set(re.findall(r"[a-z]+", label.lower())) - {"and", "or", "of", "the", "a", "to", "for", "in", "on"}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def label_overlap(first: list[ThemeOut], second: list[ThemeOut]) -> float:
    """Mean best word-overlap (Jaccard) of each label with the other run's labels, both ways."""
    def one_way(xs: list[ThemeOut], ys: list[ThemeOut]) -> list[float]:
        return [max((_jaccard(_words(x.label), _words(y.label)) for y in ys), default=0.0) for x in xs]

    scores = one_way(first, second) + one_way(second, first)
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def pair_agreement(first: list[ThemeOut], second: list[ThemeOut]) -> float:
    """Share of complaint pairs, among complaints both runs themed, that the runs agree
    on (same theme in both, or different themes in both)."""
    def assignment(themes: list[ThemeOut]) -> dict[str, int]:
        return {cid: i for i, t in enumerate(themes) for cid in t.complaint_ids}

    a, b = assignment(first), assignment(second)
    shared = sorted(set(a) & set(b))
    pairs = list(combinations(shared, 2))
    agree = sum((a[x] == a[y]) == (b[x] == b[y]) for x, y in pairs)
    return round(agree / len(pairs), 3) if pairs else 0.0


def stability(cluster: str, model: str, first: list[ThemeOut], second: list[ThemeOut]) -> StabilityResult:
    return StabilityResult(
        cluster=cluster,
        model=model,
        first_labels=[t.label for t in first],
        second_labels=[t.label for t in second],
        label_overlap=label_overlap(first, second),
        pair_agreement=pair_agreement(first, second),
    )
