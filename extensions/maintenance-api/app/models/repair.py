from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSourceType
from app.models.mixins import ActiveMixin, TimestampMixin


class RepairProfile(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "repair_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    profile_name: Mapped[str] = mapped_column(String(200), nullable=False)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    configuration_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="RESTRICT"), index=True
    )
    maintenance_level: Mapped[str | None] = mapped_column(String(64), index=True)
    repair_success_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    condemnation_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    repair_turnaround_hours: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    turnaround_std_hours: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    initial_repair_pipeline_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    data_source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType, native_enum=False, length=32),
        nullable=False,
        default=DataSourceType.MANUAL_ESTIMATE,
    )
    data_source_reference: Mapped[str | None] = mapped_column(String(500))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    confidence_level: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "repair_success_rate >= 0 AND repair_success_rate <= 1", name="ck_repair_success_rate"
        ),
        CheckConstraint(
            "condemnation_rate >= 0 AND condemnation_rate <= 1", name="ck_repair_condemnation_rate"
        ),
        CheckConstraint(
            "repair_success_rate + condemnation_rate <= 1", name="ck_repair_probability_sum"
        ),
        CheckConstraint("repair_turnaround_hours > 0", name="ck_repair_turnaround_positive"),
        CheckConstraint("turnaround_std_hours >= 0", name="ck_repair_std_nonnegative"),
        CheckConstraint(
            "initial_repair_pipeline_quantity >= 0", name="ck_repair_initial_pipeline_nonnegative"
        ),
        CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="ck_repair_sample_size_nonnegative"
        ),
        CheckConstraint(
            "confidence_level IS NULL OR (confidence_level > 0 AND confidence_level <= 1)",
            name="ck_repair_confidence",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_repair_date_order",
        ),
    )
