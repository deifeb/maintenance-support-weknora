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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    CalculationDecisionType,
    DemandExecutionMode,
    DemandListEventType,
    DemandListStatus,
    ReliabilityModelType,
)
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
    utc_now,
)


class DemandList(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "demand_lists"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    lineage_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    derived_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_lists.id", ondelete="RESTRICT"),
        index=True,
    )
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "demand_scenario_versions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    calculation_group_id: Mapped[int] = mapped_column(
        ForeignKey(
            "calculation_groups.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[DemandListStatus] = mapped_column(
        Enum(
            DemandListStatus,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=DemandListStatus.DRAFT,
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_lists.id", ondelete="SET NULL"),
        index=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_by_request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    submitted_by_user_id: Mapped[str | None] = mapped_column(String(64))
    submitted_by_request_id: Mapped[str | None] = mapped_column(
        String(128)
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    confirmed_by_user_id: Mapped[str | None] = mapped_column(String(64))
    confirmed_by_request_id: Mapped[str | None] = mapped_column(
        String(128)
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    published_by_user_id: Mapped[str | None] = mapped_column(String(64))
    published_by_request_id: Mapped[str | None] = mapped_column(
        String(128)
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    voided_by_user_id: Mapped[str | None] = mapped_column(String(64))
    voided_by_request_id: Mapped[str | None] = mapped_column(String(128))
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    items: Mapped[list["DemandListItem"]] = relationship(
        back_populates="demand_list",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["DemandListEvent"]] = relationship(
        back_populates="demand_list",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "lineage_id",
            "version_number",
            name="uq_demand_list_lineage_version",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_demand_list_version_number",
        ),
        Index(
            "uq_demand_lists_tenant_id_id",
            "tenant_id",
            "id",
            unique=True,
        ),
        Index(
            "uq_demand_lists_current_published_lineage",
            "tenant_id",
            "lineage_id",
            unique=True,
            sqlite_where=text(
                "status = 'PUBLISHED' AND is_current = 1"
            ),
            postgresql_where=text(
                "status = 'PUBLISHED' AND is_current"
            ),
        ),
    )


class DemandListItem(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "demand_list_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    demand_list_id: Mapped[int] = mapped_column(
        ForeignKey("demand_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    spare_part_code_snapshot: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    spare_part_name_snapshot: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    spare_part_unit_snapshot: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    criticality_level_snapshot: Mapped[str | None] = mapped_column(
        String(20)
    )
    source_calculation_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculation_groups.id", ondelete="RESTRICT"),
        index=True,
    )
    source_group_child_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "calculation_group_children.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    source_calculation_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculations.id", ondelete="RESTRICT"),
        index=True,
    )
    source_calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "demand_calculation_runs.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    source_result_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "demand_run_item_results.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    reliability_model: Mapped[ReliabilityModelType | None] = mapped_column(
        Enum(
            ReliabilityModelType,
            native_enum=False,
            length=32,
        )
    )
    execution_mode: Mapped[DemandExecutionMode | None] = mapped_column(
        Enum(
            DemandExecutionMode,
            native_enum=False,
            length=20,
        )
    )
    original_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )
    final_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )
    decision_type: Mapped[CalculationDecisionType | None] = mapped_column(
        Enum(
            CalculationDecisionType,
            native_enum=False,
            length=32,
        )
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decision_risk: Mapped[str | None] = mapped_column(String(20))
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
    risk_rule_version: Mapped[str | None] = mapped_column(String(64))
    source_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    decision_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    interval_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    parameter_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    warning_snapshot_json: Mapped[list[str] | None] = mapped_column(JSON)
    inventory_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    demand_list: Mapped[DemandList] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "demand_list_id",
            "spare_part_id",
            name="uq_demand_list_item",
        ),
        Index(
            "uq_demand_list_items_tenant_id_id",
            "tenant_id",
            "id",
            unique=True,
        ),
        CheckConstraint(
            "original_quantity >= 0",
            name="ck_demand_list_item_original_quantity",
        ),
        CheckConstraint(
            "final_quantity >= 0",
            name="ck_demand_list_item_final_quantity",
        ),
    )


class DemandListEvent(Base, TenantScopedMixin):
    __tablename__ = "demand_list_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    demand_list_id: Mapped[int] = mapped_column(
        ForeignKey("demand_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[DemandListEventType] = mapped_column(
        Enum(
            DemandListEventType,
            native_enum=False,
            length=32,
        ),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    actor_roles_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    before_summary_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    after_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    demand_list: Mapped[DemandList] = relationship(back_populates="events")

    __table_args__ = (
        Index(
            "uq_demand_list_events_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )
