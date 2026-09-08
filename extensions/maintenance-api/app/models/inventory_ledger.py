from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, VersionedMixin

if TYPE_CHECKING:
    from app.models.inventory import Warehouse


TRANSACTION_STATUSES = (
    "PREVIEWED",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "EXPIRED",
    "REVERSED",
)
RESERVATION_STATUSES = (
    "ACTIVE",
    "PARTIALLY_ISSUED",
    "FULFILLED",
    "RELEASED",
    "CANCELLED",
    "EXPIRED",
)
TRANSFER_STATUSES = (
    "DRAFT",
    "DISPATCHED",
    "PARTIALLY_RECEIVED",
    "COMPLETED",
    "CANCELLED",
)
STOCKTAKE_STATUSES = (
    "DRAFT",
    "COUNTING",
    "REVIEWING",
    "CONFIRMED",
    "CONFLICTED",
    "CANCELLED",
)
STOCKTAKE_LINE_RESOLUTIONS = (
    "PENDING",
    "ADJUSTED",
    "CONFLICTED",
    "RECOUNT_REQUIRED",
    "BASELINE_ACCEPTED",
)


class InventoryTargetReceiptStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
LOT_QUALITY_STATUSES = ("AVAILABLE", "QUARANTINED", "DAMAGED", "REJECTED")
EXPIRY_RULE_SCOPE_TYPES = ("TENANT", "CATEGORY", "SPARE_PART")
SERIAL_ITEM_STATUSES = (
    "IN_STOCK",
    "RESERVED",
    "ISSUED",
    "INSTALLED",
    "AWAITING_REPAIR",
    "IN_REPAIR",
    "REPAIRED",
    "SCRAPPED",
    "FROZEN",
)


