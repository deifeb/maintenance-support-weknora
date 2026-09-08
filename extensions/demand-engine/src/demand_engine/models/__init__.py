from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from demand_engine.enums import (
    AgeDistributionType,
    ExecutionMode,
    FailureProcessMode,
    ReliabilityModelType,
    ShockApplicationMode,
)
from demand_engine.exceptions import EngineValidationError


def _positive(value: float, name: str, *, allow_zero: bool = False) -> None:
    valid = value >= 0 if allow_zero else value > 0
    if not isfinite(value) or not valid:
        operator = "non-negative" if allow_zero else "positive"
        raise EngineValidationError(f"{name} must be {operator}")


@dataclass(frozen=True, slots=True)
class StageInput:
    code: str
    name: str
    order: int
    duration_hours: float
    utilization_rate: float = 1.0
    mission_intensity_factor: float = 1.0
    environment_factor: float = 1.0
    temperature_factor: float = 1.0
    dust_factor: float = 1.0
    humidity_factor: float = 1.0
    vibration_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.order < 1:
            raise EngineValidationError("stage order must be positive")
        _positive(self.duration_hours, "duration_hours")
        if not 0 <= self.utilization_rate <= 1:
            raise EngineValidationError("utilization_rate must be between 0 and 1")
        for name in (
            "mission_intensity_factor",
            "environment_factor",
            "temperature_factor",
            "dust_factor",
            "humidity_factor",
            "vibration_factor",
        ):
            _positive(getattr(self, name), name)

    @property
    def effective_hours(self) -> float:
        return self.duration_hours * self.utilization_rate

    @property
    def adjustment_factor(self) -> float:
        return (
            self.mission_intensity_factor
            * self.environment_factor
            * self.temperature_factor
            * self.dust_factor
            * self.humidity_factor
            * self.vibration_factor
        )


@dataclass(frozen=True, slots=True)
class AgeGroupInput:
    proportion: float
    distribution_type: AgeDistributionType = AgeDistributionType.FIXED
    fixed_hours: float | None = 0.0
    minimum_hours: float | None = None
    maximum_hours: float | None = None
    mean_hours: float | None = None
    std_hours: float | None = None
    mode_hours: float | None = None

    def __post_init__(self) -> None:
        if not 0 < self.proportion <= 1:
            raise EngineValidationError("age group proportion must be in (0, 1]")
        for value in (
            self.fixed_hours,
            self.minimum_hours,
            self.maximum_hours,
            self.mean_hours,
            self.std_hours,
            self.mode_hours,
        ):
            if value is not None:
                _positive(value, "age value", allow_zero=True)
        if self.distribution_type is AgeDistributionType.FIXED and self.fixed_hours is None:
            raise EngineValidationError("FIXED age group requires fixed_hours")
        if self.distribution_type in {AgeDistributionType.UNIFORM, AgeDistributionType.TRIANGULAR}:
            if self.minimum_hours is None or self.maximum_hours is None:
                raise EngineValidationError("bounded age distribution requires minimum and maximum")
            if self.maximum_hours < self.minimum_hours:
                raise EngineValidationError("maximum age must be at least minimum age")
        if self.distribution_type is AgeDistributionType.NORMAL:
            if self.mean_hours is None or self.std_hours is None:
                raise EngineValidationError("NORMAL age group requires mean and std")
        if self.distribution_type is AgeDistributionType.TRIANGULAR:
            if self.mode_hours is None or not self.minimum_hours <= self.mode_hours <= self.maximum_hours:
                raise EngineValidationError("TRIANGULAR mode must lie within bounds")


