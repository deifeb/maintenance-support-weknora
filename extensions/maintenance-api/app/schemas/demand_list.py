from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

from app.models.enums import (
    CalculationDecisionType,
    DemandExecutionMode,
    DemandListEventType,
    DemandListStatus,
    ReliabilityModelType,
)

DecimalString = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: format(value, "f"),
        return_type=str,
        when_used="json",
    ),
]


class DemandListItemQuantitySnapshot(BaseModel):
    original_quantity: DecimalString
    final_quantity: DecimalString


class DemandListCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculation_group_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None


class DemandListItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    final_quantity: DecimalString = Field(ge=0)
    adjustment_reason: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator("adjustment_reason", mode="before")
    @classmethod
    def strip_adjustment_reason(
        cls,
        value: object,
    ) -> object:
        return value.strip() if isinstance(value, str) else value


class DemandListTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class DemandListConfirmRequest(
    DemandListTransitionRequest
):
    confirmation_note: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator(
        "confirmation_note",
        mode="before",
    )
    @classmethod
    def strip_confirmation_note(
        cls,
        value: object,
    ) -> object:
        return (
            value.strip()
            if isinstance(value, str)
            else value
        )


class DemandListItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    demand_list_id: int
    spare_part_id: int
    spare_part_code_snapshot: str
    spare_part_name_snapshot: str
    spare_part_unit_snapshot: str
    criticality_level_snapshot: str | None
    source_calculation_group_id: int | None
    source_group_child_id: int | None
    source_calculation_id: int | None
    source_calculation_run_id: int | None
    source_result_id: int | None
    reliability_model: ReliabilityModelType | None
    execution_mode: DemandExecutionMode | None
    original_quantity: DecimalString
    final_quantity: DecimalString
    decision_type: CalculationDecisionType | None
    decision_reason: str | None
    decision_risk: str | None
    requires_admin_confirmation: bool
    confirmed_by_admin: bool
    risk_rule_version: str | None
    source_snapshot_json: dict[str, Any]
    decision_snapshot_json: dict[str, Any] | None
    interval_snapshot_json: dict[str, Any] | None
    parameter_snapshot_json: dict[str, Any] | None
    warning_snapshot_json: list[str] | None
    inventory_snapshot_json: dict[str, Any] | None
    version: int
    created_at: datetime
    updated_at: datetime


class DemandListEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    demand_list_id: int
    event_type: DemandListEventType
    actor_user_id: str
    actor_roles_json: list[str]
    request_id: str
    idempotency_key: str | None
    request_hash: str | None
    before_summary_json: dict[str, Any] | None
    after_summary_json: dict[str, Any] | None
    response_snapshot_json: dict[str, Any] | None
    occurred_at: datetime


class DemandListSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    lineage_id: str
    version_number: int
    derived_from_id: int | None
    scenario_version_id: int
    calculation_group_id: int
    status: DemandListStatus
    is_current: bool
    superseded_by_id: int | None
    superseded_at: datetime | None
    version: int
    created_by_user_id: str
    created_by_request_id: str
    created_at: datetime
    updated_at: datetime


class DemandListRead(DemandListSummaryRead):
    submitted_by_user_id: str | None
    submitted_by_request_id: str | None
    submitted_at: datetime | None
    confirmed_by_user_id: str | None
    confirmed_by_request_id: str | None
    confirmed_at: datetime | None
    published_by_user_id: str | None
    published_by_request_id: str | None
    published_at: datetime | None
    voided_by_user_id: str | None
    voided_by_request_id: str | None
    voided_at: datetime | None
    items: list[DemandListItemRead] = Field(
        default_factory=list,
    )
    events: list[DemandListEventRead] = Field(
        default_factory=list,
    )
