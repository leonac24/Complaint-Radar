"""Copy-paste / form-letter detection by narrative fingerprint. No AI."""

from __future__ import annotations

import hashlib
import re

import pandas as pd

from radar.schemas import EmergenceResult
from radar.taxonomy import cluster_id

FINGERPRINT_CHARS = 400
MIN_REPEATS = 5

_REDACTION = re.compile(r"x{2,}")
_NON_LETTER = re.compile(r"[^a-z]+")


def normalize_text(text: str) -> str:
    """Lowercase, drop XX.. redactions, keep letters only, collapse whitespace."""
    lowered = _REDACTION.sub(" ", text.lower())
    return _NON_LETTER.sub(" ", lowered).strip()


def fingerprint(text: str) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    return hashlib.sha1(norm[:FINGERPRINT_CHARS].encode("utf-8")).hexdigest()


def mark_templated(df: pd.DataFrame, min_repeats: int = MIN_REPEATS) -> pd.DataFrame:
    """Return narrative rows with `fingerprint` and `templated` columns."""
    narratives = df.loc[df["narrative"].ne(""), ["complaint_id", "product", "issue", "month", "narrative"]]
    prints = narratives["narrative"].map(fingerprint)
    sizes = prints.map(prints.value_counts())
    return narratives.drop(columns="narrative").assign(
        fingerprint=prints, templated=prints.notna() & (sizes >= min_repeats)
    )


def templated_shares(marked: pd.DataFrame, emergence: EmergenceResult) -> dict[str, float]:
    """Share of templated narratives per emerging cluster, over its recent months."""
    recent = marked[marked["month"].isin(emergence.recent_months)]
    by_key = recent.groupby(["product", "issue"])["templated"].mean()
    wanted = {c.id for c in emergence.clusters}
    shares = {cluster_id(p, i): round(float(s), 4) for (p, i), s in by_key.items()}
    return {cid: share for cid, share in shares.items() if cid in wanted}
