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

Run all five checks. For each, write a one-sentence reason that cites numbers from the
evidence first, then a result of pass or fail that agrees with that reason:
1. size: is the signal explained by company size? Lift compares a company's share of
   this cluster with its share of the same product, so lift near 1 means a company is
   just big within its market. Fail only if the brief attributes the signal to a
   specific company whose lift does not support it. A rise spread across companies
   with lift near 1 is a market-wide signal, not a size artifact, and passes.
2. templating: fail if 30% or more of recent narratives are templated, since
   copy-paste or form-letter submissions can manufacture a spike.
3. concentration: is it one state or one company only?
4. thin_evidence: is the AI sample too small or too off-topic to support the root
   cause the brief names? The sample is capped at about 40 complaints per cluster by
   design, so never fail because the sample is small next to total complaint volume.
   Fail if fewer than about 15 complaints were sampled, if fewer than 10 narratives
   exist in the recent months, or if the themes behind the named root cause cover only
   a small part of the sample.
5. seasonality: read the monthly counts, not just the averages. Fail if the recent
   average rests on one peak month, or if the series has fallen for the last two
   months and the latest month is well below the recent peak. A rise that holds or
   keeps climbing passes.

Judge each check on its own. Lenient guidance on one check is not a reason to pass
another, and a brief must survive all five to be kept.

Return exactly one entry per check, using these names: size, templating,
concentration, thin_evidence, seasonality. Set verdict to "rejected" if any check
fails; otherwise "kept". `note` is one plain
sentence for the UI explaining the verdict."""


def user_message(brief: Brief, evidence: dict[str, Any]) -> str:
    return (
        f"Analyst brief:\n{brief.model_dump_json(indent=1)}\n\n"
        f"Evidence package:\n{render(evidence)}\n\nReview the brief."
    )


ATTEMPTS = 2


def validate_checks(review: SkepticReview) -> SkepticReview:
    """Require all five checks, and a verdict (and so a note) that agrees with them.

    The verdict is never corrected in code: the note was written for the model's
    verdict, so a corrected verdict could sit next to a note arguing the opposite.
    """
    names = sorted(c.name for c in review.checks)
    if names != sorted(REQUIRED_CHECKS):
        raise LLMError(f"skeptic returned checks {names}, expected {sorted(REQUIRED_CHECKS)}")
    expected = "rejected" if any(c.result == "fail" for c in review.checks) else "kept"
    if review.verdict != expected:
        raise LLMError(f"skeptic verdict {review.verdict!r} disagrees with its checks")
    return review


def review_brief(llm: LLM, model: str, brief: Brief, evidence: dict[str, Any]) -> SkepticReview:
    """Review a brief, asking again (up to ATTEMPTS times) if the response is inconsistent."""
    errors: list[LLMError] = []

    def attempt() -> SkepticReview | None:
        try:
            return validate_checks(llm.structured(
                model=model, system=SYSTEM, user=user_message(brief, evidence),
                output=SkepticReview, max_tokens=MAX_TOKENS,
            ))
        except LLMError as exc:
            errors.append(exc)
            return None

    # The generator is lazy, so attempts stop at the first valid review.
    review = next((r for r in (attempt() for _ in range(ATTEMPTS)) if r is not None), None)
    if review is None:
        raise errors[-1]
    return review
