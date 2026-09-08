from demand_engine import DemandCalculationEngine
from demand_engine.enums import ExecutionMode, FailureProcessMode, ReliabilityModelType
from demand_engine.models import (
    CalculationInput,
    DemandItemInput,
    InventoryInput,
    ReliabilityInput,
    SimulationConfig,
    StageInput,
)


def build_input(mode=ExecutionMode.AUTO):
    return CalculationInput(
        calculation_code="C1",
        stages=(StageInput(code="S1", name="训练", order=1, duration_hours=100, utilization_rate=1),),
        items=(
            DemandItemInput(
                spare_part_id=1,
                spare_part_code="SP-1",
                spare_part_name="泵",
                installed_positions=100,
                replacement_ratio=1,
                is_repairable=True,
                reliability=ReliabilityInput(
                    model_type=ReliabilityModelType.EXPONENTIAL,
                    failure_rate=0.001,
                ),
                failure_process_mode=FailureProcessMode.RENEWAL,
                target_service_level=0.95,
                inventory=InventoryInput(available_quantity=5, in_transit_quantity=0, safety_stock=0),
            ),
        ),
        requested_mode=mode,
        simulation=SimulationConfig(min_runs=1000, max_runs=2000, batch_size=500, quantiles=(0.5, 0.95)),
        random_seed=7,
    )


def test_auto_engine_calculates_item_quantiles():
    result = DemandCalculationEngine().calculate(build_input())
    item = result.runs[0].items[0]
    assert result.formula_version == "DEMAND-FORMULA-1"
    assert item.expected_demand > 0
    assert item.p95 >= item.p50
    assert item.net_demand_gap >= 0


def test_compare_creates_two_runs_and_comparison():
    result = DemandCalculationEngine().calculate(build_input(ExecutionMode.COMPARE))
    assert {run.mode.value for run in result.runs} == {"ANALYTICAL", "MONTE_CARLO"}
    assert result.comparison is not None


def test_common_shock_increases_analytical_expected_demand():
    from dataclasses import replace

    from demand_engine.models import CommonShockInput
    base = build_input(ExecutionMode.ANALYTICAL)
    shocked_item = replace(base.items[0], common_shocks=(CommonShockInput(code="HOT", probability=1, multiplier=2),))
    shocked = replace(base, items=(shocked_item,))
    assert DemandCalculationEngine().calculate(shocked).runs[0].items[0].expected_demand == 20


def test_weibull_age_groups_increase_demand_for_older_population():
    from dataclasses import replace

    from demand_engine.models import AgeGroupInput, ReliabilityInput
    young_rel = ReliabilityInput(model_type=ReliabilityModelType.WEIBULL, weibull_shape=2, weibull_scale=1000)
    young_item = replace(build_input(ExecutionMode.ANALYTICAL).items[0], reliability=young_rel, is_repairable=False, failure_process_mode=FailureProcessMode.SINGLE_FAILURE, initial_age_hours=0)
    old_item = replace(young_item, age_groups=(AgeGroupInput(proportion=1, fixed_hours=800),))
    young = replace(build_input(ExecutionMode.ANALYTICAL), items=(young_item,))
    old = replace(build_input(ExecutionMode.ANALYTICAL), items=(old_item,))
    assert DemandCalculationEngine().calculate(old).runs[0].items[0].expected_demand > DemandCalculationEngine().calculate(young).runs[0].items[0].expected_demand
