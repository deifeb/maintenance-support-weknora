from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DemandReviewDecisionStatus,
    DemandReviewSeverity,
    DemandReviewStatus,
)

DecimalString = Annotated[Decimal, Field(ge=0)]


class DemandReviewRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_source_version: int = Field(ge=1)


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
