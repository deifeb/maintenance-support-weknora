from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maintenance_ai.enums import FieldRiskLevel, FieldSourceType, ScenarioReadiness


class FieldValue(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: Any = None
    source_type: FieldSourceType
    source_reference: str | None = None
    confidence: float = Field(ge=0, le=1)
    confirmed: bool = False
    risk_level: FieldRiskLevel


class ScenarioStageDraft(BaseModel):
    code: str
    name: str
    duration_hours: float = Field(gt=0)
    usage_intensity: float = Field(default=1.0, gt=0)


class ScenarioDraft(BaseModel):
    scenario_name: FieldValue | None = None
    equipment_model: FieldValue | None = None
    configuration_version: FieldValue | None = None
    equipment_quantity: FieldValue | None = None
    duration_days: FieldValue | None = None
    stages: FieldValue | None = None
    usage_intensity: FieldValue | None = None
    service_level: FieldValue | None = None
    calculation_method: FieldValue | None = None
    repair_policy: FieldValue | None = None
    common_shock_policy: FieldValue | None = None
    assumptions: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)


class ClarificationResult(BaseModel):
    readiness: ScenarioReadiness
    missing_fields: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
