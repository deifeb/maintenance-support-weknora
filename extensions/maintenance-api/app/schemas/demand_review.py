from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    DemandReviewDecisionStatus,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.schemas.demand_list import DemandListRead

DecimalString = Annotated[Decimal, Field(ge=0)]


class DemandReviewRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_source_version: int = Field(ge=1)


DecisionAction = Literal["ACCEPTED", "REJECTED", "EDIT_ACCEPTED"]


def _normalize_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_decision_shape(
    *,
    action: DecisionAction,
    final_quantity: Decimal | None,
    reason: str | None,
) -> None:
    if action in {"ACCEPTED", "REJECTED"} and final_quantity is not None:
        raise ValueError(f"{action} must not include final_quantity")
    if action == "EDIT_ACCEPTED":
        if final_quantity is None:
            raise ValueError("EDIT_ACCEPTED requires final_quantity")
        if reason is None:
            raise ValueError("EDIT_ACCEPTED requires non-empty reason")


class DemandReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_review_version: int = Field(ge=1)
    expected_finding_version: int = Field(ge=1)
    action: DecisionAction
    final_quantity: DecimalString | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _normalize_reason(value)

    @model_validator(mode="after")
    def validate_decision(self) -> "DemandReviewDecisionRequest":
        _validate_decision_shape(
            action=self.action,
            final_quantity=self.final_quantity,
            reason=self.reason,
        )
        return self


class DemandReviewBatchDecisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: int = Field(gt=0)
    expected_finding_version: int = Field(ge=1)
    action: DecisionAction
    final_quantity: DecimalString | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _normalize_reason(value)

    @model_validator(mode="after")
    def validate_decision(self) -> "DemandReviewBatchDecisionItem":
        _validate_decision_shape(
            action=self.action,
            final_quantity=self.final_quantity,
            reason=self.reason,
        )
        return self


class DemandReviewBatchDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_review_version: int = Field(ge=1)
    decisions: tuple[DemandReviewBatchDecisionItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_findings(self) -> "DemandReviewBatchDecisionRequest":
        finding_ids = [item.finding_id for item in self.decisions]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("duplicate finding_id in batch decision")
        return self


class DemandReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    captured_at: datetime
    request: dict[str, Any]
    source_demand_list: dict[str, Any]
    source_items: tuple[dict[str, Any], ...]
    source_events: tuple[dict[str, Any], ...]
    current_inventory: tuple[dict[str, Any], ...]
    master_data_evidence: dict[str, Any]
    rule_set_version: str
    input_hash: str


class FindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_key: str
    rule_code: str
    finding_type: str
    severity: DemandReviewSeverity
    blocking: bool
    requires_admin_acceptance: bool
    source_demand_list_item_id: int | None = None
    effect_key: str | None = None
    evidence_snapshot: dict[str, Any]
    suggestion_snapshot: dict[str, Any]


class DemandReviewFindingRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    finding_key: str
    rule_code: str
    finding_type: str
    severity: DemandReviewSeverity
    blocking: bool
    requires_admin_acceptance: bool
    source_demand_list_item_id: int | None
    effect_key: str | None
    evidence_snapshot: dict[str, Any]
    suggestion_snapshot: dict[str, Any]
    decision_status: DemandReviewDecisionStatus
    version: int


class DemandReviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    tenant_id: str
    source_demand_list_id: int
    source_demand_list_version: int
    source_lineage_id: str
    source_version_number: int
    status: DemandReviewStatus
    rule_set_version: str
    input_hash: str
    source_snapshot: dict[str, Any]
    total_finding_count: int
    blocking_finding_count: int
    pending_finding_count: int
    pending_blocking_finding_count: int
    derived_demand_list_id: int | None
    failure_code: str | None
    failure_summary: str | None
    version: int
    findings: tuple[DemandReviewFindingRead, ...]

class DemandReviewDeriveRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review: DemandReviewRead
    derived_demand_list: DemandListRead
