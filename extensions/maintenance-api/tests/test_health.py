from app.db.health import check_database_health


def test_database_health_is_healthy() -> None:
    result = check_database_health()
    assert result.status == "healthy"


def test_health_endpoint_returns_database_status(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["database"] == "healthy"


def test_database_failure_uses_controlled_error(monkeypatch, client) -> None:
    from app.api.v1.endpoints import health
    from app.db.health import DatabaseHealth

    monkeypatch.setattr(health, "check_database_health", lambda: DatabaseHealth(status="unhealthy"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
