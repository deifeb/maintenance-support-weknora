from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DemandExecutionMode


class CalculationPreviewRequest(BaseModel):
    scenario_version_id: int | None = Field(default=None, gt=0)
    temporary_scenario: dict[str, Any] | None = None
    requested_mode: DemandExecutionMode = DemandExecutionMode.AUTO

    @model_validator(mode="after")
    def one_source(self):
        if (self.scenario_version_id is None) == (self.temporary_scenario is None):
            raise ValueError("provide exactly one of scenario_version_id or temporary_scenario")
        return self


class CalculationCreateRequest(CalculationPreviewRequest):
    calculation_name: str = Field(min_length=1, max_length=200)
    execution_preference: str = Field(default="AUTO", pattern="^(AUTO|SYNC|ASYNC)$")
    random_seed: int = 20260723


class CalculationStatusRead(BaseModel):
    id: int
    calculation_code: str
    status: str
    progress_percent: float
    current_stage: str | None
    error_code: str | None
    error_message: str | None


class CalculationPreviewRead(BaseModel):
    stage_count: int
    fleet_group_count: int
    demand_item_count: int
    installed_position_estimate: float
    recommended_mode: str
    recommended_execution_type: str
    complexity_score: float
    warnings: list[dict[str, Any]]