@dataclass(frozen=True, slots=True)
class ReliabilityInput:
    model_type: ReliabilityModelType
    failure_rate: float | None = None
    mtbf_hours: float | None = None
    weibull_shape: float | None = None
    weibull_scale: float | None = None
    binomial_trials: int | None = None
    binomial_probability: float | None = None
    negative_binomial_r: float | None = None
    negative_binomial_p: float | None = None
    empirical_mean: float | None = None
    empirical_variance: float | None = None
    reference_duration_hours: float | None = None

    def __post_init__(self) -> None:
        if self.model_type is ReliabilityModelType.EXPONENTIAL:
            if self.failure_rate is None and self.mtbf_hours is None:
                raise EngineValidationError("exponential model requires failure_rate or mtbf_hours")
            if self.failure_rate is not None:
                _positive(self.failure_rate, "failure_rate")
            if self.mtbf_hours is not None:
                _positive(self.mtbf_hours, "mtbf_hours")
        elif self.model_type is ReliabilityModelType.WEIBULL:
            if self.weibull_shape is None or self.weibull_scale is None:
                raise EngineValidationError("weibull model requires shape and scale")
            _positive(self.weibull_shape, "weibull_shape")
            _positive(self.weibull_scale, "weibull_scale")
        elif self.model_type is ReliabilityModelType.BINOMIAL:
            if self.binomial_trials is None or self.binomial_trials <= 0:
                raise EngineValidationError("binomial model requires positive trials")
            if self.binomial_probability is None or not 0 <= self.binomial_probability <= 1:
                raise EngineValidationError("binomial probability must be between 0 and 1")
        elif self.model_type is ReliabilityModelType.NEGATIVE_BINOMIAL:
            if self.negative_binomial_r is None or self.negative_binomial_r <= 0:
                raise EngineValidationError("negative binomial r must be positive")
            if self.negative_binomial_p is None or not 0 < self.negative_binomial_p <= 1:
                raise EngineValidationError("negative binomial p must be in (0, 1]")
        elif self.model_type is ReliabilityModelType.EMPIRICAL:
            if self.empirical_mean is None or self.empirical_mean < 0:
                raise EngineValidationError("empirical model requires a non-negative mean")
            if self.empirical_variance is None or self.empirical_variance < 0:
                raise EngineValidationError("empirical model requires a non-negative variance")
        if self.reference_duration_hours is not None:
            _positive(self.reference_duration_hours, "reference_duration_hours")

    @property
    def resolved_failure_rate(self) -> float:
        if self.failure_rate is not None:
            return self.failure_rate
        assert self.mtbf_hours is not None
        return 1.0 / self.mtbf_hours


@dataclass(frozen=True, slots=True)
class RepairInput:
    success_rate: float = 0.0
    condemnation_rate: float = 1.0
    turnaround_hours: float = 1.0
    turnaround_std_hours: float = 0.0
    initial_pipeline_quantity: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.success_rate <= 1 or not 0 <= self.condemnation_rate <= 1:
            raise EngineValidationError("repair probabilities must be between 0 and 1")
        if self.success_rate + self.condemnation_rate > 1 + 1e-12:
            raise EngineValidationError("repair success and condemnation rates cannot exceed 1")
        _positive(self.turnaround_hours, "turnaround_hours")
        _positive(self.turnaround_std_hours, "turnaround_std_hours", allow_zero=True)
        _positive(self.initial_pipeline_quantity, "initial_pipeline_quantity", allow_zero=True)


@dataclass(frozen=True, slots=True)
class InventoryInput:
    on_hand_quantity: float = 0.0
    available_quantity: float = 0.0
    in_transit_quantity: float = 0.0
    safety_stock: float = 0.0

    def __post_init__(self) -> None:
        for name in ("on_hand_quantity", "available_quantity", "in_transit_quantity", "safety_stock"):
            _positive(getattr(self, name), name, allow_zero=True)


@dataclass(frozen=True, slots=True)
class CommonShockInput:
    code: str
    probability: float
    multiplier: float
    application_mode: ShockApplicationMode = ShockApplicationMode.FAILURE_RATE
    maximum_occurrences: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.probability <= 1:
            raise EngineValidationError("shock probability must be between 0 and 1")
        _positive(self.multiplier, "shock multiplier")
        if self.maximum_occurrences < 1:
            raise EngineValidationError("maximum_occurrences must be positive")


