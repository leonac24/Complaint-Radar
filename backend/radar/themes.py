"""AI consolidation of extracted root causes into 2-5 themes per cluster."""

from __future__ import annotations

from radar.llm import LLM
from radar.schemas import ClusterStats, Extraction, ThemeOut, ThemeSet

MIN_EXTRACTIONS = 5
MAX_TOKENS = 8000

SYSTEM = """You help a bank's risk team see patterns inside a group of consumer complaints
that share the same CFPB product and issue category. Each line is one complaint: its
CFPB complaint ID, a short root-cause phrase, and a one-sentence summary, all written by
an earlier extraction step.

Complaints are unverified allegations. Treat them as claims, not findings.

Group the complaints into 2 to 5 consolidated themes that are more specific and useful
than the form category. Each theme needs a short label (sentence case, under 8 words),
a one-sentence neutral description, and the complaint IDs that belong to it. Use only
IDs from the input. A complaint may sit in at most one theme; leave out complaints that
fit no theme rather than forcing them in."""


def user_message(cluster: ClusterStats, items: list[tuple[str, Extraction]]) -> str:
    lines = "\n".join(f"{cid} | {e.root_cause} | {e.summary}" for cid, e in items)
    return (
        f"Category: {cluster.product} / {cluster.issue}\n"
        f"{len(items)} complaints (id | root cause | summary):\n{lines}"
    )


def clean(themes: ThemeSet, valid_ids: set[str]) -> list[ThemeOut]:
    """Drop IDs the model invented or repeated across themes, then empty themes."""
    seen: set[str] = set()
    cleaned = []
    for theme in themes.themes:
        ids = [cid for cid in dict.fromkeys(theme.complaint_ids) if cid in valid_ids and cid not in seen]
        seen.update(ids)
        cleaned.append(theme.model_copy(update={"complaint_ids": ids}))
    return [t for t in cleaned if t.complaint_ids]


def consolidate(
    llm: LLM, model: str, cluster: ClusterStats, items: list[tuple[str, Extraction]]
) -> list[ThemeOut] | None:
    """Themes for one cluster, or None when there are too few extractions to group."""
    if len(items) < MIN_EXTRACTIONS:
        return None
    result = llm.structured(model=model, system=SYSTEM, user=user_message(cluster, items),
                            output=ThemeSet, max_tokens=MAX_TOKENS)
    return clean(result, {cid for cid, _ in items})
