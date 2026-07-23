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


def test_root_endpoint(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "service": "maintenance-api",
            "docs": "/docs",
        },
        "message": "Maintenance Support API is running",
    }


def test_system_info_returns_non_sensitive_information(client) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["data"]["service"] == "maintenance-api"
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["environment"] == "development"
    assert body["data"]["api_prefix"] == "/api/v1"
    assert body["data"]["python_version"].startswith("3.11.")
    assert body["data"]["database_type"] == "sqlite"
    assert body["message"] == "System information retrieved"

    assert "database_url" not in body["data"]
    assert "password" not in body["data"]
