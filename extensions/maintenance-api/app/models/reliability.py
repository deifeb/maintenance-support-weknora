from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DataSourceType, ReliabilityModelType
from app.models.mixins import ActiveMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.catalog import SparePart
    from app.models.equipment import ConfigurationVersion


class ReliabilityProfile(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "reliability_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    configuration_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="RESTRICT"), index=True
    )
    model_type: Mapped[ReliabilityModelType] = mapped_column(
        Enum(ReliabilityModelType, native_enum=False, length=32), nullable=False, index=True
    )
    failure_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    mtbf_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    weibull_shape: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    weibull_scale: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    binomial_trials: Mapped[int | None] = mapped_column(Integer)
    binomial_probability: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    negative_binomial_r: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    negative_binomial_p: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    empirical_mean: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    empirical_variance: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    extension_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    operating_condition_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    data_source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType, native_enum=False, length=32), nullable=False
    )
    data_source_reference: Mapped[str | None] = mapped_column(String(500))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    confidence_level: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    estimated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    spare_part: Mapped["SparePart"] = relationship(back_populates="reliability_profiles")
    configuration_version: Mapped["ConfigurationVersion | None"] = relationship(
        back_populates="reliability_profiles"
    )

    __table_args__ = (
        CheckConstraint(
            "failure_rate IS NULL OR failure_rate > 0", name="ck_reliability_failure_rate"
        ),
        CheckConstraint("mtbf_hours IS NULL OR mtbf_hours > 0", name="ck_reliability_mtbf"),
        CheckConstraint(
            "weibull_shape IS NULL OR weibull_shape > 0", name="ck_reliability_weibull_shape"
        ),
        CheckConstraint(
            "weibull_scale IS NULL OR weibull_scale > 0", name="ck_reliability_weibull_scale"
        ),
        CheckConstraint(
            "binomial_trials IS NULL OR binomial_trials > 0", name="ck_reliability_binomial_trials"
        ),
        CheckConstraint(
            "binomial_probability IS NULL OR (binomial_probability >= 0 AND binomial_probability <= 1)",
            name="ck_reliability_binomial_probability",
        ),
        CheckConstraint(
            "negative_binomial_r IS NULL OR negative_binomial_r > 0",
            name="ck_reliability_negative_r",
        ),
        CheckConstraint(
            "negative_binomial_p IS NULL OR (negative_binomial_p > 0 AND negative_binomial_p <= 1)",
            name="ck_reliability_negative_p",
        ),
        CheckConstraint(
            "empirical_mean IS NULL OR empirical_mean >= 0", name="ck_reliability_empirical_mean"
        ),
        CheckConstraint(
            "empirical_variance IS NULL OR empirical_variance >= 0",
            name="ck_reliability_empirical_variance",
        ),
        CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="ck_reliability_sample_size"
        ),
        CheckConstraint(
            "confidence_level IS NULL OR (confidence_level > 0 AND confidence_level <= 1)",
            name="ck_reliability_confidence",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_reliability_date_order",
        ),
    )
