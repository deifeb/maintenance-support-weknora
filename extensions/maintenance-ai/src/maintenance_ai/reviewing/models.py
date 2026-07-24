from pydantic import BaseModel, ConfigDict, Field

from maintenance_ai.enums import ReviewBlockingLevel, ReviewSeverity


class ReviewFindingInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    rule_code: str
    title: str
    deterministic_message: str
    severity: ReviewSeverity
    blocking_level: ReviewBlockingLevel
    evidence_ids: tuple[str, ...] = ()
    observed_value: str | None = None
    expected_range: str | None = None


class ReviewExplanationPayload(BaseModel):
    summary: str
    cause: str
    impact: str
    suggested_actions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewExplanation(BaseModel):
    rule_code: str
    summary: str
    cause: str
    impact: str
    suggested_actions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    severity: ReviewSeverity
    blocking_level: ReviewBlockingLevel
