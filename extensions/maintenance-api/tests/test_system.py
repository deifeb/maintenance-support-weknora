from app.core.config import get_settings
from app.core.responses import success_response


def test_settings_have_expected_defaults() -> None:
    settings = get_settings()
    assert settings.app_name == "Maintenance Support API"
    assert settings.app_version == "0.2.0"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url.startswith("sqlite")


def test_success_response_uses_standard_envelope() -> None:
    response = success_response({"value": 1}, "Operation successful")
    assert response.model_dump() == {
        "success": True,
        "data": {"value": 1},
        "message": "Operation successful",
    }


def test_root_endpoint(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["data"]["service"] == "maintenance-api"


def test_system_info_returns_non_sensitive_information(client) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["database_type"] == "sqlite"
    assert "database_url" not in data
