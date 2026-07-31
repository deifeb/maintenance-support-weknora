from app.scripts.seed_demand_scenarios import seed


def test_demand_seed_is_idempotent():
    first = seed(tenant_id="tenant-a")
    second = seed(tenant_id="tenant-a")
    assert first == second
    assert first["scenario_templates"] >= 3
    assert first["repair_profiles"] >= 5
