from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
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
        Enum(*LOT_QUALITY_STATUSES, name="inventorylotqualitystatus", native_enum=False, length=16),
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
        Enum(*SERIAL_ITEM_STATUSES, name="serializeditemstatus", native_enum=False, length=24),
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
        Enum(*TRANSACTION_STATUSES, name="inventorytransactionstatus", native_enum=False, length=24),
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
