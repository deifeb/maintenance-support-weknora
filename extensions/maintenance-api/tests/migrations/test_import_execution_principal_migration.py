from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect

REVISION = "20260803_10"
PREVIOUS_REVISION = "20260803_09"


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "import-execution-principal-migration-secret-01",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def test_import_execution_principal_revision_is_reversible(
    tmp_path,
    monkeypatch,
):
    config, url = _config(tmp_path / "execution-principal.db", monkeypatch)
    script = ScriptDirectory.from_config(config)
    assert script.get_revision(REVISION).down_revision == PREVIOUS_REVISION

    command.upgrade(config, REVISION)
    inspector = inspect(create_engine(url))
    columns = {
        column["name"]: column
        for column in inspector.get_columns("master_data_import_tasks")
    }
    assert {
        "execution_user_id",
        "execution_roles_json",
        "execution_request_id",
        "execution_token_id",
        "queued_at",
    } <= columns.keys()
    assert all(
        columns[name]["nullable"]
        for name in (
            "execution_user_id",
            "execution_roles_json",
            "execution_request_id",
            "execution_token_id",
            "queued_at",
        )
    )

    command.downgrade(config, PREVIOUS_REVISION)
    downgraded = {
        column["name"]
        for column in inspect(create_engine(url)).get_columns(
            "master_data_import_tasks"
        )
    }
    assert "execution_user_id" not in downgraded
    command.upgrade(config, REVISION)
    upgraded = {
        column["name"]
        for column in inspect(create_engine(url)).get_columns(
            "master_data_import_tasks"
        )
    }
    assert "execution_user_id" in upgraded
