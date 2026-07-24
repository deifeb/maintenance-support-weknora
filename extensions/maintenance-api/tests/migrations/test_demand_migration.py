from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

MASTER_TABLES = {
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_inventories",
    "suppliers",
    "supplier_offers",
}
DEMAND_TABLES = {
    "repair_profiles",
    "demand_scenario_templates",
    "demand_scenario_versions",
    "demand_scenario_stages",
    "demand_fleet_groups",
    "demand_age_groups",
    "demand_stage_fleet_usages",
    "demand_parameter_overrides",
    "demand_common_shock_rules",
    "demand_calculations",
    "demand_calculation_runs",
    "demand_run_item_results",
    "demand_run_contributions",
}


def test_phase_three_upgrade_downgrade_upgrade(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "phase3.db"
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    assert MASTER_TABLES <= names
    assert DEMAND_TABLES <= names
    command.downgrade(config, "cdbae5051f35")
    names = set(inspect(engine).get_table_names())
    assert MASTER_TABLES <= names
    assert not (DEMAND_TABLES & names)
    command.upgrade(config, "head")
    assert DEMAND_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
    get_settings.cache_clear()
