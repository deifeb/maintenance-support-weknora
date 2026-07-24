from maintenance_ai import AI_CORE_VERSION


def test_maintenance_ai_editable_dependency_is_importable() -> None:
    assert AI_CORE_VERSION == "0.1.0"
