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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AgeDistributionType,
    DemandExecutionMode,
    FailureProcessMode,
    MissingParameterPolicy,
    ScenarioVersionStatus,
    ShockApplicationMode,
)
from app.models.mixins import ActiveMixin, TimestampMixin


class DemandScenarioTemplate(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "demand_scenario_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[list[str] | None] = mapped_column(JSON)
    versions: Mapped[list["DemandScenarioVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class DemandScenarioVersion(Base, TimestampMixin):
    __tablename__ = "demand_scenario_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_template_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ScenarioVersionStatus] = mapped_column(
        Enum(ScenarioVersionStatus, native_enum=False, length=20),
        nullable=False,
        default=ScenarioVersionStatus.DRAFT,
        index=True,
    )
    default_service_level: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), nullable=False, default=Decimal("0.9")
    )
    criticality_service_levels_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {"CRITICAL": "0.99", "HIGH": "0.95", "MEDIUM": "0.90", "LOW": "0.80"},
    )
    missing_parameter_policy: Mapped[MissingParameterPolicy] = mapped_column(
        Enum(MissingParameterPolicy, native_enum=False, length=24),
        nullable=False,
        default=MissingParameterPolicy.WARN_AND_SKIP,
    )
    execution_mode: Mapped[DemandExecutionMode] = mapped_column(
        Enum(DemandExecutionMode, native_enum=False, length=20),
        nullable=False,
        default=DemandExecutionMode.AUTO,
    )
    comparison_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_initial_age_hours: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    default_repair_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    fallback_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    simulation_config_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {
            "min_runs": 1000,
            "max_runs": 50000,
            "batch_size": 1000,
            "quantiles": ["0.50", "0.80", "0.90", "0.95", "0.99"],
        },
    )
    formula_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="DEMAND-FORMULA-1"
    )
    input_schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    template: Mapped[DemandScenarioTemplate] = relationship(back_populates="versions")
    stages: Mapped[list["DemandScenarioStage"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    fleet_groups: Mapped[list["DemandFleetGroup"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    overrides: Mapped[list["DemandParameterOverride"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("scenario_template_id", "version_code", name="uq_demand_scenario_version"),
        CheckConstraint(
            "default_service_level > 0 AND default_service_level < 1",
            name="ck_demand_default_service_level",
        ),
        CheckConstraint("default_initial_age_hours >= 0", name="ck_demand_default_age_nonnegative"),
    )


class DemandScenarioStage(Base, TimestampMixin):
    __tablename__ = "demand_scenario_stages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    utilization_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=1)
    mission_intensity_factor: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False, default=1
    )
    environment_factor: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False, default=1)
    temperature_factor: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False, default=1)
    dust_factor: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False, default=1)
    humidity_factor: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False, default=1)
    vibration_factor: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False, default=1)
    maintenance_level: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[DemandScenarioVersion] = relationship(back_populates="stages")
    fleet_usages: Mapped[list["DemandStageFleetUsage"]] = relationship(
        back_populates="stage", cascade="all, delete-orphan"
    )
    shocks: Mapped[list["DemandCommonShockRule"]] = relationship(
        back_populates="stage", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("scenario_version_id", "stage_code", name="uq_demand_stage_code"),
        UniqueConstraint("scenario_version_id", "stage_order", name="uq_demand_stage_order"),
        CheckConstraint("stage_order >= 1", name="ck_demand_stage_order"),
        CheckConstraint("duration_hours > 0", name="ck_demand_stage_duration"),
        CheckConstraint(
            "utilization_rate >= 0 AND utilization_rate <= 1", name="ck_demand_stage_utilization"
        ),
    )


class DemandFleetGroup(Base, TimestampMixin):
    __tablename__ = "demand_fleet_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_code: Mapped[str] = mapped_column(String(64), nullable=False)
    group_name: Mapped[str] = mapped_column(String(200), nullable=False)
    configuration_version_id: Mapped[int] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    initial_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    default_initial_age_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[DemandScenarioVersion] = relationship(back_populates="fleet_groups")
    age_groups: Mapped[list["DemandAgeGroup"]] = relationship(
        back_populates="fleet_group", cascade="all, delete-orphan"
    )
    stage_usages: Mapped[list["DemandStageFleetUsage"]] = relationship(
        back_populates="fleet_group", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("scenario_version_id", "group_code", name="uq_demand_fleet_group_code"),
        CheckConstraint("initial_quantity > 0", name="ck_demand_fleet_quantity"),
        CheckConstraint(
            "default_initial_age_hours IS NULL OR default_initial_age_hours >= 0",
            name="ck_demand_fleet_age",
        ),
    )


