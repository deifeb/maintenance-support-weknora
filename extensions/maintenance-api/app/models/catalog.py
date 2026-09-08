from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import (
    ActiveMixin,
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from app.models.equipment import ConfigurationItem
    from app.models.reliability import ReliabilityProfile
    from app.models.supplier import SupplierOffer


class Part(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    ActiveMixin,
    TimestampMixin,
):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    part_type: Mapped[str | None] = mapped_column(String(100))
    specification: Mapped[str | None] = mapped_column(String(500))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(32), default="件", nullable=False)
    drawing_number: Mapped[str | None] = mapped_column(String(100))
    maintenance_level: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    configuration_items: Mapped[list["ConfigurationItem"]] = relationship(back_populates="part")

    __table_args__ = (
        Index(
            "uq_parts_tenant_code",
            "tenant_id",
            "code",
            unique=True,
        ),
    )


class SparePart(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    ActiveMixin,
    TimestampMixin,
):
    __tablename__ = "spare_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    specification: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="件")
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    material_code: Mapped[str | None] = mapped_column(String(100))
    national_standard: Mapped[str | None] = mapped_column(String(100))
    shelf_life_months: Mapped[int | None] = mapped_column(Integer)
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_repairable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_service_level: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    description: Mapped[str | None] = mapped_column(Text)

    configuration_items: Mapped[list["ConfigurationItem"]] = relationship(
        back_populates="spare_part"
    )
    reliability_profiles: Mapped[list["ReliabilityProfile"]] = relationship(
        back_populates="spare_part"
    )
    supplier_offers: Mapped[list["SupplierOffer"]] = relationship(back_populates="spare_part")

    __table_args__ = (
        Index(
            "uq_spare_parts_tenant_code",
            "tenant_id",
            "code",
            unique=True,
        ),
        CheckConstraint(
            "shelf_life_months IS NULL OR shelf_life_months >= 0",
            name="ck_spare_shelf_life_nonnegative",
        ),
        CheckConstraint(
            "default_service_level IS NULL OR (default_service_level > 0 AND default_service_level <= 1)",
            name="ck_spare_default_service_level",
        ),
    )
