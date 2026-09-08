from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maintenance_ai.enums import ConfirmationLevel, PlanActionType, UserIntent


class PlanStep(BaseModel):
    model_config = ConfigDict(frozen=True)
    step_code: str
    action_type: PlanActionType = PlanActionType.CALL_TOOL
    tool_name: str | None = None
    input_template: dict[str, Any] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    requires_confirmation: ConfirmationLevel = ConfirmationLevel.NONE
    risk_level: str = "LOW"


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    goal: str
    intent: UserIntent
    steps: tuple[PlanStep, ...]
    plan_version: str = "1.0"


class ToolPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    allowed_intents: set[UserIntent]
    confirmation_level: ConfirmationLevel = ConfirmationLevel.NONE
