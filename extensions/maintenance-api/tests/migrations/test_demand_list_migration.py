from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.schemas.demand_list import DemandListItemQuantitySnapshot
from sqlalchemy import Numeric, create_engine, inspect

REVISION = "20260731_07"
PREVIOUS_REVISION = "20260731_06"
DEMAND_LIST_TABLES = {
    "demand_lists",
    "demand_list_items",
    "demand_list_events",
}


def _config(
    database_path: Path,
    monkeypatch,
) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "demand-list-migration-secret-000001",
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
        for item in inspector.get_unique_constraints(table_name)
    }
    indexes = {
        tuple(item["column_names"])
        for item in inspector.get_indexes(table_name)
        if item["unique"]
    }
    return constraints | indexes


def _partial_unique_predicates(
    inspector,
    table_name: str,
) -> dict[tuple[str, ...], str]:
    predicates: dict[tuple[str, ...], str] = {}
    for item in inspector.get_indexes(table_name):
        if not item["unique"]:
            continue
        options = item.get("dialect_options") or {}
        predicate = options.get("sqlite_where")
        if predicate is None:
            predicate = options.get("postgresql_where")
        if predicate is not None:
            predicates[tuple(item["column_names"])] = " ".join(
                str(predicate).upper().split()
            )
    return predicates


def test_demand_list_schema_has_required_constraints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "demand-lists.db",
        monkeypatch,
    )

    command.upgrade(config, REVISION)

    engine = create_engine(url)
    inspector = inspect(engine)
    assert DEMAND_LIST_TABLES <= set(inspector.get_table_names())
    assert (
        "tenant_id",
        "lineage_id",
        "version_number",
    ) in _unique_column_sets(inspector, "demand_lists")
    assert (
        "tenant_id",
        "demand_list_id",
        "spare_part_id",
    ) in _unique_column_sets(inspector, "demand_list_items")

    list_predicates = _partial_unique_predicates(
        inspector,
        "demand_lists",
    )
    assert (
        "tenant_id",
        "lineage_id",
    ) in list_predicates
    assert "STATUS = 'PUBLISHED'" in list_predicates[
        ("tenant_id", "lineage_id")
    ]
    assert "IS_CURRENT" in list_predicates[
        ("tenant_id", "lineage_id")
    ]

    event_predicates = _partial_unique_predicates(
        inspector,
        "demand_list_events",
    )
    assert (
        "tenant_id",
        "idempotency_key",
    ) in event_predicates
    assert "IDEMPOTENCY_KEY IS NOT NULL" in event_predicates[
        ("tenant_id", "idempotency_key")
    ]

    item_columns = {
        item["name"]: item
        for item in inspector.get_columns("demand_list_items")
    }
    for name in ("original_quantity", "final_quantity"):
        column_type = item_columns[name]["type"]
        assert isinstance(column_type, Numeric)
        assert column_type.precision == 20
        assert column_type.scale == 6

    engine.dispose()
    get_settings.cache_clear()


def test_demand_list_migration_round_trips_one_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "demand-lists-round-trip.db",
        monkeypatch,
    )
    engine = create_engine(url)

    command.upgrade(config, REVISION)
    assert DEMAND_LIST_TABLES <= set(
        inspect(engine).get_table_names()
    )

    command.downgrade(config, PREVIOUS_REVISION)
    assert not (
        DEMAND_LIST_TABLES
        & set(inspect(engine).get_table_names())
    )

    command.upgrade(config, REVISION)
    assert DEMAND_LIST_TABLES <= set(
        inspect(engine).get_table_names()
    )
    engine.dispose()
    get_settings.cache_clear()


def test_demand_list_quantities_serialize_as_exact_decimal_strings() -> None:
    snapshot = DemandListItemQuantitySnapshot(
        original_quantity=Decimal("123456789.123456"),
        final_quantity=Decimal("123456789.123456"),
    )

    assert snapshot.model_dump(mode="json") == {
        "original_quantity": "123456789.123456",
        "final_quantity": "123456789.123456",
    }