class DemandAgeGroup(Base, TimestampMixin):
    __tablename__ = "demand_age_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fleet_group_id: Mapped[int] = mapped_column(
        ForeignKey("demand_fleet_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_code: Mapped[str] = mapped_column(String(64), nullable=False)
    group_name: Mapped[str] = mapped_column(String(200), nullable=False)
    distribution_type: Mapped[AgeDistributionType] = mapped_column(
        Enum(AgeDistributionType, native_enum=False, length=20), nullable=False
    )
    proportion: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    fixed_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    minimum_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    maximum_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    mean_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    std_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    mode_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fleet_group: Mapped[DemandFleetGroup] = relationship(back_populates="age_groups")
    __table_args__ = (
        UniqueConstraint("fleet_group_id", "group_code", name="uq_demand_age_group_code"),
        CheckConstraint("proportion > 0 AND proportion <= 1", name="ck_demand_age_proportion"),
        CheckConstraint("sort_order >= 0", name="ck_demand_age_sort"),
    )


class DemandStageFleetUsage(Base, ActiveMixin, TimestampMixin):
    __tablename__ = "demand_stage_fleet_usages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_stages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fleet_group_id: Mapped[int] = mapped_column(
        ForeignKey("demand_fleet_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    active_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    utilization_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    equipment_intensity_factor: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False, default=1
    )
    environment_factor_override: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    notes: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[DemandScenarioStage] = relationship(back_populates="fleet_usages")
    fleet_group: Mapped[DemandFleetGroup] = relationship(back_populates="stage_usages")
    __table_args__ = (
        UniqueConstraint("stage_id", "fleet_group_id", name="uq_demand_stage_fleet_usage"),
        CheckConstraint("active_quantity >= 0", name="ck_demand_active_quantity"),
    )


class DemandParameterOverride(Base, TimestampMixin):
    __tablename__ = "demand_parameter_overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_stages.id", ondelete="CASCADE"), index=True
    )
    fleet_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_fleet_groups.id", ondelete="CASCADE"), index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reliability_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reliability_profiles.id", ondelete="RESTRICT")
    )
    repair_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_profiles.id", ondelete="RESTRICT")
    )
    model_type_override: Mapped[str | None] = mapped_column(String(32))
    failure_process_mode: Mapped[FailureProcessMode] = mapped_column(
        Enum(FailureProcessMode, native_enum=False, length=32),
        nullable=False,
        default=FailureProcessMode.AUTO,
    )
    service_level_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    exclude_from_calculation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reliability_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    repair_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    adjustment_factors_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    override_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[DemandScenarioVersion] = relationship(back_populates="overrides")
    __table_args__ = (
        UniqueConstraint(
            "scenario_version_id",
            "stage_id",
            "fleet_group_id",
            "spare_part_id",
            name="uq_demand_override_scope",
        ),
        CheckConstraint(
            "service_level_override IS NULL OR (service_level_override > 0 AND service_level_override < 1)",
            name="ck_demand_override_service_level",
        ),
    )


class DemandCommonShockRule(Base, TimestampMixin):
    __tablename__ = "demand_common_shock_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("demand_scenario_stages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shock_code: Mapped[str] = mapped_column(String(64), nullable=False)
    shock_name: Mapped[str] = mapped_column(String(200), nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    application_mode: Mapped[ShockApplicationMode] = mapped_column(
        Enum(ShockApplicationMode, native_enum=False, length=32), nullable=False
    )
    fleet_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_fleet_groups.id", ondelete="CASCADE"), index=True
    )
    affected_criticality_json: Mapped[list[str] | None] = mapped_column(JSON)
    affected_categories_json: Mapped[list[str] | None] = mapped_column(JSON)
    affected_spare_parts_json: Mapped[list[str] | None] = mapped_column(JSON)
    maximum_occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[DemandScenarioStage] = relationship(back_populates="shocks")
    __table_args__ = (
        UniqueConstraint("stage_id", "shock_code", name="uq_demand_shock_code"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1", name="ck_demand_shock_probability"
        ),
        CheckConstraint("multiplier > 0", name="ck_demand_shock_multiplier"),
        CheckConstraint("maximum_occurrences >= 1", name="ck_demand_shock_occurrences"),
    )
