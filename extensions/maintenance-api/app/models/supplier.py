from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
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
    from app.models.catalog import SparePart


class Supplier(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    ActiveMixin,
    TimestampMixin,
):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_type: Mapped[str | None] = mapped_column(String(100))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    credit_code: Mapped[str | None] = mapped_column(String(100))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    qualification_status: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    offers: Mapped[list["SupplierOffer"]] = relationship(back_populates="supplier")

    __table_args__ = (
        Index(
            "uq_suppliers_tenant_code",
            "tenant_id",
            "code",
            unique=True,
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 100)", name="ck_supplier_rating"
        ),
    )


class SupplierOffer(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    ActiveMixin,
    TimestampMixin,
):
    __tablename__ = "supplier_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    offer_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    price_includes_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_order_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=1
    )
    order_multiple: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=1)
    maximum_supply_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    warranty_months: Mapped[int | None] = mapped_column(Integer)
    quality_level: Mapped[str | None] = mapped_column(String(100))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped[Supplier] = relationship(back_populates="offers")
    spare_part: Mapped["SparePart"] = relationship(back_populates="supplier_offers")

    __table_args__ = (
        Index(
            "uq_supplier_offers_tenant_offer_code",
            "tenant_id",
            "offer_code",
            unique=True,
        ),
        CheckConstraint("unit_price >= 0", name="ck_offer_price_nonnegative"),
        CheckConstraint(
            "tax_rate IS NULL OR (tax_rate >= 0 AND tax_rate <= 1)", name="ck_offer_tax_rate"
        ),
        CheckConstraint("lead_time_days >= 0", name="ck_offer_lead_time_nonnegative"),
        CheckConstraint("minimum_order_quantity >= 0", name="ck_offer_min_order_nonnegative"),
        CheckConstraint("order_multiple > 0", name="ck_offer_order_multiple_positive"),
        CheckConstraint(
            "maximum_supply_quantity IS NULL OR maximum_supply_quantity >= 0",
            name="ck_offer_max_supply_nonnegative",
        ),
        CheckConstraint(
            "warranty_months IS NULL OR warranty_months >= 0", name="ck_offer_warranty_nonnegative"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_offer_date_order",
        ),
    )
