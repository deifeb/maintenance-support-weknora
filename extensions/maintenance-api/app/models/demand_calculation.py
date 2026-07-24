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
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    ReliabilityModelType,
    RerunMode,
    ShortageRiskLevel,
)
from app.models.mixins import TimestampMixin


class DemandCalculation(Base, TimestampMixin):
    __tablename__ = "demand_calculations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calculation_code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    calculation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    scenario_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="RESTRICT"), index=True
    )
    source_calculation_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculations.id", ondelete="RESTRICT"), index=True
    )
    rerun_mode: Mapped[RerunMode] = mapped_column(
        Enum(RerunMode, native_enum=False, length=24), nullable=False, default=RerunMode.NEW
    )
    execution_type: Mapped[CalculationExecutionType] = mapped_column(
        Enum(CalculationExecutionType, native_enum=False, length=20), nullable=False
    )
    requested_mode: Mapped[DemandExecutionMode] = mapped_column(
        Enum(DemandExecutionMode, native_enum=False, length=20), nullable=False
    )
    status: Mapped[CalculationStatus] = mapped_column(
        Enum(CalculationStatus, native_enum=False, length=24),
        nullable=False,
        default=CalculationStatus.PENDING,
        index=True,
    )
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(200))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    inventory_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    warnings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    runs: Mapped[list["DemandCalculationRun"]] = relationship(
        back_populates="calculation", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_demand_calculation_progress",
        ),
    )


class DemandCalculationRun(Base, TimestampMixin):
    __tablename__ = "demand_calculation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calculation_id: Mapped[int] = mapped_column(
        ForeignKey("demand_calculations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_mode: Mapped[DemandExecutionMode] = mapped_column(
        Enum(DemandExecutionMode, native_enum=False, length=20), nullable=False
    )
    status: Mapped[CalculationStatus] = mapped_column(
        Enum(CalculationStatus, native_enum=False, length=24),
        nullable=False,
        default=CalculationStatus.PENDING,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculation_runs.id", ondelete="SET NULL")
    )
    is_current_attempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    current_stage_code: Mapped[str | None] = mapped_column(String(64))
    completed_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int | None] = mapped_column(Integer)
    simulation_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    actual_simulation_runs: Mapped[int | None] = mapped_column(Integer)
    converged: Mapped[bool | None] = mapped_column(Boolean)
    stop_reason: Mapped[str | None] = mapped_column(String(100))
    convergence_metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    warnings_json: Mapped[list[str] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculation: Mapped[DemandCalculation] = relationship(back_populates="runs")
    item_results: Mapped[list["DemandRunItemResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    contributions: Mapped[list["DemandRunContribution"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint(
            "calculation_id", "run_mode", "attempt_number", name="uq_demand_run_attempt"
        ),
        CheckConstraint("attempt_number >= 1", name="ck_demand_run_attempt"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="ck_demand_run_progress"
        ),
    )


class DemandRunItemResult(Base, TimestampMixin):
    __tablename__ = "demand_run_item_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("demand_calculation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    spare_part_code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    spare_part_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    criticality_level: Mapped[str | None] = mapped_column(String(20))
    calculation_status: Mapped[ItemCalculationStatus] = mapped_column(
        Enum(ItemCalculationStatus, native_enum=False, length=20), nullable=False
    )
    selected_model_type: Mapped[ReliabilityModelType | None] = mapped_column(
        Enum(ReliabilityModelType, native_enum=False, length=32)
    )
    failure_process_mode: Mapped[FailureProcessMode] = mapped_column(
        Enum(FailureProcessMode, native_enum=False, length=32), nullable=False
    )
    selected_reliability_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reliability_profiles.id", ondelete="SET NULL")
    )
    selected_repair_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_profiles.id", ondelete="SET NULL")
    )
    selection_reason_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    parameter_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_manually_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_service_level: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    expected_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    variance: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    standard_deviation: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    p50: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    p80: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    p90: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    p95: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    p99: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    target_quantile_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    gross_replacement_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    repair_pipeline_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    repair_pipeline_peak: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    net_consumption_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    recommended_spare_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    in_transit_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    safety_stock_reserved: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    usable_inventory: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    net_demand_gap: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    inventory_coverage_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    shortage_risk_level: Mapped[ShortageRiskLevel] = mapped_column(
        Enum(ShortageRiskLevel, native_enum=False, length=20), nullable=False
    )
    minimum_inventory_point: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    maximum_simultaneous_gap: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    common_shock_demand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    warning_codes_json: Mapped[list[str] | None] = mapped_column(JSON)
    run: Mapped[DemandCalculationRun] = relationship(back_populates="item_results")
    __table_args__ = (
        UniqueConstraint("calculation_run_id", "spare_part_id", name="uq_demand_run_item"),
    )


class DemandRunContribution(Base, TimestampMixin):
    __tablename__ = "demand_run_contributions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("demand_calculation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_stages.id", ondelete="SET NULL"), index=True
    )
    stage_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    stage_name_snapshot: Mapped[str | None] = mapped_column(String(200))
    fleet_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_fleet_groups.id", ondelete="SET NULL"), index=True
    )
    fleet_group_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    configuration_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="SET NULL")
    )
    configuration_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    configuration_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_items.id", ondelete="SET NULL")
    )
    item_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    position_code_snapshot: Mapped[str | None] = mapped_column(String(100))
    part_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    install_quantity_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    equipment_quantity_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    replacement_ratio_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), nullable=False, default=1
    )
    expected_failure_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    gross_replacement_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    net_consumption_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    repair_pipeline_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    common_shock_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    reliability_parameter_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    repair_parameter_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    adjustment_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    selection_reason_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    run: Mapped[DemandCalculationRun] = relationship(back_populates="contributions")
