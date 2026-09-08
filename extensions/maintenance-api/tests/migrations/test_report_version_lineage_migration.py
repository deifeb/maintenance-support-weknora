from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.models.ai_report import AIReportVersion
from sqlalchemy import create_engine, inspect

REVISION = "20260830_16"
PREVIOUS_REVISION = "20260827_15"

_REQUIRED_COLUMNS = {
    "parent_version_id",
    "source_snapshot_json",
    "input_digest",
    "generation_mode",
    "generated_at",
}


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "c2b-report-lineage-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def _require_revision(script: ScriptDirectory):
    revision = script.get_revision(REVISION)
    assert revision is not None, (
        "C2B RED M01: Alembic revision "
        "20260830_16_report_version_lineage is absent"
    )
    return revision


def test_report_version_lineage_model_contract_is_absent_before_green() -> None:
    columns = set(AIReportVersion.__table__.columns.keys())
    assert _REQUIRED_COLUMNS <= columns, (
        "C2B RED M02: AIReportVersion lineage/provenance "
        f"columns are absent: {sorted(_REQUIRED_COLUMNS - columns)}"
    )


def test_report_version_lineage_revision_extends_current_single_head() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    revision = _require_revision(script)

    assert revision.down_revision == PREVIOUS_REVISION
    heads = script.get_heads()
    assert len(heads) == 1
    assert REVISION in {
        candidate.revision
        for candidate in script.iterate_revisions(heads[0], "base")
    }


def test_report_version_lineage_migration_round_trips(
    tmp_path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "report-lineage.db",
        monkeypatch,
    )
    script = ScriptDirectory.from_config(config)
    _require_revision(script)

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE ai_report_versions ("
            "id INTEGER NOT NULL PRIMARY KEY"
            ")"
        )
    command.stamp(config, PREVIOUS_REVISION)

    before = inspect(engine)
    before_columns = {
        column["name"]
        for column in before.get_columns("ai_report_versions")
    }
    assert _REQUIRED_COLUMNS.isdisjoint(before_columns)

    command.upgrade(config, REVISION)
    upgraded = inspect(create_engine(url))
    upgraded_columns = {
        column["name"]
        for column in upgraded.get_columns("ai_report_versions")
    }
    assert _REQUIRED_COLUMNS <= upgraded_columns

    parent_fks = [
        foreign_key
        for foreign_key in upgraded.get_foreign_keys(
            "ai_report_versions"
        )
        if foreign_key["constrained_columns"]
        == ["parent_version_id"]
    ]
    assert len(parent_fks) == 1
    assert parent_fks[0]["referred_table"] == "ai_report_versions"
    assert parent_fks[0]["referred_columns"] == ["id"]

    assert any(
        index["column_names"] == ["parent_version_id"]
        for index in upgraded.get_indexes("ai_report_versions")
    )

    generation_mode_checks = [
        constraint
        for constraint in upgraded.get_check_constraints(
            "ai_report_versions"
        )
        if "generation_mode" in str(constraint.get("sqltext", ""))
    ]
    assert generation_mode_checks
    check_sql = " ".join(
        str(row.get("sqltext", ""))
        for row in generation_mode_checks
    )
    assert "LLM" in check_sql
    assert "RULE_FALLBACK" in check_sql

    command.downgrade(config, PREVIOUS_REVISION)
    downgraded = inspect(create_engine(url))
    downgraded_columns = {
        column["name"]
        for column in downgraded.get_columns(
            "ai_report_versions"
        )
    }
    assert _REQUIRED_COLUMNS.isdisjoint(downgraded_columns)

    command.upgrade(config, REVISION)
    reupgraded = inspect(create_engine(url))
    assert _REQUIRED_COLUMNS <= {
        column["name"]
        for column in reupgraded.get_columns(
            "ai_report_versions"
        )
    }
