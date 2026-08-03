from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text


REVISION = "20260803_08"
PREVIOUS_REVISION = "20260731_07"


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("INTERNAL_JWT_SECRET", "inventory-ledger-migration-secret-000001")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def _seed_legacy_inventory(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO warehouses "
                "(id, code, name, status, is_active, tenant_id, version, created_at, updated_at) "
                "VALUES (1, 'WH-1', 'Warehouse 1', 'NORMAL', 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO spare_parts "
                "(id, code, name, unit, is_serialized, is_repairable, is_critical, is_active, tenant_id, version, created_at, updated_at) "
                "VALUES (1, 'SP-1', 'Spare 1', 'EA', 0, 0, 0, 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO warehouse_inventories "
                "(warehouse_id, spare_part_id, on_hand_quantity, reserved_quantity, damaged_quantity, quarantined_quantity, in_transit_quantity, safety_stock, reorder_point, maximum_stock, notes, tenant_id, version, created_at, updated_at) "
                "VALUES (1, 1, '12.5000', '2.0000', '1.0000', '0.5000', '3.0000', '4.0000', '5.0000', '9.0000', 'legacy', 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )


def _one(engine, table_name: str) -> dict:
    with engine.connect() as connection:
        return dict(connection.execute(text(f"SELECT * FROM {table_name}")).mappings().one())


def test_upgrade_backfills_default_location_and_opening_ledger(tmp_path: Path, monkeypatch) -> None:
    config, url = _config(tmp_path / "inventory-ledger.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)

    command.upgrade(config, REVISION)

    location = _one(engine, "warehouse_locations")
    policy = _one(engine, "inventory_policies")
    balance = _one(engine, "inventory_balances")
    transaction = _one(engine, "inventory_transactions")
    entry = _one(engine, "inventory_ledger_entries")
    assert location["code"] == "DEFAULT"
    assert policy["safety_stock"] == 4
    assert balance["on_hand_quantity"] == 12.5
    assert entry["reserved_delta"] == 2
    assert transaction["operation_type"] == "MIGRATION_OPENING"
    assert entry["state_before_json"] != entry["state_after_json"]
    assert "warehouse_inventories" not in inspect(engine).get_table_names()
    engine.dispose()
    get_settings.cache_clear()


def test_upgrade_creates_default_location_for_warehouse_without_legacy_inventory(tmp_path: Path, monkeypatch) -> None:
    config, url = _config(tmp_path / "inventory-ledger-empty-warehouse.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO warehouses "
                "(id, code, name, status, is_active, tenant_id, version, created_at, updated_at) "
                "VALUES (2, 'WH-2', 'Warehouse 2', 'NORMAL', 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, REVISION)

    with engine.connect() as connection:
        locations = connection.execute(
            text("SELECT warehouse_id, code FROM warehouse_locations ORDER BY warehouse_id")
        ).all()
    assert locations == [(2, "DEFAULT")]
    engine.dispose()
    get_settings.cache_clear()


def test_downgrade_round_trips_lossless_default_aggregate(tmp_path: Path, monkeypatch) -> None:
    config, url = _config(tmp_path / "inventory-ledger-roundtrip.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    command.upgrade(config, REVISION)

    command.downgrade(config, PREVIOUS_REVISION)
    legacy = _one(engine, "warehouse_inventories")
    assert legacy["on_hand_quantity"] == 12.5

    command.upgrade(config, REVISION)
    assert _one(engine, "inventory_balances")["reserved_quantity"] == 2
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "table_name, insert_sql",
    [
        (
            "warehouse_locations",
            "INSERT INTO warehouse_locations (tenant_id, warehouse_id, code, name, location_type, is_pickable, is_active, version, created_at, updated_at) VALUES ('tenant-a', 1, 'AISLE-A', 'Aisle A', 'STORAGE', 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
        (
            "inventory_lots",
            "INSERT INTO inventory_lots (tenant_id, spare_part_id, lot_code, quality_status, is_frozen, version, created_at, updated_at) VALUES ('tenant-a', 1, 'LOT-1', 'AVAILABLE', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
        (
            "serialized_items",
            "INSERT INTO serialized_items (tenant_id, spare_part_id, serial_number, warehouse_id, location_id, status, version, created_at, updated_at) VALUES ('tenant-a', 1, 'SERIAL-1', 1, 1, 'IN_STOCK', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
    ],
)
def test_downgrade_rejects_granular_inventory_facts(tmp_path: Path, monkeypatch, table_name: str, insert_sql: str) -> None:
    config, url = _config(tmp_path / f"granular-{table_name}.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    command.upgrade(config, REVISION)
    with engine.begin() as connection:
        if table_name == "warehouse_locations":
            connection.execute(text("DELETE FROM warehouse_locations WHERE code = 'DEFAULT'"))
        connection.execute(text(insert_sql))

    with pytest.raises(CommandError, match="inventory ledger contains granular facts"):
        command.downgrade(config, PREVIOUS_REVISION)
    engine.dispose()
    get_settings.cache_clear()
