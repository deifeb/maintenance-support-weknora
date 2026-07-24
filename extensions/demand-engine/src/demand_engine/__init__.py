from demand_engine.engine import DemandCalculationEngine
from demand_engine.version import (
    ENGINE_VERSION,
    FORMULA_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
)

__version__ = ENGINE_VERSION

__all__ = [
    "DemandCalculationEngine",
    "ENGINE_VERSION",
    "FORMULA_VERSION",
    "INPUT_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "__version__",
]