class WarehouseLocation(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "warehouse_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_warehouse_location_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_pickable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    warehouse: Mapped["Warehouse"] = relationship(back_populates="locations")
    balances: Mapped[list["InventoryBalance"]] = relationship(back_populates="location")


class InventoryPolicy(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "inventory_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "warehouse_id", "spare_part_id", name="uq_inventory_policy_warehouse_spare"
        ),
        CheckConstraint("safety_stock >= 0", name="ck_inventory_policy_safety_nonnegative"),
        CheckConstraint("reorder_point >= 0", name="ck_inventory_policy_reorder_nonnegative"),
        CheckConstraint(
            "maximum_stock IS NULL OR maximum_stock >= 0", name="ck_inventory_policy_max_nonnegative"
        ),
        CheckConstraint("reorder_point >= safety_stock", name="ck_inventory_policy_reorder_ge_safety"),
        CheckConstraint(
            "maximum_stock IS NULL OR maximum_stock >= reorder_point",
            name="ck_inventory_policy_max_ge_reorder",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    notes: Mapped[str | None] = mapped_column(Text)


class InventoryExpiryRule(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "inventory_expiry_rules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scope_type", "category", "spare_part_id", name="uq_inventory_expiry_rule_scope"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(
        Enum(
            *EXPIRY_RULE_SCOPE_TYPES,
            name="inventoryexpiryrulescopetype",
            native_enum=False,
            create_constraint=True,
            length=16,
        ),
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(100))
    spare_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT")
    )
    warning_days_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class InventoryLot(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "spare_part_id", "lot_code", name="uq_inventory_lot_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_code: Mapped[str] = mapped_column(String(128), nullable=False)
    manufacture_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quality_status: Mapped[str] = mapped_column(
        Enum(*LOT_QUALITY_STATUSES, name="inventorylotqualitystatus", native_enum=False, create_constraint=True, length=16),
        nullable=False,
        default="AVAILABLE",
    )
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    freeze_reason: Mapped[str | None] = mapped_column(String(500))


class SerializedItem(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "serialized_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "serial_number", name="uq_serialized_item_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_lots.id", ondelete="RESTRICT"))
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*SERIAL_ITEM_STATUSES, name="serializeditemstatus", native_enum=False, create_constraint=True, length=24),
        nullable=False,
        default="IN_STOCK",
    )
    equipment_id: Mapped[int | None] = mapped_column(Integer)
    installation_position: Mapped[str | None] = mapped_column(String(128))


class InventoryBalance(Base, TenantScopedMixin, VersionedMixin, TimestampMixin):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "warehouse_id", "location_id", "spare_part_id", "lot_id",
            name="uq_inventory_balance_identity",
        ),
        Index(
            "uq_inventory_balances_tenant_id_id",
            "tenant_id",
            "id",
            unique=True,
        ),
        Index(
            "uq_inventory_balance_default_identity",
            "tenant_id",
            "warehouse_id",
            "location_id",
            "spare_part_id",
            unique=True,
            sqlite_where=text("lot_id IS NULL"),
            postgresql_where=text("lot_id IS NULL"),
        ),
        CheckConstraint("on_hand_quantity >= 0", name="ck_inventory_balance_on_hand_nonnegative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_inventory_balance_reserved_nonnegative"),
        CheckConstraint("damaged_quantity >= 0", name="ck_inventory_balance_damaged_nonnegative"),
        CheckConstraint("quarantined_quantity >= 0", name="ck_inventory_balance_quarantined_nonnegative"),
        CheckConstraint("in_transit_quantity >= 0", name="ck_inventory_balance_in_transit_nonnegative"),
        CheckConstraint(
            "reserved_quantity + damaged_quantity + quarantined_quantity <= on_hand_quantity",
            name="ck_inventory_balance_allocated_not_exceed_on_hand",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_lots.id", ondelete="RESTRICT"))
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    damaged_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    quarantined_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    in_transit_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    location: Mapped[WarehouseLocation] = relationship(back_populates="balances")

    @hybrid_property
    def available_quantity(self) -> Decimal:
        return (
            self.on_hand_quantity
            - self.reserved_quantity
            - self.damaged_quantity
            - self.quarantined_quantity
        )


class InventoryTransaction(Base, TimestampMixin):
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "operation_type", "idempotency_key",
            name="uq_inventory_tx_tenant_operation_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*TRANSACTION_STATUSES, name="inventorytransactionstatus", native_enum=False, create_constraint=True, length=24),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reversed_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryTargetReceipt(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "inventory_target_receipts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_inventory_target_receipt_tenant_key",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'COMPLETED')",
            name="ck_inventory_target_receipt_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND result_json IS NULL AND completed_at IS NULL) "
            "OR (status = 'COMPLETED' AND result_json IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_inventory_target_receipt_state",
        ),
        CheckConstraint(
            "length(source_hash) = 64",
            name="ck_inventory_target_receipt_source_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[InventoryTargetReceiptStatus] = mapped_column(
        Enum(
            InventoryTargetReceiptStatus,
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=InventoryTargetReceiptStatus.PENDING,
    )
    result_json: Mapped[dict | None] = mapped_column(JSON)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryLedgerEntry(Base, TimestampMixin):
    __tablename__ = "inventory_ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    balance_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_balances.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lot_id: Mapped[int | None] = mapped_column(Integer)
    serial_item_id: Mapped[int | None] = mapped_column(Integer)
    on_hand_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    damaged_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    quarantined_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    in_transit_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    state_before_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_after_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    before_balance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_balance_version: Mapped[int] = mapped_column(Integer, nullable=False)


class InventoryReservation(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_reservation_tenant_id",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'PARTIALLY_ISSUED', 'FULFILLED', "
            "'RELEASED', 'CANCELLED', 'EXPIRED')",
            name="ck_inventory_reservation_status",
        ),
        Index(
            "ix_inventory_reservations_tenant_status_expires",
            "tenant_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_partial: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)


class InventoryReservationLine(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "inventory_reservation_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["inventory_reservations.tenant_id", "inventory_reservations.id"],
            name="fk_inventory_reservation_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "requested_quantity >= 0",
            name="ck_inventory_reservation_line_requested_nonnegative",
        ),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_inventory_reservation_line_reserved_nonnegative",
        ),
        CheckConstraint(
            "issued_quantity >= 0",
            name="ck_inventory_reservation_line_issued_nonnegative",
        ),
        CheckConstraint(
            "released_quantity >= 0",
            name="ck_inventory_reservation_line_released_nonnegative",
        ),
        CheckConstraint(
            "ROUND(issued_quantity + released_quantity, 4) <= "
            "ROUND(reserved_quantity, 4)",
            name="ck_inventory_reservation_line_lifecycle",
        ),
        CheckConstraint(
            "serial_item_id IS NULL OR ("
            "requested_quantity IN (0, 1) AND "
            "reserved_quantity IN (0, 1) AND "
            "issued_quantity IN (0, 1) AND "
            "released_quantity IN (0, 1))",
            name="ck_inventory_reservation_line_serial_quantities",
        ),
        Index(
            "ix_inventory_reservation_lines_tenant_reservation",
            "tenant_id",
            "reservation_id",
        ),
        Index(
            "ix_inventory_reservation_lines_tenant_balance",
            "tenant_id",
            "balance_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    balance_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_balances.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_lots.id", ondelete="RESTRICT")
    )
    serial_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("serialized_items.id", ondelete="RESTRICT")
    )
    requested_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    issued_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default=text("0")
    )
    released_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default=text("0")
    )
    expected_balance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    fefo_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    fefo_override_reason: Mapped[str | None] = mapped_column(String(500))
    recommended_selection_json: Mapped[dict | None] = mapped_column(JSON)
    actual_selection_json: Mapped[dict | None] = mapped_column(JSON)


