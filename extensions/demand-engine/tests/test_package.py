from demand_engine import (
    ENGINE_VERSION,
    FORMULA_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
)


def test_public_versions_are_stable():
    assert ENGINE_VERSION == "0.1.0"
    assert FORMULA_VERSION == "DEMAND-FORMULA-1"
    assert INPUT_SCHEMA_VERSION == "1.0"
    assert RESULT_SCHEMA_VERSION == "1.0"
