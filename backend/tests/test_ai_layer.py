from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from radar import emergence, extract, themes
from radar.agents import analyst, evidence, skeptic
from radar.llm import ClaudeLLM, LLMError
from radar.schemas import Brief, Extraction, ThemeOut, ThemeSet
from tests import fixtures
from tests.fakes import EXTRACTION, REVIEW, FakeLLM


@pytest.fixture(scope="module")
def result(complaints: pd.DataFrame):
    return emergence.compute(complaints)


# ---------- extract ----------


def test_sample_respects_limits_and_window(complaints: pd.DataFrame, result) -> None:
    sampled = extract.sample(complaints, result, clusters=3, per_cluster=10)
    assert len(sampled) == 30
    assert {s.cluster_id for s in sampled} == {c.id for c in result.clusters[:3]}
    months = complaints.set_index("complaint_id").loc[[s.complaint_id for s in sampled], "month"]
    assert months.max() <= result.month


def test_sample_is_deterministic(complaints: pd.DataFrame, result) -> None:
    a = extract.sample(complaints, result, clusters=2, per_cluster=5)
    b = extract.sample(complaints, result, clusters=2, per_cluster=5)
    assert a == b


def test_extract_prompt_has_required_instructions() -> None:
    assert "unverified allegations" in extract.SYSTEM
    assert "XXXX" in extract.SYSTEM


def test_cache_prevents_reextraction(tmp_path: Path, complaints: pd.DataFrame, result) -> None:
    cache_path = tmp_path / "extractions.jsonl"
    sampled = extract.sample(complaints, result, clusters=1, per_cluster=6)
    llm = FakeLLM()
    first = extract.plan(sampled, extract.load_cache(cache_path), limit=None)
    ok, failed = extract.run(llm, "claude-haiku-4-5-20251001", first.to_call, use_batch=False)
    extract.append_cache(cache_path, ok, "m")
    assert (len(ok), failed, len(llm.calls)) == (6, 0, 6)

    second = extract.plan(sampled, extract.load_cache(cache_path), limit=None)
    assert second.to_call == [] and second.cached == 6


def test_limit_and_estimate(complaints: pd.DataFrame, result) -> None:
    sampled = extract.sample(complaints, result, clusters=2, per_cluster=10)
    work = extract.plan(sampled, {}, limit=5)
    assert len(work.to_call) == 5
    assert work.estimate_usd(batch=True) == pytest.approx(work.estimate_usd(batch=False) / 2)


def test_failed_extractions_are_not_cached(complaints: pd.DataFrame, result) -> None:
    def bad(call):
        raise LLMError("no tool call")

    sampled = extract.sample(complaints, result, clusters=1, per_cluster=3)
    ok, failed = extract.run(FakeLLM(responder=bad), "m", sampled, use_batch=False)
    assert ok == {} and failed == 3


# ---------- themes ----------


def _items(n: int) -> list[tuple[str, Extraction]]:
    return [(str(i), Extraction.model_validate(EXTRACTION)) for i in range(n)]


def test_themes_skip_thin_clusters(result) -> None:
    llm = FakeLLM()
    assert themes.consolidate(llm, "m", result.clusters[0], _items(3)) is None
    assert llm.calls == []


def test_themes_drop_invented_and_duplicate_ids(result) -> None:
    def respond(call):
        return {"themes": [
            {"label": "a", "description": "d", "complaint_ids": ["0", "1", "999"]},
            {"label": "b", "description": "d", "complaint_ids": ["1", "2"]},
            {"label": "c", "description": "d", "complaint_ids": ["777"]},
        ]}

    llm = FakeLLM(responder=respond)
    found = themes.consolidate(llm, "m", result.clusters[0], _items(6))
    assert [(t.label, t.complaint_ids) for t in found] == [("a", ["0", "1"]), ("b", ["2"])]
    assert "unverified allegations" in llm.calls[0].system
    assert "0 | transfer reversed after scam report" in llm.calls[0].user


# ---------- agents ----------


def _package(result) -> dict:
    cluster = result.clusters[0]
    found = [ThemeOut(label="Scam reimbursements", description="d", complaint_ids=["0", "1"])]
    return evidence.build(cluster, result, 0.02, found, dict(_items(6)))


