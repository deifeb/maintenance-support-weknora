from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    CalculationDecisionType,
    CalculationGroupStatus,
    DemandExecutionMode,
    ReliabilityModelType,
)


class CalculationGroupChildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    calculation_id: int
    attempt_number: int
    is_current_attempt: bool
    is_primary: bool
    selection_reason: str | None
    created_at: datetime


class CalculationGroupEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    child_id: int | None
    sequence: int
    event_type: str
    payload_json: dict[str, Any]
    occurred_at: datetime


class CalculationItemDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    spare_part_id: int
    source_child_id: int
    selected_child_id: int
    original_quantity: Decimal
    final_quantity: Decimal
    decision_type: CalculationDecisionType
    reason: str | None
    risk: str
    requires_admin_confirmation: bool
    confirmed_by_admin: bool
    risk_rule_version: str
    version: int
    updated_at: datetime


class CalculationGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_version_id: int
    status: CalculationGroupStatus
    primary_candidate_key: str
    recommendation_snapshot_json: dict[str, Any]
    parameter_snapshot_json: dict[str, Any]
    last_event_sequence: int
    version: int
    created_by_user_id: str
    created_by_request_id: str
    created_at: datetime
    updated_at: datetime


class CalculationGroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_version_id: int = Field(gt=0)
    primary_candidate_key: str = Field(
        min_length=3,
        max_length=80,
    )
    selected_candidate_keys: list[str] = Field(
        min_length=1,
        max_length=10,
    )
    random_seed: int = 20260723


class ComparisonCandidateCell(BaseModel):
    child_id: int
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    status: str
    item_status: str | None = None
    recommended_quantity: Decimal | None = None
    expected_demand: Decimal | None = None
    p50: Decimal | None = None
    p95: Decimal | None = None
    p99: Decimal | None = None
    usable_inventory: Decimal | None = None
    net_demand_gap: Decimal | None = None
    shortage_risk_level: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CalculationComparisonRow(BaseModel):
    spare_part_id: int
    spare_part_code: str
    spare_part_name: str
    criticality_level: str | None
    system_child_id: int
    candidates: dict[str, ComparisonCandidateCell]
    decision: CalculationItemDecisionRead | None = None


class CalculationGroupComparisonRead(BaseModel):
    group_id: int
    group_status: CalculationGroupStatus
    primary_candidate_key: str
    candidate_keys: list[str]
    risk_rule_version: str
    rows: list[CalculationComparisonRow]


class CalculationItemDecisionSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    selected_child_id: int = Field(gt=0)
    final_quantity: Decimal = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)
