"""Skeptic agent: challenges each brief against the same evidence, keep or reject."""

from __future__ import annotations

from typing import Any

from radar.agents.evidence import render
from radar.llm import LLM, LLMError
from radar.schemas import Brief, SkepticReview

MAX_TOKENS = 8000
REQUIRED_CHECKS = ("size", "templating", "concentration", "thin_evidence", "seasonality")

SYSTEM = """You are the skeptic on a bank's risk team. An analyst wrote a brief claiming
that a cluster of consumer complaints is an emerging risk signal. Your job is to reject
weak signals. You see the brief and the exact evidence package the analyst used.

Complaints are unverified allegations; you are judging whether the signal is real and
well supported, not whether any company did anything wrong.

Run all five checks and give each a result of pass or fail with a one-sentence reason
that cites numbers from the evidence:
1. size: is the signal explained by a company's overall volume? Check lift: a top
   company with lift near 1 is just big, not over-represented.
2. templating: is a high templated share of narratives driving the spike?
3. concentration: is it one state or one company only?
4. thin_evidence: are there too few narratives or AI-sampled complaints to support
   the root cause the brief names?
5. seasonality: does the monthly series look like a single blip or a known one-off
   rather than sustained acceleration?

Return exactly one entry per check, using these names: size, templating,
concentration, thin_evidence, seasonality. Set verdict to "rejected" if any check fails
in a way that undermines the brief's main claim; otherwise "kept". `note` is one plain
sentence for the UI explaining the verdict."""


def user_message(brief: Brief, evidence: dict[str, Any]) -> str:
    return (
        f"Analyst brief:\n{brief.model_dump_json(indent=1)}\n\n"
        f"Evidence package:\n{render(evidence)}\n\nReview the brief."
    )


def validate_checks(review: SkepticReview) -> SkepticReview:
    names = sorted(c.name for c in review.checks)
    if names != sorted(REQUIRED_CHECKS):
        raise LLMError(f"skeptic returned checks {names}, expected {sorted(REQUIRED_CHECKS)}")
    return review


def review_brief(llm: LLM, model: str, brief: Brief, evidence: dict[str, Any]) -> SkepticReview:
    review = llm.structured(model=model, system=SYSTEM, user=user_message(brief, evidence),
                            output=SkepticReview, max_tokens=MAX_TOKENS)
    return validate_checks(review)
