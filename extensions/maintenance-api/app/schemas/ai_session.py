from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.business_card import MaintenanceBusinessCard


class AISessionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    sensitivity_level: str = "INTERNAL"
    active_scenario_version_id: int | None = Field(default=None, gt=0)


class AIMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    model_override: str | None = None


class AISessionRead(BaseModel):
    id: int
    session_code: str
    title: str
    status: str
    sensitivity_level: str
    execution_mode: str
    last_event_sequence: int


class AIMessageProcessRead(BaseModel):
    message_id: int
    scenario_draft: dict[str, Any]
    readiness: str
    clarification_questions: list[str]


class MaintenanceProjectionSource(BaseModel):
    kind: Literal["AI_MESSAGE_TRIGGER"] = "AI_MESSAGE_TRIGGER"
    session_id: int = Field(gt=0)
    message_id: int = Field(gt=0)


class AIMessageBusinessCardProjectionRead(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source: MaintenanceProjectionSource
    cards: list[MaintenanceBusinessCard] = Field(default_factory=list)
