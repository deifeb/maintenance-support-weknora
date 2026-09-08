from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AgeDistributionType,
    DemandExecutionMode,
    FailureProcessMode,
    MissingParameterPolicy,
    ScenarioVersionStatus,
    ShockApplicationMode,
)
from app.schemas.base import CodeModel, ORMModel, TimestampRead


class ScenarioTemplateCreate(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    tags_json: list[str] | None = None
    is_active: bool = True


class ScenarioTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    tags_json: list[str] | None = None
    is_active: bool | None = None


class ScenarioTemplateRead(ScenarioTemplateCreate, TimestampRead):
    id: int


class SimulationConfigSchema(BaseModel):
    min_runs: int = Field(default=1000, gt=0)
    max_runs: int = Field(default=50000, gt=0)
    batch_size: int = Field(default=1000, gt=0)
    mean_relative_tolerance: Decimal = Field(default=Decimal("0.01"), gt=0)
    quantile_absolute_tolerance: Decimal = Field(default=Decimal("1"), ge=0)
    required_stable_batches: int = Field(default=3, gt=0)
    quantiles: list[Decimal] = Field(
        default_factory=lambda: [
            Decimal("0.5"),
            Decimal("0.8"),
            Decimal("0.9"),
            Decimal("0.95"),
            Decimal("0.99"),
        ]
    )

    @model_validator(mode="after")
    def validate_runs_and_quantiles(self):
        if self.max_runs < self.min_runs:
            raise ValueError("max_runs must be greater than or equal to min_runs")
        if any(q <= 0 or q >= 1 for q in self.quantiles):
            raise ValueError("quantiles must be between 0 and 1")
        return self


class ScenarioVersionCreate(CodeModel):
    version_code: str = Field(min_length=1, max_length=64)
    version_name: str = Field(min_length=1, max_length=200)
    default_service_level: Decimal = Field(default=Decimal("0.9"), gt=0, lt=1)
    criticality_service_levels_json: dict[str, str] = Field(
        default_factory=lambda: {
            "CRITICAL": "0.99",
            "HIGH": "0.95",
            "MEDIUM": "0.90",
            "LOW": "0.80",
        }
    )
    missing_parameter_policy: MissingParameterPolicy = MissingParameterPolicy.WARN_AND_SKIP
    execution_mode: DemandExecutionMode = DemandExecutionMode.AUTO
    comparison_enabled: bool = False
    default_initial_age_hours: Decimal = Field(default=Decimal("0"), ge=0)
    default_repair_parameters_json: dict[str, Any] | None = None
    fallback_parameters_json: dict[str, Any] | None = None
    simulation_config_json: SimulationConfigSchema = Field(default_factory=SimulationConfigSchema)
    formula_version: str = "DEMAND-FORMULA-1"
    input_schema_version: str = "1.0"
    description: str | None = None


class ScenarioVersionUpdate(BaseModel):
    version_name: str | None = Field(default=None, min_length=1, max_length=200)
    default_service_level: Decimal | None = Field(default=None, gt=0, lt=1)
    criticality_service_levels_json: dict[str, str] | None = None
    missing_parameter_policy: MissingParameterPolicy | None = None
    execution_mode: DemandExecutionMode | None = None
    comparison_enabled: bool | None = None
    default_initial_age_hours: Decimal | None = Field(default=None, ge=0)
    default_repair_parameters_json: dict[str, Any] | None = None
    fallback_parameters_json: dict[str, Any] | None = None
    simulation_config_json: SimulationConfigSchema | None = None
    description: str | None = None


class ScenarioVersionRead(ORMModel):
    id: int
    scenario_template_id: int
    version_code: str
    version_name: str
    status: ScenarioVersionStatus
    default_service_level: Decimal
    criticality_service_levels_json: dict[str, Any]
    missing_parameter_policy: MissingParameterPolicy
    execution_mode: DemandExecutionMode
    comparison_enabled: bool
    default_initial_age_hours: Decimal
    default_repair_parameters_json: dict[str, Any] | None
    fallback_parameters_json: dict[str, Any] | None
    simulation_config_json: dict[str, Any]
    formula_version: str
    input_schema_version: str
    description: str | None
    published_at: Any | None
    retired_at: Any | None
    created_at: Any
    updated_at: Any


class ScenarioStageCreate(CodeModel):
    stage_code: str = Field(min_length=1, max_length=64)
    stage_name: str = Field(min_length=1, max_length=200)
    stage_order: int = Field(ge=1)
    duration_hours: Decimal = Field(gt=0)
    utilization_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    mission_intensity_factor: Decimal = Field(default=Decimal("1"), gt=0)
    environment_factor: Decimal = Field(default=Decimal("1"), gt=0)
    temperature_factor: Decimal = Field(default=Decimal("1"), gt=0)
    dust_factor: Decimal = Field(default=Decimal("1"), gt=0)
    humidity_factor: Decimal = Field(default=Decimal("1"), gt=0)
    vibration_factor: Decimal = Field(default=Decimal("1"), gt=0)
    maintenance_level: str | None = Field(default=None, max_length=64)
    description: str | None = None


class FleetGroupCreate(CodeModel):
    group_code: str = Field(min_length=1, max_length=64)
    group_name: str = Field(min_length=1, max_length=200)
    configuration_version_id: int = Field(gt=0)
    initial_quantity: int = Field(gt=0)
    default_initial_age_hours: Decimal | None = Field(default=None, ge=0)
    description: str | None = None


class AgeGroupCreate(CodeModel):
    group_code: str = Field(min_length=1, max_length=64)
    group_name: str = Field(min_length=1, max_length=200)
    distribution_type: AgeDistributionType
    proportion: Decimal = Field(gt=0, le=1)
    fixed_hours: Decimal | None = Field(default=None, ge=0)
    minimum_hours: Decimal | None = Field(default=None, ge=0)
    maximum_hours: Decimal | None = Field(default=None, ge=0)
    mean_hours: Decimal | None = Field(default=None, ge=0)
    std_hours: Decimal | None = Field(default=None, ge=0)
    mode_hours: Decimal | None = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_distribution(self):
        if self.distribution_type is AgeDistributionType.FIXED and self.fixed_hours is None:
            raise ValueError("FIXED requires fixed_hours")
        if self.distribution_type is AgeDistributionType.UNIFORM:
            if self.minimum_hours is None or self.maximum_hours is None:
                raise ValueError("UNIFORM requires minimum_hours and maximum_hours")
        if self.distribution_type is AgeDistributionType.NORMAL:
            if self.mean_hours is None or self.std_hours is None:
                raise ValueError("NORMAL requires mean_hours and std_hours")
        if self.distribution_type is AgeDistributionType.TRIANGULAR:
            if self.minimum_hours is None or self.maximum_hours is None or self.mode_hours is None:
                raise ValueError("TRIANGULAR requires minimum, maximum and mode")
        return self


class FleetUsageCreate(BaseModel):
    fleet_group_id: int = Field(gt=0)
    active_quantity: int = Field(ge=0)
    utilization_override: Decimal | None = Field(default=None, ge=0, le=1)
    equipment_intensity_factor: Decimal = Field(default=Decimal("1"), gt=0)
    environment_factor_override: Decimal | None = Field(default=None, gt=0)
    is_active: bool = True
    notes: str | None = None


class ParameterOverrideCreate(BaseModel):
    stage_id: int | None = Field(default=None, gt=0)
    fleet_group_id: int | None = Field(default=None, gt=0)
    spare_part_id: int = Field(gt=0)
    reliability_profile_id: int | None = Field(default=None, gt=0)
    repair_profile_id: int | None = Field(default=None, gt=0)
    model_type_override: str | None = None
    failure_process_mode: FailureProcessMode = FailureProcessMode.AUTO
    service_level_override: Decimal | None = Field(default=None, gt=0, lt=1)
    exclude_from_calculation: bool = False
    reliability_parameters_json: dict[str, Any] | None = None
    repair_parameters_json: dict[str, Any] | None = None
    adjustment_factors_json: dict[str, Any] | None = None
    override_reason: str | None = None


class CommonShockCreate(CodeModel):
    shock_code: str = Field(min_length=1, max_length=64)
    shock_name: str = Field(min_length=1, max_length=200)
    probability: Decimal = Field(ge=0, le=1)
    multiplier: Decimal = Field(gt=0)
    application_mode: ShockApplicationMode
    fleet_group_id: int | None = Field(default=None, gt=0)
    affected_criticality_json: list[str] | None = None
    affected_categories_json: list[str] | None = None
    affected_spare_parts_json: list[str] | None = None
    maximum_occurrences: int = Field(default=1, ge=1)
    notes: str | None = None


class ScenarioValidationResult(BaseModel):
    valid: bool
    issues: list[dict[str, Any]]


class ScenarioCloneRequest(CodeModel):
    version_code: str = Field(min_length=1, max_length=64)
    version_name: str = Field(min_length=1, max_length=200)
