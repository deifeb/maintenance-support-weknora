from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    CalculationDecisionType,
    CalculationGroupStatus,
    DemandExecutionMode,
    ReliabilityModelType,
)
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
    utc_now,
)


class CalculationGroup(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "calculation_groups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "demand_scenario_versions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[CalculationGroupStatus] = mapped_column(
        Enum(
            CalculationGroupStatus,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=CalculationGroupStatus.PENDING,
        index=True,
    )
    primary_candidate_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    recommendation_snapshot_json: Mapped[
        dict[str, Any]
    ] = mapped_column(JSON, nullable=False)
    parameter_snapshot_json: Mapped[
        dict[str, Any]
    ] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
    )
    request_hash: Mapped[str | None] = mapped_column(
        String(64),
    )
    last_event_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_by_request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    children: Mapped[list["CalculationGroupChild"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["CalculationGroupEvent"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[
        list["CalculationItemDecision"]
    ] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "uq_calculation_groups_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
        ),
        CheckConstraint(
            "last_event_sequence >= 0",
            name="ck_calculation_group_event_sequence",
        ),
    )


class CalculationGroupChild(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "calculation_group_children"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_groups.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    candidate_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    reliability_model: Mapped[
        ReliabilityModelType
    ] = mapped_column(
        Enum(
            ReliabilityModelType,
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    execution_mode: Mapped[
        DemandExecutionMode
    ] = mapped_column(
        Enum(
            DemandExecutionMode,
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    calculation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "demand_calculations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    is_current_attempt: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    selection_reason: Mapped[str | None] = mapped_column(
        Text,
    )
    group: Mapped[CalculationGroup] = relationship(
        back_populates="children",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "group_id",
            "candidate_key",
            "attempt_number",
            name="uq_calculation_group_child_attempt",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_calculation_group_child_attempt",
        ),
    )


class CalculationGroupEvent(
    Base,
    TenantScopedMixin,
):
    __tablename__ = "calculation_group_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_groups.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "calculation_group_children.id",
            ondelete="SET NULL",
        ),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    group: Mapped[CalculationGroup] = relationship(
        back_populates="events",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "group_id",
            "sequence",
            name="uq_calculation_group_event_sequence",
        ),
        CheckConstraint(
            "sequence >= 1",
            name="ck_calculation_group_event_sequence_positive",
        ),
    )


class CalculationItemDecision(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "calculation_item_decisions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_groups.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey(
            "spare_parts.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    source_child_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_group_children.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    selected_child_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_group_children.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    original_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )
    final_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )
    decision_type: Mapped[
        CalculationDecisionType
    ] = mapped_column(
        Enum(
            CalculationDecisionType,
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    requires_admin_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    confirmed_by_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    risk_rule_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    decided_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    decided_by_request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    group: Mapped[CalculationGroup] = relationship(
        back_populates="decisions",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "group_id",
            "spare_part_id",
            name="uq_calculation_item_decision",
        ),
        CheckConstraint(
            "original_quantity >= 0",
            name="ck_calculation_decision_original_quantity",
        ),
        CheckConstraint(
            "final_quantity >= 0",
            name="ck_calculation_decision_final_quantity",
        ),
    )
