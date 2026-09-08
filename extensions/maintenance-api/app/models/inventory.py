from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum,
    Index,
    Integer,
    String,
    Text,
)
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
