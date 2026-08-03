from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import WarehouseStatus
from app.models.mixins import (
    ActiveMixin,
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from app.models.catalog import SparePart
    from app.models.inventory_ledger import WarehouseLocation


class Warehouse(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    ActiveMixin,
    TimestampMixin,
):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    warehouse_type: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(500))
    organization: Mapped[str | None] = mapped_column(String(200))
    responsible_person: Mapped[str | None] = mapped_column(String(100))
    contact: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[WarehouseStatus] = mapped_column(
        Enum(WarehouseStatus, native_enum=False, length=20),
        nullable=False,
        default=WarehouseStatus.NORMAL,
    )
    description: Mapped[str | None] = mapped_column(Text)

    locations: Mapped[list["WarehouseLocation"]] = relationship(back_populates="warehouse")

    __table_args__ = (
        Index(
            "uq_warehouses_tenant_code",
            "tenant_id",
            "code",
            unique=True,
        ),
    )


class WarehouseInventory(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "warehouse_inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    damaged_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    quarantined_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    in_transit_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    last_counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    warehouse: Mapped[Warehouse] = relationship()
    spare_part: Mapped["SparePart"] = relationship()

    @hybrid_property
    def available_quantity(self) -> Decimal:
        return (
            self.on_hand_quantity
            - self.reserved_quantity
            - self.damaged_quantity
            - self.quarantined_quantity
        )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "spare_part_id", name="uq_inventory_warehouse_spare"),
        CheckConstraint("on_hand_quantity >= 0", name="ck_inventory_on_hand_nonnegative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved_nonnegative"),
        CheckConstraint("damaged_quantity >= 0", name="ck_inventory_damaged_nonnegative"),
        CheckConstraint("quarantined_quantity >= 0", name="ck_inventory_quarantined_nonnegative"),
        CheckConstraint("in_transit_quantity >= 0", name="ck_inventory_in_transit_nonnegative"),
        CheckConstraint("safety_stock >= 0", name="ck_inventory_safety_nonnegative"),
        CheckConstraint("reorder_point >= 0", name="ck_inventory_reorder_nonnegative"),
        CheckConstraint(
            "maximum_stock IS NULL OR maximum_stock >= 0", name="ck_inventory_max_nonnegative"
        ),
        CheckConstraint(
            "reserved_quantity + damaged_quantity + quarantined_quantity <= on_hand_quantity",
            name="ck_inventory_allocated_not_exceed_on_hand",
        ),
        CheckConstraint("reorder_point >= safety_stock", name="ck_inventory_reorder_ge_safety"),
        CheckConstraint(
            "maximum_stock IS NULL OR maximum_stock >= reorder_point",
            name="ck_inventory_max_ge_reorder",
        ),
    )
