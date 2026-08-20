from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, VersionedMixin

RULE_STATUSES = ("DRAFT", "SIMULATED", "PUBLISHED", "RETIRED")
SIMULATION_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
PLAN_STATUSES = (
    "DRAFT",
    "PREVIEWED",
    "CONFIRMED",
    "EXECUTING",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "VOIDED",
)


class AllocationRuleVersion(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "allocation_rule_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_allocation_rule_version_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "lineage_id",
            "version_number",
            name="uq_allocation_rule_lineage_version",
        ),
        CheckConstraint("version >= 1", name="ck_allocation_rule_version"),
        CheckConstraint("version_number >= 1", name="ck_allocation_rule_version_number"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_allocation_rule_effective_range",
        ),
        Index("ix_allocation_rule_versions_tenant_status", "tenant_id", "status"),
        Index(
            "ix_allocation_rule_versions_tenant_effective",
            "tenant_id",
            "effective_from",
            "effective_to",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lineage_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            *RULE_STATUSES,
            name="allocationrulestatus",
            native_enum=False,
            create_constraint=True,
            length=16,
        ),
        nullable=False,
        default="DRAFT",
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hard_rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalization_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    published_by_user_id: Mapped[str | None] = mapped_column(String(128))
    published_by_request_id: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AllocationSimulation(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "allocation_simulations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_allocation_simulation_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_allocation_simulation_tenant_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "candidate_rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "baseline_rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_allocation_simulation_version"),
        Index("ix_allocation_simulations_tenant_status", "tenant_id", "status"),
        Index(
            "ix_allocation_simulations_tenant_candidate",
            "tenant_id",
            "candidate_rule_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_rule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_rule_id: Mapped[int | None] = mapped_column(Integer)
    source_demand_list_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_ref: Mapped[str | None] = mapped_column(String(128))
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    inventory_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            *SIMULATION_STATUSES,
            name="allocationsimulationstatus",
            native_enum=False,
            create_constraint=True,
            length=16,
        ),
        nullable=False,
        default="PENDING",
    )
    blockers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)


class AllocationSimulationResult(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "allocation_simulation_results"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_allocation_simulation_result_tenant_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "simulation_id"],
            ["allocation_simulations.tenant_id", "allocation_simulations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "candidate_balance_id"],
            ["inventory_balances.tenant_id", "inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "baseline_rank IS NULL OR baseline_rank >= 1",
            name="ck_allocation_simulation_result_baseline_rank",
        ),
        CheckConstraint(
            "candidate_rank IS NULL OR candidate_rank >= 1",
            name="ck_allocation_simulation_result_candidate_rank",
        ),
        Index(
            "ix_allocation_simulation_results_tenant_simulation",
            "tenant_id",
            "simulation_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_list_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_balance_id: Mapped[int | None] = mapped_column(Integer)
    baseline_rank: Mapped[int | None] = mapped_column(Integer)
    candidate_rank: Mapped[int | None] = mapped_column(Integer)
    baseline_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    candidate_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    score_delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class AllocationPlan(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "allocation_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_allocation_plan_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_allocation_plan_tenant_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_allocation_plan_version"),
        CheckConstraint(
            "source_demand_list_version >= 1",
            name="ck_allocation_plan_source_version",
        ),
        Index("ix_allocation_plans_tenant_status", "tenant_id", "status"),
        Index(
            "ix_allocation_plans_tenant_source",
            "tenant_id",
            "source_demand_list_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_demand_list_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_demand_list_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            *PLAN_STATUSES,
            name="allocationplanstatus",
            native_enum=False,
            create_constraint=True,
            length=24,
        ),
        nullable=False,
        default="DRAFT",
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AllocationPlanLine(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "allocation_plan_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_allocation_plan_line_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "plan_id"],
            ["allocation_plans.tenant_id", "allocation_plans.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "recommended_balance_id"],
            ["inventory_balances.tenant_id", "inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["inventory_reservations.tenant_id", "inventory_reservations.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_allocation_plan_line_version"),
        CheckConstraint(
            "demand_quantity >= 0",
            name="ck_allocation_plan_line_demand_nonnegative",
        ),
        CheckConstraint(
            "allocated_quantity >= 0",
            name="ck_allocation_plan_line_allocated_nonnegative",
        ),
        CheckConstraint(
            "gap_quantity >= 0",
            name="ck_allocation_plan_line_gap_nonnegative",
        ),
        CheckConstraint(
            "expected_balance_version >= 1",
            name="ck_allocation_plan_line_expected_balance_version",
        ),
        Index("ix_allocation_plan_lines_tenant_plan", "tenant_id", "plan_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_list_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    spare_part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_balance_id: Mapped[int | None] = mapped_column(Integer)
    recommended_lot_id: Mapped[int | None] = mapped_column(Integer)
    recommended_serial_item_id: Mapped[int | None] = mapped_column(Integer)
    demand_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    gap_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    risks_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    manual_override_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expected_balance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reservation_id: Mapped[int | None] = mapped_column(Integer)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AllocationPlanEvent(Base, TenantScopedMixin):
    __tablename__ = "allocation_plan_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "plan_id"],
            ["allocation_plans.tenant_id", "allocation_plans.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_allocation_plan_events_tenant_plan", "tenant_id", "plan_id"),
        Index("ix_allocation_plan_events_tenant_request", "tenant_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    before_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
