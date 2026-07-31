from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ScenarioDraftEnvelope(BaseModel):
    session_id: int
    snapshot_id: int
    version: int
    origin: ScenarioDraftOrigin
    draft: ScenarioDraftPayload
    completion: dict[str, bool]
    blocking_fields: list[str]
    updated_at: datetime