@dataclass(frozen=True, slots=True)
class DemandItemInput:
    spare_part_id: int
    spare_part_code: str
    spare_part_name: str
    installed_positions: float
    replacement_ratio: float
    is_repairable: bool
    reliability: ReliabilityInput
    failure_process_mode: FailureProcessMode = FailureProcessMode.AUTO
    target_service_level: float = 0.95
    initial_age_hours: float = 0.0
    age_groups: tuple[AgeGroupInput, ...] = ()
    repair: RepairInput | None = None
    inventory: InventoryInput = field(default_factory=InventoryInput)
    common_shocks: tuple[CommonShockInput, ...] = ()
    manual_override: bool = False
    selection_reason: str = "AUTO_SELECTED"

    def __post_init__(self) -> None:
        _positive(self.installed_positions, "installed_positions", allow_zero=True)
        if not 0 <= self.replacement_ratio <= 1:
            raise EngineValidationError("replacement_ratio must be between 0 and 1")
        if not 0 < self.target_service_level < 1:
            raise EngineValidationError("target_service_level must be between 0 and 1")
        _positive(self.initial_age_hours, "initial_age_hours", allow_zero=True)
        if self.age_groups and abs(sum(group.proportion for group in self.age_groups) - 1.0) > 1e-6:
            raise EngineValidationError("age group proportions must sum to 1")
        if self.is_repairable and self.repair is None:
            object.__setattr__(self, "repair", RepairInput())


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    min_runs: int = 1000
    max_runs: int = 50000
    batch_size: int = 1000
    mean_relative_tolerance: float = 0.01
    quantile_absolute_tolerance: float = 1.0
    required_stable_batches: int = 3
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95, 0.99)

    def __post_init__(self) -> None:
        if self.min_runs <= 0 or self.max_runs < self.min_runs or self.batch_size <= 0:
            raise EngineValidationError("invalid simulation run bounds")
        if self.required_stable_batches <= 0:
            raise EngineValidationError("required_stable_batches must be positive")
        if any(not 0 < q < 1 for q in self.quantiles):
            raise EngineValidationError("quantiles must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CalculationInput:
    calculation_code: str
    stages: tuple[StageInput, ...]
    items: tuple[DemandItemInput, ...]
    requested_mode: ExecutionMode = ExecutionMode.AUTO
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    random_seed: int = 20260723
    formula_version: str = "DEMAND-FORMULA-1"
    input_schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.stages:
            raise EngineValidationError("at least one stage is required")
        if sorted(stage.order for stage in self.stages) != list(range(1, len(self.stages) + 1)):
            raise EngineValidationError("stage order must be contiguous")


@dataclass(frozen=True, slots=True)
class ItemResult:
    spare_part_id: int
    spare_part_code: str
    spare_part_name: str
    expected_demand: float
    variance: float
    standard_deviation: float
    p50: float
    p80: float
    p90: float
    p95: float
    p99: float
    target_service_level: float
    target_quantile_demand: float
    gross_replacement_demand: float
    repair_pipeline_demand: float
    repair_pipeline_peak: float
    net_consumption_demand: float
    recommended_spare_quantity: float
    usable_inventory: float
    net_demand_gap: float
    inventory_coverage_rate: float
    selected_model_type: ReliabilityModelType
    failure_process_mode: FailureProcessMode
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunResult:
    mode: ExecutionMode
    items: tuple[ItemResult, ...]
    actual_simulation_runs: int | None = None
    converged: bool | None = None
    stop_reason: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    consistency: str
    item_differences: tuple[dict[str, float | int | str], ...]


@dataclass(frozen=True, slots=True)
class CalculationResult:
    calculation_code: str
    engine_version: str
    formula_version: str
    input_schema_version: str
    result_schema_version: str
    runs: tuple[RunResult, ...]
    comparison: ComparisonResult | None = None
