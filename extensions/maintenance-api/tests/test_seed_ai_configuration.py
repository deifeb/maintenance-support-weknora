from app.scripts.seed_ai_configuration import seed_ai_configuration


def test_seed_ai_configuration_is_idempotent(session) -> None:
    first = seed_ai_configuration(session)
    second = seed_ai_configuration(session)

    assert first == second
    assert first["models"] == 2
    assert first["routes"] == 4
    assert first["tools"] >= 20
    assert first["review_rules"] >= 30
    assert first["report_templates"] == 3
    assert len(first["digest"]) == 64
