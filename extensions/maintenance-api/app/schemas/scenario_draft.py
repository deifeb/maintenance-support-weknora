from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.demand_scenario import (
    AgeGroupCreate,
    CommonShockCreate,
    FleetGroupCreate,
    ParameterOverrideCreate,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioValidationResult,
    ScenarioVersionCreate,
)

ScenarioDraftOrigin = Literal["MANUAL", "AI"]
ScenarioFieldSource = Literal[
    "MASTER_DATA",
    "USER_INPUT",
    "AI_INFERRED",
    "SYSTEM_DEFAULT",
    "DERIVED",
]
ScenarioFieldRisk = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
    "BLOCKING",
]


class ScenarioFieldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None = None
    source: ScenarioFieldSource
    confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    risk: ScenarioFieldRisk
    confirmed: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class ScenarioDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(default="", max_length=200)
    current_step: int = Field(default=1, ge=1, le=6)
    fields: dict[str, ScenarioFieldState] = Field(
        default_factory=dict
    )


class ScenarioDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    sensitivity_level: str = Field(
        default="INTERNAL",
        min_length=1,
        max_length=24,
    )


class ScenarioDraftSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    draft: ScenarioDraftPayload


class ScenarioDraftEvaluation(BaseModel):
    completion: dict[str, bool]
    blocking_fields: list[str]


class ScenarioDraftFleetUsage(BaseModel):
    fleet_group_key: str = Field(min_length=1, max_length=64)
    active_quantity: int = Field(ge=0)
    utilization_override: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    equipment_intensity_factor: Decimal = Field(
        default=Decimal("1"),
        gt=0,
    )
    environment_factor_override: Decimal | None = Field(
        default=None,
        gt=0,
    )
    is_active: bool = True
    notes: str | None = None


class ScenarioDraftShock(CommonShockCreate):
    fleet_group_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )


class ScenarioDraftStage(ScenarioStageCreate):
    client_key: str = Field(min_length=1, max_length=64)
    fleet_usages: list[ScenarioDraftFleetUsage] = Field(
        default_factory=list
    )
    shocks: list[ScenarioDraftShock] = Field(
        default_factory=list
    )


class ScenarioDraftFleetGroup(FleetGroupCreate):
    client_key: str = Field(min_length=1, max_length=64)
    age_groups: list[AgeGroupCreate] = Field(
        default_factory=list
    )


class ScenarioDraftOverride(ParameterOverrideCreate):
    stage_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )
    fleet_group_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )


class ScenarioDraftMaterializationPayload(BaseModel):
    template: ScenarioTemplateCreate
    version: ScenarioVersionCreate
    fleet_groups: list[ScenarioDraftFleetGroup]
    stages: list[ScenarioDraftStage]
    overrides: list[ScenarioDraftOverride] = Field(
        default_factory=list
    )


class ScenarioDraftMaterializeRequest(BaseModel):
    expected_version: int = Field(ge=1)


class ScenarioDraftMaterializeResponse(BaseModel):
    scenario_id: int
    scenario_version_id: int
    status: str
    validation: ScenarioValidationResult
    replayed: bool


class ScenarioDraftEnvelope(BaseModel):
    session_id: int
    snapshot_id: int
    version: int
    origin: ScenarioDraftOrigin
    draft: ScenarioDraftPayload
    completion: dict[str, bool]
    blocking_fields: list[str]
    updated_at: datetime
