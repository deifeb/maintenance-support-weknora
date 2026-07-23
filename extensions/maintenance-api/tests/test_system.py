from app.core.config import get_settings


def test_settings_have_expected_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "Maintenance Support API"
    assert settings.app_version == "0.1.0"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url.startswith("sqlite")


def test_success_response_uses_standard_envelope() -> None:
    from app.core.responses import success_response

    response = success_response(
        data={"value": 1},
        message="Operation successful",
    )

    assert response.model_dump() == {
        "success": True,
        "data": {"value": 1},
        "message": "Operation successful",
    }
