from pathlib import Path

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect

REVISION = "20260731_06"
PREVIOUS_REVISION = "20260729_05"
GROUP_TABLES = {
    "calculation_groups",
    "calculation_group_children",
    "calculation_group_events",
    "calculation_item_decisions",
}


def _config(
    database_path: Path,
    monkeypatch,
) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "calculation-group-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def _unique_column_sets(
    inspector,
    table_name: str,
) -> set[tuple[str, ...]]:
    constraints = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints(
            table_name
        )
    }
    indexes = {
        tuple(item["column_names"])
        for item in inspector.get_indexes(table_name)
        if item["unique"]
    }
    return constraints | indexes


def test_calculation_group_schema_has_required_constraints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "calculation-groups.db",
        monkeypatch,
    )

    command.upgrade(config, "head")

    engine = create_engine(url)
    inspector = inspect(engine)
    assert GROUP_TABLES <= set(inspector.get_table_names())
    assert (
        "tenant_id",
        "group_id",
        "candidate_key",
        "attempt_number",
    ) in _unique_column_sets(
        inspector,
        "calculation_group_children",
    )
    assert (
        "tenant_id",
        "group_id",
        "sequence",
    ) in _unique_column_sets(
        inspector,
        "calculation_group_events",
    )
    assert (
        "tenant_id",
        "group_id",
        "spare_part_id",
    ) in _unique_column_sets(
        inspector,
        "calculation_item_decisions",
    )
    engine.dispose()
    get_settings.cache_clear()


def test_calculation_group_migration_round_trips_one_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "calculation-groups-round-trip.db",
        monkeypatch,
    )
    engine = create_engine(url)

    command.upgrade(config, REVISION)
    assert GROUP_TABLES <= set(
        inspect(engine).get_table_names()
    )

    command.downgrade(config, PREVIOUS_REVISION)
    assert not (
        GROUP_TABLES
        & set(inspect(engine).get_table_names())
    )

    command.upgrade(config, REVISION)
    assert GROUP_TABLES <= set(
        inspect(engine).get_table_names()
    )
    engine.dispose()
    get_settings.cache_clear()
