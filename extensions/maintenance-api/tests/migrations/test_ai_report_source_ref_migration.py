from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect

REVISION = "20260904_17"
PREVIOUS_REVISION = "20260830_16"


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "c2d-source-ref-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def test_source_ref_revision_is_the_only_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION
    assert script.get_heads() == [REVISION]


def test_source_ref_migration_round_trips(tmp_path, monkeypatch) -> None:
    config, url = _config(tmp_path / "source-ref.db", monkeypatch)
    engine = create_engine(url)
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        command.upgrade(config, REVISION)
        inspector = inspect(engine)
        assert "ai_report_source_refs" in inspector.get_table_names()
        assert {
            "tenant_id",
            "report_version_id",
            "source_type",
            "source_id",
            "source_version",
            "source_lineage_id",
            "source_digest",
            "ordinal",
        } <= {
            column["name"]
            for column in inspector.get_columns("ai_report_source_refs")
        }
        assert any(
            fk["referred_table"] == "ai_report_versions"
            for fk in inspector.get_foreign_keys("ai_report_source_refs")
        )
        assert any(
            index["column_names"]
            == ["tenant_id", "source_type", "source_id"]
            for index in inspector.get_indexes("ai_report_source_refs")
        )
        assert any(
            index["column_names"]
            == ["report_version_id", "ordinal"]
            for index in inspector.get_indexes("ai_report_source_refs")
        )
        assert any(
            constraint["column_names"]
            == [
                "report_version_id",
                "source_type",
                "source_id",
                "source_version",
            ]
            for constraint in inspector.get_unique_constraints(
                "ai_report_source_refs"
            )
        )
        command.downgrade(config, PREVIOUS_REVISION)
        assert "ai_report_source_refs" not in inspect(
            engine
        ).get_table_names()
        command.upgrade(config, REVISION)
    finally:
        engine.dispose()
        get_settings.cache_clear()
