from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DemandExecutionMode,
    ReliabilityModelType,
)

RecommendationRisk = Literal["LOW", "MEDIUM", "HIGH"]
RecommendationRuleVersion = Literal["MODEL-RECOMMENDATION-1"]


class CandidateRecommendation(BaseModel):
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    applicable: bool
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    missing_requirements: list[str]
    parameter_sources: dict[str, str]
    risk: RecommendationRisk
    rule_version: RecommendationRuleVersion


class ModelRecommendationSet(BaseModel):
    scenario_version_id: int
    primary: CandidateRecommendation | None
    items: list[CandidateRecommendation]
    rule_version: RecommendationRuleVersion
    warnings: list[dict[str, object]] = Field(default_factory=list)


class ModelRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_version_id: int = Field(gt=0)
