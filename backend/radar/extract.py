"""Per-narrative AI extraction with a permanent cache keyed by complaint_id."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from radar.llm import LLM, Job, LLMError
from radar.schemas import EmergenceResult, Extraction

MAX_NARRATIVE_CHARS = 6000
MAX_TOKENS = 600
POOL_FACTOR = 10  # sample from the newest per_cluster * POOL_FACTOR narratives
SEED = 1

# Rough Haiku 4.5 prices for the dry-run estimate only ($ per million tokens).
PRICE_IN, PRICE_OUT = 1.0, 5.0
EST_OVERHEAD_TOKENS = 700
EST_OUTPUT_TOKENS = 250

SYSTEM = """You analyze consumer complaints about financial companies for a bank's risk team.
Read the narrative and extract what actually happened, beyond the form category the
consumer picked. Be literal: report only what the narrative supports.

Narratives are unverified allegations made by consumers. Describe them as claims, never
as established facts or findings of wrongdoing. 'XXXX' (or any run of X characters)
marks text the CFPB redacted; do not guess what it hid.

The summary must be one neutral sentence that paraphrases the claim, with no names of
people and no quoted text from the narrative. Call the submit tool with your result."""


@dataclass(frozen=True)
class Sampled:
    complaint_id: str
    cluster_id: str
    product: str
    issue: str
    narrative: str


def sample(
    df: pd.DataFrame, emergence: EmergenceResult, clusters: int, per_cluster: int
) -> list[Sampled]:
    """Up to per_cluster narratives from each of the top clusters, newest first.

    Only months inside the analysis window are eligible, so --as-of runs never see
    narratives from the future.
    """
    eligible = df[df["narrative"].ne("") & df["month"].isin(emergence.window_months)]
    grouped = dict(list(eligible.groupby(["product", "issue"])))
    picked = [
        _pick(grouped.get((c.product, c.issue)), c.id, per_cluster)
        for c in emergence.clusters[:clusters]
    ]
    return [row for rows in picked for row in rows]


def _pick(pool: pd.DataFrame | None, cluster_id: str, per_cluster: int) -> list[Sampled]:
    if pool is None or pool.empty:
        return []
    newest = pool.sort_values(["date_received", "complaint_id"]).tail(per_cluster * POOL_FACTOR)
    chosen = newest.sample(min(per_cluster, len(newest)), random_state=SEED)
    return [
        Sampled(r.complaint_id, cluster_id, r.product, r.issue, r.narrative)
        for r in chosen.itertuples(index=False)
    ]


def user_message(row: Sampled) -> str:
    return (
        f"Product: {row.product}\nIssue picked by the consumer: {row.issue}\n\n"
        f"Narrative (unverified allegation):\n{row.narrative[:MAX_NARRATIVE_CHARS]}"
    )


# ---------- cache ----------


def load_cache(path: Path) -> dict[str, Extraction]:
    if not path.exists():
        return {}
    records = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return {r["complaint_id"]: Extraction.model_validate(r["extraction"]) for r in records}


def append_cache(path: Path, results: dict[str, Extraction], model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.writelines(
            json.dumps({"complaint_id": cid, "model": model, "extraction": e.model_dump()}) + "\n"
            for cid, e in results.items()
        )


# ---------- planning and running ----------


@dataclass(frozen=True)
class Plan:
    sampled: list[Sampled]
    to_call: list[Sampled]
    cached: int

    def estimate_usd(self, batch: bool) -> float:
        tokens_in = sum(len(r.narrative[:MAX_NARRATIVE_CHARS]) / 4 + EST_OVERHEAD_TOKENS
                        for r in self.to_call)
        tokens_out = EST_OUTPUT_TOKENS * len(self.to_call)
        cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6
        return cost / 2 if batch else cost


def plan(sampled: list[Sampled], cache: dict[str, Extraction], limit: int | None) -> Plan:
    unique = list({r.complaint_id: r for r in sampled}.values())
    missing = [r for r in unique if r.complaint_id not in cache]
    to_call = missing[:limit] if limit is not None else missing
    return Plan(sampled=sampled, to_call=to_call, cached=len(unique) - len(missing))


def run(llm: LLM, model: str, todo: list[Sampled], use_batch: bool) -> tuple[dict[str, Extraction], int]:
    """Extract every row in todo. Returns (successes, failure count)."""
    jobs = [Job(custom_id=r.complaint_id, user=user_message(r)) for r in todo]
    results = llm.many(model=model, system=SYSTEM, jobs=jobs, output=Extraction,
                       max_tokens=MAX_TOKENS, use_batch=use_batch)
    ok = {cid: res for cid, res in results.items() if not isinstance(res, LLMError)}
    return ok, len(results) - len(ok)


def sample_index(sampled: list[Sampled]) -> dict[str, list[str]]:
    """cluster_id -> sampled complaint IDs, the input contract for `themes`."""
    index: dict[str, list[str]] = {}
    for row in sampled:
        index.setdefault(row.cluster_id, []).append(row.complaint_id)
    return index
