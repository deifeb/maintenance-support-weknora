import time

import pytest
from demand_engine import DemandCalculationEngine
from demand_engine.enums import ExecutionMode, FailureProcessMode, ReliabilityModelType
from demand_engine.models import (
    CalculationInput,
    DemandItemInput,
    ReliabilityInput,
    SimulationConfig,
    StageInput,
)


def _input(item_count, stage_count, mode, runs=1000):
    stages = tuple(
        StageInput(code=f"S{i}", name=f"阶段{i}", order=i, duration_hours=100, utilization_rate=0.8)
        for i in range(1, stage_count + 1)
    )
    items = tuple(
        DemandItemInput(
            spare_part_id=i,
            spare_part_code=f"SP-{i:03d}",
            spare_part_name=f"器材{i}",
            installed_positions=20,
            replacement_ratio=1,
            is_repairable=True,
            reliability=ReliabilityInput(
                model_type=ReliabilityModelType.EXPONENTIAL, failure_rate=0.0001
            ),
            failure_process_mode=FailureProcessMode.RENEWAL,
        )
        for i in range(1, item_count + 1)
    )
    return CalculationInput(
        calculation_code="PERF",
        stages=stages,
        items=items,
        requested_mode=mode,
        simulation=SimulationConfig(
            min_runs=runs,
            max_runs=runs,
            batch_size=runs,
            required_stable_batches=1,
            quantiles=(0.5, 0.95),
        ),
    )


@pytest.mark.performance
def test_analytical_100_items_10_stages_under_two_seconds():
    started = time.perf_counter()
    result = DemandCalculationEngine().calculate(_input(100, 10, ExecutionMode.ANALYTICAL))
    elapsed = time.perf_counter() - started
    assert len(result.runs[0].items) == 100
    assert elapsed < 2.0


@pytest.mark.performance
def test_monte_carlo_50_items_10000_runs_completes():
    started = time.perf_counter()
    result = DemandCalculationEngine().calculate(
        _input(50, 5, ExecutionMode.MONTE_CARLO, runs=10000)
    )
    elapsed = time.perf_counter() - started
    assert result.runs[0].actual_simulation_runs == 10000
    assert elapsed < 15.0
