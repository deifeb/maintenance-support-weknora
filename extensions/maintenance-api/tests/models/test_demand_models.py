import app.models  # noqa: F401
from app.db.base import Base


def test_all_demand_tables_are_registered():
    names = {
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
    assert names <= set(Base.metadata.tables)
