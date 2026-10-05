"""Analyst agent: writes an issue brief for one emerging cluster."""

from __future__ import annotations

from typing import Any

from radar.agents.evidence import render
from radar.llm import LLM
from radar.schemas import Brief

MAX_TOKENS = 8000

SYSTEM = """You are a risk analyst writing for a bank executive. You receive an evidence
package about one cluster of consumer complaints sent to the CFPB: complaint volume
over time, how fast it is accelerating, which companies are over-represented relative
to their size within the same product (lift above 1), how many narratives look templated, and themes and
summaries written by an earlier AI step over a sample of narratives.

Rules:
- Complaints are unverified allegations. Call them claims or signals, never findings
  of wrongdoing, and never predict a legal or regulatory outcome for any company.
- Use only numbers that appear in the evidence package. Every item in `evidence` must
  be a quantified statement taken from it.
- Judge companies by lift, not by raw complaint count. Large companies get more
  complaints because they have more customers.
- Frame `likely_root_cause` as a hypothesis to test, not a conclusion.
- `process_or_control_to_check` names where inside a bank to look (a process,
  control, or team), not what a specific company did.
- `regulatory_area` names a general area such as electronic fund transfer disputes or
  debt collection conduct. Do not cite specific rule sections unless you are certain.
- `headline` is plain language, under 15 words, sentence case.
- `confidence` (0 to 1) reflects how well the evidence supports the brief: lower it for
  thin samples, high templating, or a short baseline."""


def user_message(evidence: dict[str, Any]) -> str:
    return f"Evidence package:\n{render(evidence)}\n\nWrite the issue brief."


def write_brief(llm: LLM, model: str, evidence: dict[str, Any]) -> Brief:
    return llm.structured(model=model, system=SYSTEM, user=user_message(evidence),
                          output=Brief, max_tokens=MAX_TOKENS)
