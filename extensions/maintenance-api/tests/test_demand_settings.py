from app.core.config import Settings


def test_demand_settings_have_safe_defaults(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}", _env_file=None)
    assert settings.demand_worker_count == 2
    assert settings.demand_sync_timeout_seconds == 5
    assert settings.demand_max_pending_tasks == 20
    assert settings.demand_max_monte_carlo_runs == 50000
    assert settings.demand_max_scenario_stages == 100
    assert settings.demand_max_fleet_groups == 500
    assert settings.demand_max_demand_items == 5000
    assert settings.demand_result_export_max_rows == 100000
