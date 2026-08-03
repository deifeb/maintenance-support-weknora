from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from app.core.config import get_settings
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


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
    last_counted_at = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
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
                "(warehouse_id, spare_part_id, on_hand_quantity, reserved_quantity, damaged_quantity, quarantined_quantity, in_transit_quantity, safety_stock, reorder_point, maximum_stock, last_counted_at, notes, tenant_id, version, created_at, updated_at) "
                "VALUES (1, 1, '12.5000', '2.0000', '1.0000', '0.5000', '3.0000', '4.0000', '5.0000', '9.0000', :last_counted_at, 'legacy', 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"last_counted_at": last_counted_at},
        )


def _one(engine, table_name: str) -> dict:
    with engine.connect() as connection:
        return dict(connection.execute(text(f"SELECT * FROM {table_name}")).mappings().one())


def _decimal_string(value) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.0001")), ".4f")


def _json(value) -> dict:
    return value if isinstance(value, dict) else json.loads(value)


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
    assert _decimal_string(policy["safety_stock"]) == "4.0000"
    expected_quantities = {
        "on_hand_quantity": "12.5000",
        "reserved_quantity": "2.0000",
        "damaged_quantity": "1.0000",
        "quarantined_quantity": "0.5000",
        "in_transit_quantity": "3.0000",
    }
    assert {
        key: _decimal_string(balance[key]) for key in expected_quantities
    } == expected_quantities
    assert {
        f"{key.removesuffix('_quantity')}_delta": _decimal_string(
            entry[f"{key.removesuffix('_quantity')}_delta"]
        )
        for key in expected_quantities
    } == {
        "on_hand_delta": "12.5000",
        "reserved_delta": "2.0000",
        "damaged_delta": "1.0000",
        "quarantined_delta": "0.5000",
        "in_transit_delta": "3.0000",
    }
    assert transaction["operation_type"] == "MIGRATION_OPENING"
    assert _json(entry["state_before_json"]) == {
        key.removesuffix("_quantity"): "0.0000" for key in expected_quantities
    }
    assert _json(entry["state_after_json"]) == {
        key.removesuffix("_quantity"): value
        for key, value in expected_quantities.items()
    }
    assert _json(transaction["response_snapshot_json"])["legacy_last_counted_at"].startswith(
        "2026-08-01T12:30:00"
    )
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
    assert _decimal_string(legacy["on_hand_quantity"]) == "12.5000"
    assert str(legacy["last_counted_at"]).startswith("2026-08-01 12:30:00")

    command.upgrade(config, REVISION)
    assert _decimal_string(_one(engine, "inventory_balances")["reserved_quantity"]) == "2.0000"
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


