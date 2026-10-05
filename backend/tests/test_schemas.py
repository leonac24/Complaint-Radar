from __future__ import annotations

import pytest
from pydantic import ValidationError

from radar.schemas import Extraction, RadarFile, ThemeSet

RADAR_EXAMPLE = {
    "month": "2026-07",
    "clusters": [{
        "id": "a1b2c3d4e5",
        "product": "Money transfer, virtual currency, or money service",
        "issue": "Fraud or scam",
        "product_family": "payments",
        "velocity": 2.9,
        "recent_monthly_avg": 415,
        "baseline_monthly_avg": 140,
        "severity": 3.8,
        "templated_share": 0.04,
        "vulnerable_share": 0.21,
        "narrative_count": 1210,
        "themes": [{"label": "l", "description": "d", "share": 0.42}],
        "top_companies": [{"name": "n", "count": 947, "lift": 2.1}],
        "states": {"CA": 120},
        "months": [{"month": "2025-09", "count": 130}],
        "brief": {"headline": "h", "confidence": 0.8},
        "skeptic": {"verdict": "kept", "note": "n"},
    }],
}


def test_radar_contract_example_validates() -> None:
    parsed = RadarFile.model_validate(RADAR_EXAMPLE)
    assert parsed.model_dump(mode="json") == RADAR_EXAMPLE


def test_ai_fields_may_be_null_before_ai_steps_run() -> None:
    cluster = {**RADAR_EXAMPLE["clusters"][0], "severity": None, "brief": None, "skeptic": None}
    RadarFile.model_validate({"month": "2026-07", "clusters": [cluster]})


def test_extraction_rejects_bad_enum_and_severity() -> None:
    good = {
        "root_cause": "dispute not investigated",
        "root_cause_family": "disputes_and_errors",
        "journey_stage": "dispute",
        "harm": "lost $200",
        "money_at_stake_usd": 200,
        "vulnerable_consumer": False,
        "severity": 3,
        "summary": "Consumer says a dispute was closed without review.",
        "looks_templated": False,
    }
    Extraction.model_validate(good)
    with pytest.raises(ValidationError):
        Extraction.model_validate({**good, "root_cause_family": "made_up"})
    with pytest.raises(ValidationError):
        Extraction.model_validate({**good, "severity": 6})


def test_theme_set_bounds() -> None:
    theme = {"label": "l", "description": "d", "complaint_ids": ["1"]}
    with pytest.raises(ValidationError):
        ThemeSet.model_validate({"themes": [theme]})
    ThemeSet.model_validate({"themes": [theme] * 5})
