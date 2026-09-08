from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewEventType,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
    utc_now,
)


class DemandReview(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "demand_list_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_demand_list_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_demand_list_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_lineage_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DemandReviewStatus] = mapped_column(
        Enum(
            DemandReviewStatus,
            name="demandreviewstatus",
            native_enum=False,
            create_constraint=True,
            length=32,
        ),
        nullable=False,
        default=DemandReviewStatus.CREATED,
    )
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    total_finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_finding_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pending_finding_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pending_blocking_finding_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    derived_demand_list_id: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_summary: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_demand_list_review_tenant_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "derived_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_demand_review_version"),
        CheckConstraint(
            "source_demand_list_version >= 1",
            name="ck_demand_review_source_version",
        ),
        CheckConstraint(
            "source_version_number >= 1",
            name="ck_demand_review_source_version_number",
        ),
        CheckConstraint(
            "total_finding_count >= 0",
            name="ck_demand_review_total_count",
        ),
        CheckConstraint(
            "blocking_finding_count >= 0",
            name="ck_demand_review_blocking_count",
        ),
        CheckConstraint(
            "pending_finding_count >= 0",
            name="ck_demand_review_pending_count",
        ),
        CheckConstraint(
            "pending_blocking_finding_count >= 0",
            name="ck_demand_review_pending_blocking_count",
        ),
        CheckConstraint(
            "blocking_finding_count <= total_finding_count",
            name="ck_demand_review_blocking_le_total",
        ),
        CheckConstraint(
            "pending_finding_count <= total_finding_count",
            name="ck_demand_review_pending_le_total",
        ),
        CheckConstraint(
            "pending_blocking_finding_count <= blocking_finding_count "
            "AND pending_blocking_finding_count <= pending_finding_count",
            name="ck_demand_review_pending_blocking_bounds",
        ),
        CheckConstraint(
            "(status = 'DERIVED' AND derived_demand_list_id IS NOT NULL) "
            "OR (status <> 'DERIVED' AND derived_demand_list_id IS NULL)",
            name="ck_demand_review_derived_state",
        ),
        CheckConstraint(
            "status = 'FAILED' OR "
            "(failure_code IS NULL AND failure_summary IS NULL)",
            name="ck_demand_review_failure_state",
        ),
        Index(
            "ix_demand_list_reviews_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_demand_list_reviews_tenant_source",
            "tenant_id",
            "source_demand_list_id",
        ),
    )


class DemandReviewFinding(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "demand_list_review_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_key: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[DemandReviewSeverity] = mapped_column(
        Enum(
            DemandReviewSeverity,
            name="demandreviewseverity",
            native_enum=False,
            create_constraint=True,
            length=16,
        ),
        nullable=False,
    )
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_admin_acceptance: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    source_demand_list_item_id: Mapped[int | None] = mapped_column(Integer)
    effect_key: Mapped[str | None] = mapped_column(String(200))
    evidence_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    suggestion_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision_status: Mapped[DemandReviewDecisionStatus] = mapped_column(
        Enum(
            DemandReviewDecisionStatus,
            name="demandreviewdecisionstatus",
            native_enum=False,
            create_constraint=True,
            length=24,
        ),
        nullable=False,
        default=DemandReviewDecisionStatus.PENDING,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_demand_list_review_finding_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "review_id",
            "finding_key",
            name="uq_demand_review_finding_key",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_demand_review_finding_version"),
        Index(
            "uq_demand_review_finding_effect",
            "tenant_id",
            "review_id",
            "effect_key",
            unique=True,
            sqlite_where=text("effect_key IS NOT NULL"),
            postgresql_where=text("effect_key IS NOT NULL"),
        ),
        Index(
            "ix_demand_review_findings_tenant_review",
            "tenant_id",
            "review_id",
        ),
    )


class DemandReviewDecision(Base, TenantScopedMixin):
    __tablename__ = "demand_list_review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    final_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    review_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    before_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            [
                "demand_list_review_findings.tenant_id",
                "demand_list_review_findings.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('ACCEPTED', 'REJECTED', 'EDIT_ACCEPTED')",
            name="ck_demand_review_decision_action",
        ),
        CheckConstraint(
            "suggested_quantity IS NULL OR suggested_quantity >= 0",
            name="ck_demand_review_decision_suggested_quantity",
        ),
        CheckConstraint(
            "final_quantity IS NULL OR final_quantity >= 0",
            name="ck_demand_review_decision_final_quantity",
        ),
        Index(
            "ix_demand_review_decisions_tenant_review",
            "tenant_id",
            "review_id",
        ),
        Index(
            "ix_demand_review_decisions_tenant_finding",
            "tenant_id",
            "finding_id",
        ),
    )


class DemandReviewEvent(Base, TenantScopedMixin):
    __tablename__ = "demand_list_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[DemandReviewEventType] = mapped_column(
        Enum(
            DemandReviewEventType,
            name="demandrevieweventtype",
            native_enum=False,
            create_constraint=True,
            length=24,
        ),
        nullable=False,
    )
    command_type: Mapped[DemandReviewCommandType | None] = mapped_column(
        Enum(
            DemandReviewCommandType,
            name="demandreviewcommandtype",
            native_enum=False,
            create_constraint=True,
            length=24,
        )
    )
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    before_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(command_type IS NULL AND idempotency_key IS NULL) OR "
            "(command_type IS NOT NULL AND idempotency_key IS NOT NULL "
            "AND request_hash IS NOT NULL)",
            name="ck_demand_review_event_command_receipt",
        ),
        Index(
            "uq_demand_review_event_command_key",
            "tenant_id",
            "command_type",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_demand_review_events_tenant_review",
            "tenant_id",
            "review_id",
        ),
    )