@pytest.mark.parametrize(
    "mutation_sql",
    [
        "INSERT INTO inventory_expiry_rules (tenant_id, scope_type, category, spare_part_id, warning_days_json, version, created_at, updated_at) VALUES ('tenant-a', 'TENANT', NULL, NULL, '{}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        "DELETE FROM inventory_balances",
        "INSERT INTO inventory_transactions (tenant_id, operation_type, status, idempotency_key, request_hash, response_snapshot_json, reference_type, reference_id, reason, confirmation_token_hash, confirmation_expires_at, actor_user_id, actor_roles_json, request_id, reversed_transaction_id, version, created_at, updated_at, completed_at, failed_at) VALUES ('tenant-a', 'ADJUST', 'COMPLETED', 'extra-transaction', '1111111111111111111111111111111111111111111111111111111111111111', NULL, NULL, NULL, 'extra fact', NULL, NULL, 'admin', '[]', 'request-extra', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)",
        "INSERT INTO inventory_ledger_entries (tenant_id, transaction_id, balance_id, spare_part_id, warehouse_id, location_id, lot_id, serial_item_id, on_hand_delta, reserved_delta, damaged_delta, quarantined_delta, in_transit_delta, state_before_json, state_after_json, before_balance_version, resulting_balance_version, created_at, updated_at) VALUES ('tenant-a', 1, 1, 1, 1, 1, NULL, NULL, 0, 0, 0, 0, 0, '{}', '{}', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    ],
)
def test_downgrade_rejects_other_non_lossless_ledger_facts(tmp_path: Path, monkeypatch, mutation_sql: str) -> None:
    config, url = _config(tmp_path / "non-lossless.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    command.upgrade(config, REVISION)
    with engine.begin() as connection:
        connection.execute(text(mutation_sql))

    with pytest.raises(CommandError, match="inventory ledger contains granular facts"):
        command.downgrade(config, PREVIOUS_REVISION)
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "mutation_sql",
    [
        "UPDATE warehouse_locations SET name = 'Renamed default' WHERE code = 'DEFAULT'",
        "UPDATE warehouse_locations SET location_type = 'STORAGE', is_pickable = 0, is_active = 0 WHERE code = 'DEFAULT'",
        "UPDATE inventory_transactions SET reference_type = NULL",
        "UPDATE inventory_transactions SET reason = 'changed migration reason'",
        "UPDATE inventory_transactions SET response_snapshot_json = '{}'",
        "UPDATE inventory_ledger_entries SET state_after_json = '{}'",
        "UPDATE inventory_ledger_entries SET resulting_balance_version = 99",
    ],
)
def test_downgrade_rejects_mutated_migration_facts(tmp_path: Path, monkeypatch, mutation_sql: str) -> None:
    config, url = _config(tmp_path / "mutated-migration-facts.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    command.upgrade(config, REVISION)
    with engine.begin() as connection:
        connection.execute(text(mutation_sql))

    with pytest.raises(CommandError, match="inventory ledger contains granular facts"):
        command.downgrade(config, PREVIOUS_REVISION)
    engine.dispose()
    get_settings.cache_clear()


def test_upgrade_conservation_failure_keeps_legacy_source_data(tmp_path: Path, monkeypatch) -> None:
    config, url = _config(tmp_path / "conservation-failure.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    corrupted = False

    def corrupt_destination_after_balance_insert(
        connection,
        cursor,
        statement,
        parameters,
        execution_context,
        executemany,
    ) -> None:
        nonlocal corrupted
        if (
            not corrupted
            and str(connection.engine.url) == url
            and "INSERT INTO inventory_balances" in statement
        ):
            corrupted = True
            connection.exec_driver_sql("UPDATE inventory_balances SET on_hand_quantity = 13")

    event.listen(Engine, "after_cursor_execute", corrupt_destination_after_balance_insert)
    try:
        with pytest.raises(CommandError, match="inventory ledger migration conservation check failed"):
            command.upgrade(config, REVISION)
    finally:
        event.remove(Engine, "after_cursor_execute", corrupt_destination_after_balance_insert)

    assert "warehouse_inventories" in inspect(engine).get_table_names()
    legacy = _one(engine, "warehouse_inventories")
    assert _decimal_string(legacy["on_hand_quantity"]) == "12.5000"
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "table_name, insert_sql",
    [
        (
            "inventory_expiry_rules",
            "INSERT INTO inventory_expiry_rules (tenant_id, scope_type, category, spare_part_id, warning_days_json, version, created_at, updated_at) VALUES ('tenant-a', 'INVALID', NULL, NULL, '{}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
        (
            "inventory_lots",
            "INSERT INTO inventory_lots (tenant_id, spare_part_id, lot_code, quality_status, is_frozen, version, created_at, updated_at) VALUES ('tenant-a', 1, 'LOT-INVALID', 'INVALID', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
        (
            "serialized_items",
            "INSERT INTO serialized_items (tenant_id, spare_part_id, serial_number, warehouse_id, location_id, status, version, created_at, updated_at) VALUES ('tenant-a', 1, 'SERIAL-INVALID', 1, 1, 'INVALID', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        ),
        (
            "inventory_transactions",
            "INSERT INTO inventory_transactions (tenant_id, operation_type, status, idempotency_key, request_hash, response_snapshot_json, reference_type, reference_id, reason, confirmation_token_hash, confirmation_expires_at, actor_user_id, actor_roles_json, request_id, reversed_transaction_id, version, created_at, updated_at, completed_at, failed_at) VALUES ('tenant-a', 'ADJUST', 'INVALID', 'invalid-status', '1111111111111111111111111111111111111111111111111111111111111111', NULL, NULL, NULL, 'invalid enum', NULL, NULL, 'admin', '[]', 'request-invalid', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL)",
        ),
    ],
)
def test_database_rejects_invalid_inventory_enum_values(tmp_path: Path, monkeypatch, table_name: str, insert_sql: str) -> None:
    config, url = _config(tmp_path / f"invalid-{table_name}.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_legacy_inventory(engine)
    command.upgrade(config, REVISION)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(insert_sql))
    engine.dispose()
    get_settings.cache_clear()
