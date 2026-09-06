from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.models.ai_report import AIReportJob, AIReportVersion
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

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
        with Session(engine) as session:
            job = AIReportJob(
                tenant_id="legacy-tenant",
                report_code="AIR-LEGACY-001",
                report_type=AIReportType.MANAGEMENT_DECISION,
                status=AIReportJobStatus.CREATED,
                title="Legacy report",
            )
            session.add(job)
            session.flush()
            legacy_version = AIReportVersion(
                tenant_id=job.tenant_id,
                report_job_id=job.id,
                version_number=1,
                status=AIReportVersionStatus.DRAFT,
                template_version="1.0",
                content_digest="f" * 64,
                metadata_json={"legacy": True},
            )
            session.add(legacy_version)
            session.commit()
            legacy_id = legacy_version.id
        command.upgrade(config, REVISION)
        with engine.connect() as connection:
            source_ref_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM ai_report_source_refs"
            ).scalar_one()
        assert source_ref_count == 0
        with Session(engine) as session:
            legacy_version = session.get(AIReportVersion, legacy_id)
            assert legacy_version is not None
            assert legacy_version.metadata_json == {"legacy": True}
            assert legacy_version.source_snapshot_json is None
            assert legacy_version.input_digest is None
            assert session.scalar(
                select(AIReportVersion.id).where(
                    AIReportVersion.id == legacy_id
                )
            ) == legacy_id
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
        with engine.connect() as connection:
            source_ref_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM ai_report_source_refs"
            ).scalar_one()
        assert source_ref_count == 0
    finally:
        engine.dispose()
        get_settings.cache_clear()
