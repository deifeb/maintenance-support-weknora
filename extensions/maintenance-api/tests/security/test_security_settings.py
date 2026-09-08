from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.core.config import Settings
from pydantic import ValidationError

EXAMPLE_INTERNAL_JWT_SECRET = (
    "replace-with-at-least-32-random-bytes"
)
REAL_INTERNAL_JWT_SECRET = "r" * 48

API_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str,
    secret: str,
) -> Settings:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("INTERNAL_JWT_SECRET", secret)
    return Settings(_env_file=None)


def test_production_rejects_example_internal_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        ValidationError,
        match="INTERNAL_JWT_SECRET",
    ) as exc_info:
        _settings(
            monkeypatch,
            app_env="production",
            secret=EXAMPLE_INTERNAL_JWT_SECRET,
        )

    assert (
        EXAMPLE_INTERNAL_JWT_SECRET
        not in str(exc_info.value)
    )


def test_development_allows_documented_example_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        monkeypatch,
        app_env="development",
        secret=EXAMPLE_INTERNAL_JWT_SECRET,
    )

    assert settings.app_env == "development"


def test_production_accepts_replaced_internal_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        monkeypatch,
        app_env=" Production ",
        secret=REAL_INTERNAL_JWT_SECRET,
    )

    assert (
        settings.internal_jwt_secret.get_secret_value()
        == REAL_INTERNAL_JWT_SECRET
    )


def test_dockerfile_packages_sibling_dependencies() -> None:
    dockerfile = API_ROOT / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    required_lines = {
        "FROM python:3.11-slim",
        "COPY demand-engine /demand-engine",
        "COPY maintenance-ai /maintenance-ai",
        (
            "COPY maintenance-api/requirements.txt "
            "/app/requirements.txt"
        ),
        "COPY maintenance-api/app /app/app",
        "COPY maintenance-api/alembic /app/alembic",
        (
            "COPY maintenance-api/alembic.ini "
            "/app/alembic.ini"
        ),
        "COPY maintenance-api/config /app/config",
        "COPY maintenance-api/templates /app/templates",
        'EXPOSE 8100',
    }

    assert required_lines <= set(text.splitlines())
    assert "COPY . /app" not in text
    assert '"app.main:app"' in text
    assert '"0.0.0.0"' in text
    assert '"8100"' in text


def test_compose_maintenance_service_is_internal_only() -> None:
    compose = yaml.safe_load(
        (
            REPOSITORY_ROOT / "docker-compose.yml"
        ).read_text(encoding="utf-8")
    )

    service = compose["services"]["maintenance-api"]
    assert service["build"] == {
        "context": "./extensions",
        "dockerfile": "maintenance-api/Dockerfile",
    }
    assert service["expose"] == ["8100"]
    assert "ports" not in service
    assert service["networks"] == ["WeKnora-network"]

    environment = service["environment"]
    assert environment["APP_ENV"] == "production"
    assert environment["APP_DEBUG"] == "false"
    assert environment["INTERNAL_JWT_SECRET"] == (
        "${WEKNORA_MAINTENANCE_SIGNING_SECRET:"
        "?set WEKNORA_MAINTENANCE_SIGNING_SECRET}"
    )
    assert environment["DATABASE_URL"] == (
        "sqlite:////app/data/maintenance.db"
    )

    app_environment = set(
        compose["services"]["app"]["environment"]
    )
    assert {
        (
            "WEKNORA_MAINTENANCE_ENABLED="
            "${WEKNORA_MAINTENANCE_ENABLED:-false}"
        ),
        (
            "WEKNORA_MAINTENANCE_BASE_URL="
            "${WEKNORA_MAINTENANCE_BASE_URL:"
            "-http://maintenance-api:8100}"
        ),
        (
            "WEKNORA_MAINTENANCE_SIGNING_SECRET="
            "${WEKNORA_MAINTENANCE_SIGNING_SECRET:-}"
        ),
        (
            "WEKNORA_MAINTENANCE_ISSUER="
            "${WEKNORA_MAINTENANCE_ISSUER:-weknora}"
        ),
        (
            "WEKNORA_MAINTENANCE_AUDIENCE="
            "${WEKNORA_MAINTENANCE_AUDIENCE:"
            "-maintenance-api}"
        ),
        (
            "WEKNORA_MAINTENANCE_TOKEN_TTL="
            "${WEKNORA_MAINTENANCE_TOKEN_TTL:-3m}"
        ),
        (
            "WEKNORA_MAINTENANCE_REQUEST_TIMEOUT="
            "${WEKNORA_MAINTENANCE_REQUEST_TIMEOUT:-30s}"
        ),
    } <= app_environment

    assert {
        "maintenance-data",
        "maintenance-exports",
    } <= set(compose["volumes"])


def test_documented_secret_and_migration_contract() -> None:
    root_env = (
        REPOSITORY_ROOT / ".env.example"
    ).read_text(encoding="utf-8")
    api_env = (
        API_ROOT / ".env.example"
    ).read_text(encoding="utf-8")
    readme = (
        API_ROOT / "README.md"
    ).read_text(encoding="utf-8")

    assert (
        "WEKNORA_MAINTENANCE_SIGNING_SECRET="
        + EXAMPLE_INTERNAL_JWT_SECRET
        in root_env
    )
    assert (
        "INTERNAL_JWT_SECRET="
        + EXAMPLE_INTERNAL_JWT_SECRET
        in api_env
    )

    for marker in (
        "RandomNumberGenerator",
        "[System.Security.Cryptography.RandomNumberGenerator]::Create()",
        "GetBytes",
        "Dispose()",
        "$env:WEKNORA_MAINTENANCE_SIGNING_SECRET",
        "$env:INTERNAL_JWT_SECRET",
        "python -m alembic upgrade head",
        "MAINTENANCE_LEGACY_TENANT_ID",
        "/health",
        "8100",
    ):
        assert marker in readme

        assert "$rng = [\n" not in readme

        assert "::Fill" not in readme