class InventoryTransfer(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "inventory_transfers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_transfer_tenant_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'DISPATCHED', 'PARTIALLY_RECEIVED', "
            "'COMPLETED', 'CANCELLED')",
            name="ck_inventory_transfer_status",
        ),
        CheckConstraint(
            "source_location_id <> target_location_id",
            name="ck_inventory_transfer_distinct_locations",
        ),
        Index(
            "ix_inventory_transfers_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    source_warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_location_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_location_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryTransferLine(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "inventory_transfer_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["inventory_transfers.tenant_id", "inventory_transfers.id"],
            name="fk_inventory_transfer_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "requested_quantity >= 0",
            name="ck_inventory_transfer_line_requested_nonnegative",
        ),
        CheckConstraint(
            "dispatched_quantity >= 0",
            name="ck_inventory_transfer_line_dispatched_nonnegative",
        ),
        CheckConstraint(
            "received_quantity >= 0",
            name="ck_inventory_transfer_line_received_nonnegative",
        ),
        CheckConstraint(
            "dispatched_quantity <= requested_quantity",
            name="ck_inventory_transfer_line_dispatch_lifecycle",
        ),
        CheckConstraint(
            "received_quantity <= dispatched_quantity",
            name="ck_inventory_transfer_line_receive_lifecycle",
        ),
        CheckConstraint(
            "serial_item_id IS NULL OR ("
            "requested_quantity IN (0, 1) AND "
            "dispatched_quantity IN (0, 1) AND "
            "received_quantity IN (0, 1))",
            name="ck_inventory_transfer_line_serial_quantities",
        ),
        Index(
            "ix_inventory_transfer_lines_tenant_transfer",
            "tenant_id",
            "transfer_id",
        ),
        Index(
            "ix_inventory_transfer_lines_source_balance",
            "source_balance_id",
        ),
        Index(
            "ix_inventory_transfer_lines_target_balance",
            "target_balance_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transfer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_balance_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_balances.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_balance_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_balances.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_lots.id", ondelete="RESTRICT")
    )
    serial_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("serialized_items.id", ondelete="RESTRICT")
    )
    requested_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    dispatched_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default=text("0")
    )
    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, server_default=text("0")
    )
    expected_source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_target_version: Mapped[int] = mapped_column(Integer, nullable=False)


class InventoryStocktake(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "stocktakes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_stocktake_tenant_id",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'COUNTING', 'REVIEWING', 'CONFIRMED', "
            "'CONFLICTED', 'CANCELLED')",
            name="ck_inventory_stocktake_status",
        ),
        Index(
            "ix_stocktakes_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryStocktakeLine(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "stocktake_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "stocktake_id"],
            ["stocktakes.tenant_id", "stocktakes.id"],
            name="fk_inventory_stocktake_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "system_quantity >= 0",
            name="ck_inventory_stocktake_line_system_nonnegative",
        ),
        CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name="ck_inventory_stocktake_line_counted_nonnegative",
        ),
        CheckConstraint(
            "resolution IN ('PENDING', 'ADJUSTED', 'CONFLICTED', "
            "'RECOUNT_REQUIRED', 'BASELINE_ACCEPTED')",
            name="ck_inventory_stocktake_line_resolution",
        ),
        CheckConstraint(
            "(counted_quantity IS NULL AND variance_quantity IS NULL) OR "
            "(counted_quantity IS NOT NULL AND "
            "ROUND(variance_quantity, 4) = "
            "ROUND(counted_quantity - system_quantity, 4))",
            name="ck_inventory_stocktake_line_variance",
        ),
        Index(
            "ix_stocktake_lines_tenant_stocktake",
            "tenant_id",
            "stocktake_id",
        ),
        Index("ix_stocktake_lines_balance", "balance_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stocktake_id: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_balances.id", ondelete="RESTRICT"),
        nullable=False,
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_lots.id", ondelete="RESTRICT")
    )
    serial_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("serialized_items.id", ondelete="RESTRICT")
    )
    system_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    counted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    variance_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    snapshot_balance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    resolution: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    conflict_details_json: Mapped[dict | None] = mapped_column(JSON)
