from app.scripts.seed_demand_scenarios import seed


def test_demand_seed_is_idempotent():
    first = seed()
    second = seed()
    assert first == second
    assert first["scenario_templates"] >= 3
    assert first["repair_profiles"] >= 5
