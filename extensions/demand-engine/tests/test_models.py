from dataclasses import FrozenInstanceError

import pytest

from demand_engine.enums import ExecutionMode, FailureProcessMode, ReliabilityModelType
from demand_engine.exceptions import EngineValidationError
from demand_engine.models import SimulationConfig, StageInput


def test_stage_input_is_frozen():
    stage = StageInput(code="S1", name="训练", order=1, duration_hours=100.0, utilization_rate=0.8)
    with pytest.raises(FrozenInstanceError):
        stage.duration_hours = 120.0


def test_simulation_config_rejects_invalid_bounds():
    with pytest.raises(EngineValidationError):
        SimulationConfig(min_runs=2000, max_runs=1000, batch_size=100)


def test_required_enums_are_available():
    assert ExecutionMode.AUTO.value == "AUTO"
    assert FailureProcessMode.RENEWAL.value == "RENEWAL"
    assert ReliabilityModelType.WEIBULL.value == "WEIBULL"
