from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from app.models.enums import ConfigurationStatus, CriticalityLevel
from app.models.mixins import ActiveMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.catalog import Part, SparePart
    from app.models.reliability import ReliabilityProfile


class EquipmentModel(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "equipment_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model_series: Mapped[str | None] = mapped_column(String(100))
    service_life_years: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column(Text)

    configuration_versions: Mapped[list["ConfigurationVersion"]] = relationship(
        back_populates="equipment_model", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "service_life_years IS NULL OR service_life_years >= 0",
            name="ck_equipment_service_life_nonnegative",
        ),
    )


class ConfigurationVersion(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "configuration_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_model_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_models.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConfigurationStatus] = mapped_column(
        Enum(ConfigurationStatus, native_enum=False, length=20),
        nullable=False,
        default=ConfigurationStatus.DRAFT,
        index=True,
    )
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)

    equipment_model: Mapped[EquipmentModel] = relationship(back_populates="configuration_versions")
    items: Mapped[list["ConfigurationItem"]] = relationship(
        back_populates="configuration_version",
        cascade="all, delete-orphan",
        foreign_keys="ConfigurationItem.configuration_version_id",
    )
    reliability_profiles: Mapped[list["ReliabilityProfile"]] = relationship(
        back_populates="configuration_version"
    )

    __table_args__ = (
        UniqueConstraint(
            "equipment_model_id",
            "version_code",
            name="uq_configuration_equipment_version",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR effective_date IS NULL OR expiry_date > effective_date",
            name="ck_configuration_date_order",
        ),
        Index(
            "uq_configuration_active_default",
            "equipment_model_id",
            unique=True,
            sqlite_where=text("is_default = 1 AND is_active = 1 AND status = 'PUBLISHED'"),
            postgresql_where=text("is_default IS TRUE AND is_active IS TRUE AND status = 'PUBLISHED'"),
        ),
    )


class ConfigurationItem(Base, TimestampMixin):
    __tablename__ = "configuration_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    configuration_version_id: Mapped[int] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_items.id", ondelete="RESTRICT"), index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), index=True
    )
    install_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    position_code: Mapped[str | None] = mapped_column(String(100))
    position_name: Mapped[str | None] = mapped_column(String(200))
    criticality_level: Mapped[CriticalityLevel] = mapped_column(
        Enum(CriticalityLevel, native_enum=False, length=20),
        nullable=False,
        default=CriticalityLevel.MEDIUM,
    )
    replacement_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("1")
    )
    maintenance_level: Mapped[str | None] = mapped_column(String(64))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    configuration_version: Mapped[ConfigurationVersion] = relationship(
        back_populates="items", foreign_keys=[configuration_version_id]
    )
    parent: Mapped["ConfigurationItem | None"] = relationship(
        remote_side="ConfigurationItem.id",
        back_populates="children",
        foreign_keys=[parent_item_id],
    )
    children: Mapped[list["ConfigurationItem"]] = relationship(
        back_populates="parent", foreign_keys=[parent_item_id]
    )
    part: Mapped["Part"] = relationship(back_populates="configuration_items")
    spare_part: Mapped["SparePart | None"] = relationship(back_populates="configuration_items")

    __table_args__ = (
        UniqueConstraint(
            "configuration_version_id", "item_code", name="uq_configuration_item_code"
        ),
        CheckConstraint("install_quantity > 0", name="ck_configuration_install_quantity_positive"),
        CheckConstraint(
            "replacement_ratio >= 0 AND replacement_ratio <= 1",
            name="ck_configuration_replacement_ratio",
        ),
        CheckConstraint("sort_order >= 0", name="ck_configuration_sort_order_nonnegative"),
        CheckConstraint("parent_item_id IS NULL OR parent_item_id != id", name="ck_item_not_self_parent"),
    )
