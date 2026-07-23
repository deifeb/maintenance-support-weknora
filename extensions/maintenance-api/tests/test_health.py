from app.db.health import check_database_health


def test_database_health_is_healthy() -> None:
    result = check_database_health()

    assert result.status == "healthy"
    assert result.error is None