def test_evidence_uses_pipeline_numbers(result) -> None:
    package = _package(result)
    top = result.clusters[0]
    assert package["velocity"] == top.velocity
    assert package["top_companies"][0]["name"] == fixtures.ACCEL_COMPANY
    assert package["ai_mean_severity_1_to_5"] == 4
    assert package["ai_themes"][0]["share_of_sample"] == 1.0
    assert evidence.severity_mean([]) is None


def test_analyst_prompt_and_output(result) -> None:
    llm = FakeLLM()
    brief = analyst.write_brief(llm, "claude-sonnet-5-5", _package(result))
    system = llm.calls[0].system
    for phrase in ["unverified allegations", "hypothesis", "lift", "Do not cite specific rule sections"]:
        assert phrase in system
    assert fixtures.ACCEL_COMPANY in llm.calls[0].user
    assert brief.confidence == 0.7


def test_skeptic_prompt_lists_all_checks(result) -> None:
    llm = FakeLLM()
    brief = Brief.model_validate(analyst.write_brief(FakeLLM(), "m", _package(result)))
    review = skeptic.review_brief(llm, "claude-opus-5-5", brief, _package(result))
    assert review.verdict == "kept"
    for name in skeptic.REQUIRED_CHECKS:
        assert name in llm.calls[0].system
    assert brief.headline in llm.calls[0].user


def test_skeptic_rejects_missing_checks(result) -> None:
    partial = {**REVIEW, "checks": REVIEW["checks"][:4]}
    brief = Brief.model_validate(analyst.write_brief(FakeLLM(), "m", _package(result)))
    with pytest.raises(LLMError):
        skeptic.review_brief(FakeLLM(responder=lambda c: partial), "m", brief, _package(result))


def test_skeptic_verdict_follows_checks(result) -> None:
    failed = [{**REVIEW["checks"][0], "result": "fail"}, *REVIEW["checks"][1:]]
    contradictory = {**REVIEW, "checks": failed, "verdict": "kept"}
    brief = Brief.model_validate(analyst.write_brief(FakeLLM(), "m", _package(result)))
    review = skeptic.review_brief(FakeLLM(responder=lambda c: contradictory), "m", brief,
                                  _package(result))
    assert review.verdict == "rejected"


# ---------- Claude client request shapes ----------


class RecordingClient:
    def __init__(self, message=None, parsed=None) -> None:
        self.kwargs: dict = {}
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._message, self._parsed = message, parsed

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self._message

    def _parse(self, **kwargs):
        self.kwargs = kwargs
        return self._parsed


def test_haiku_uses_forced_tool_and_cached_system() -> None:
    message = SimpleNamespace(stop_reason="tool_use",
                              content=[SimpleNamespace(type="tool_use", input=EXTRACTION)])
    client = RecordingClient(message=message)
    out = ClaudeLLM(client).structured(model="claude-haiku-4-5-20251001", system="s", user="u",
                                       output=Extraction, max_tokens=600)
    assert out.severity == 4
    assert client.kwargs["tool_choice"] == {"type": "tool", "name": "submit"}
    assert client.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert set(client.kwargs["tools"][0]["input_schema"]["properties"]) == set(EXTRACTION)


def test_opus_uses_structured_outputs_with_fallbacks() -> None:
    parsed = ThemeSet.model_validate({"themes": [{"label": "a", "description": "d", "complaint_ids": []}] * 2})
    client = RecordingClient(parsed=SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    out = ClaudeLLM(client).structured(model="claude-opus-5-5", system="s", user="u",
                                       output=ThemeSet, max_tokens=100)
    assert out is parsed
    assert "tool_choice" not in client.kwargs
    assert client.kwargs["output_format"] is ThemeSet
    assert client.kwargs["fallbacks"] == "default"
    assert client.kwargs["output_config"] == {"effort": "high"}


def test_refusal_raises() -> None:
    client = RecordingClient(parsed=SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(LLMError):
        ClaudeLLM(client).structured(model="claude-opus-5-5", system="s", user="u",
                                     output=ThemeSet, max_tokens=100)
