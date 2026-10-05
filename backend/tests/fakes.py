"""A fake LLM that records calls and returns canned, schema-valid outputs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from radar.llm import Job, LLMError

EXTRACTION = {
    "root_cause": "transfer reversed after scam report",
    "root_cause_family": "fraud_and_scams",
    "journey_stage": "dispute",
    "harm": "lost funds",
    "money_at_stake_usd": 250.0,
    "vulnerable_consumer": False,
    "severity": 4,
    "summary": "Consumer says a scam transfer was not reimbursed.",
    "looks_templated": False,
}
BRIEF = {
    "headline": "Scam transfer disputes rising at one payments company",
    "what_is_happening": "w",
    "who_is_affected": "a",
    "likely_root_cause": "Hypothesis: r",
    "process_or_control_to_check": "p",
    "regulatory_area": "electronic fund transfer disputes",
    "evidence": ["velocity 3.5x"],
    "confidence": 0.7,
}
CHECKS = ["size", "templating", "concentration", "thin_evidence", "seasonality"]
REVIEW = {
    "verdict": "kept",
    "checks": [{"name": n, "result": "pass", "reason": "r"} for n in CHECKS],
    "note": "n",
}


@dataclass
class Call:
    model: str
    system: str
    user: str
    output: type[BaseModel]


@dataclass
class FakeLLM:
    responder: Callable[[Call], dict[str, Any]] | None = None
    calls: list[Call] = field(default_factory=list)

    def structured(self, *, model: str, system: str, user: str, output: type[BaseModel],
                   max_tokens: int, effort: str | None = None) -> Any:
        call = Call(model, system, user, output)
        self.calls.append(call)
        return output.model_validate(self.responder(call) if self.responder else default(call))

    def many(self, *, model: str, system: str, jobs: Sequence[Job], output: type[BaseModel],
             max_tokens: int, use_batch: bool = False) -> dict[str, Any]:
        return {j.custom_id: self._safe(model, system, j.user, output, max_tokens) for j in jobs}

    def _safe(self, model: str, system: str, user: str, output: type[BaseModel],
              max_tokens: int) -> Any:
        try:
            return self.structured(model=model, system=system, user=user, output=output,
                                   max_tokens=max_tokens)
        except LLMError as exc:
            return exc


def default(call: Call) -> dict[str, Any]:
    name = call.output.__name__
    if name == "Extraction":
        return EXTRACTION
    if name == "Brief":
        return BRIEF
    if name == "SkepticReview":
        return REVIEW
    raise AssertionError(f"no canned output for {name}")
