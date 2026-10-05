"""Pydantic models for pipeline outputs and the frontend data contract.

Keep the contract models (Radar*, ClusterDetail, ...) in sync with frontend/lib/types.ts.
Fields that depend on an AI step are nullable: if the step has not run they are null,
never guessed.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

RootCauseFamily = Literal[
    "fees_and_charges",
    "disputes_and_errors",
    "fraud_and_scams",
    "access_and_service",
    "credit_reporting_accuracy",
    "collections_conduct",
    "servicing_process",
    "disclosure_and_terms",
    "other",
]
JourneyStage = Literal[
    "account_opening", "everyday_use", "payment", "dispute", "collections", "closing", "other"
]
Verdict = Literal["kept", "rejected"]
CheckName = Literal["size", "templating", "concentration", "thin_evidence", "seasonality"]


# ---------- shared pieces ----------


class MonthCount(BaseModel):
    month: str
    count: int


class TopCompany(BaseModel):
    name: str
    count: int
    lift: float


# ---------- emergence (no AI) ----------


class ClusterStats(BaseModel):
    id: str
    product: str
    issue: str
    product_family: str
    rank: int
    velocity: float
    recent_monthly_avg: float
    baseline_monthly_avg: float
    baseline_months: int
    narrative_count: int
    months: list[MonthCount]
    states: dict[str, int]
    top_companies: list[TopCompany]


class EmergenceResult(BaseModel):
    month: str
    as_of: str | None
    recent_months: list[str]
    baseline_months: list[str]
    window_months: list[str]
    total_recent_complaints: int
    clusters: list[ClusterStats]


# ---------- AI outputs ----------


class Extraction(BaseModel):
    root_cause: str
    root_cause_family: RootCauseFamily
    journey_stage: JourneyStage
    harm: str
    money_at_stake_usd: float | None
    vulnerable_consumer: bool
    severity: int = Field(ge=1, le=5)
    summary: str
    looks_templated: bool

    # Haiku occasionally writes "<UNKNOWN>" for a null amount or invents a category
    # name; both used to fail the whole extraction.
    @field_validator("money_at_stake_usd", mode="before")
    @classmethod
    def _placeholder_amount_is_null(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return float(value.replace("$", "").replace(",", ""))
            except ValueError:
                return None
        return value

    @field_validator("root_cause_family", "journey_stage", mode="before")
    @classmethod
    def _unknown_category_is_other(cls, value: Any, info: Any) -> Any:
        allowed = get_args(cls.model_fields[info.field_name].annotation)
        return value if value in allowed else "other"


class ThemeOut(BaseModel):
    label: str
    description: str
    complaint_ids: list[str]


class ThemeSet(BaseModel):
    themes: list[ThemeOut] = Field(min_length=2, max_length=5)


class Brief(BaseModel):
    headline: str
    what_is_happening: str
    who_is_affected: str
    likely_root_cause: str
    process_or_control_to_check: str
    regulatory_area: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)


# Field order matters: structured output is generated in this order, so the reason
# comes before the result and the checks come before the verdict.
class SkepticCheck(BaseModel):
    name: CheckName
    reason: str
    result: Literal["pass", "fail"]


class SkepticReview(BaseModel):
    checks: list[SkepticCheck]
    verdict: Verdict
    note: str


# ---------- frontend contract ----------


class ThemeShare(BaseModel):
    label: str
    description: str
    share: float


class BriefSummary(BaseModel):
    headline: str
    confidence: float


class SkepticSummary(BaseModel):
    verdict: Verdict
    note: str


class RadarCluster(BaseModel):
    id: str
    product: str
    issue: str
    product_family: str
    velocity: float
    recent_monthly_avg: float
    baseline_monthly_avg: float
    severity: float | None
    templated_share: float | None
    vulnerable_share: float | None
    narrative_count: int
    themes: list[ThemeShare]
    top_companies: list[TopCompany]
    states: dict[str, int]
    months: list[MonthCount]
    brief: BriefSummary | None
    skeptic: SkepticSummary | None


class RadarFile(BaseModel):
    month: str
    clusters: list[RadarCluster]


class ExampleSummary(BaseModel):
    complaint_id: str
    summary: str


class ThemeDetail(BaseModel):
    label: str
    description: str
    share: float
    complaint_ids: list[str]
    examples: list[ExampleSummary]


class ClusterDetail(BaseModel):
    id: str
    month: str
    product: str
    issue: str
    product_family: str
    velocity: float
    recent_monthly_avg: float
    baseline_monthly_avg: float
    severity: float | None
    templated_share: float | None
    vulnerable_share: float | None
    narrative_count: int
    top_companies: list[TopCompany]
    states: dict[str, int]
    months: list[MonthCount]
    themes: list[ThemeDetail]
    brief: Brief | None
    skeptic: SkepticReview | None
    examples: list[ExampleSummary]
