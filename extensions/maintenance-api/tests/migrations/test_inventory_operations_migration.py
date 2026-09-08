from __future__ import annotations

import hashlib
import json
from io import StringIO
from pathlib import Path

import app.models  # noqa: F401
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

REVISION = "20260803_11"
PREVIOUS_REVISION = "20260803_10"
OPERATION_TABLES = {
    "inventory_reservations",
    "inventory_reservation_lines",
    "inventory_transfers",
    "inventory_transfer_lines",
    "stocktakes",
    "stocktake_lines",
}
EXPECTED_COLUMNS = {
    "inventory_reservations": {
        "id", "tenant_id", "owner_type", "owner_id", "status", "expires_at",
        "allow_partial", "actor_user_id", "actor_roles_json", "request_id",
        "version", "created_at", "updated_at",
    },
    "inventory_reservation_lines": {
        "id", "tenant_id", "reservation_id", "spare_part_id", "balance_id",
        "lot_id", "serial_item_id", "requested_quantity", "reserved_quantity",
        "issued_quantity", "released_quantity", "expected_balance_version",
        "fefo_rank", "fefo_override_reason", "recommended_selection_json",
        "actual_selection_json", "version", "created_at", "updated_at",
    },
    "inventory_transfers": {
        "id", "tenant_id", "status", "source_warehouse_id", "source_location_id",
        "target_warehouse_id", "target_location_id", "reference_type",
        "reference_id", "reason", "actor_user_id", "actor_roles_json",
        "request_id", "version", "created_at", "updated_at", "dispatched_at",
        "completed_at", "cancelled_at",
    },
    "inventory_transfer_lines": {
        "id", "tenant_id", "transfer_id", "spare_part_id", "source_balance_id",
        "target_balance_id", "lot_id", "serial_item_id", "requested_quantity",
        "dispatched_quantity", "received_quantity", "expected_source_version",
        "expected_target_version", "version", "created_at", "updated_at",
    },
    "stocktakes": {
        "id", "tenant_id", "warehouse_id", "location_id", "status",
        "snapshot_at", "actor_user_id", "actor_roles_json", "request_id",
        "version", "created_at", "updated_at", "confirmed_at", "cancelled_at",
    },
    "stocktake_lines": {
        "id", "tenant_id", "stocktake_id", "balance_id", "spare_part_id",
        "lot_id", "serial_item_id", "system_quantity", "counted_quantity",
        "variance_quantity", "snapshot_balance_version",
        "confirmed_transaction_id", "resolution", "conflict_details_json",
        "version", "created_at", "updated_at",
    },
}


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "inventory-operations-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def _seed_05_4a_facts(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO warehouses "
                "(id, code, name, status, is_active, tenant_id, version, created_at, updated_at) "
                "VALUES "
                "(1, 'WH-OP-SOURCE', 'Source warehouse', 'NORMAL', 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "(2, 'WH-OP-TARGET', 'Target warehouse', 'NORMAL', 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO spare_parts "
                "(id, code, name, unit, is_serialized, is_repairable, is_critical, is_active, tenant_id, version, created_at, updated_at) "
                "VALUES (1, 'SP-OP-1', 'Operation spare', 'EA', 0, 0, 0, 1, 'tenant-a', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO warehouse_locations "
                "(id, tenant_id, warehouse_id, code, name, location_type, is_pickable, is_active, version, created_at, updated_at) "
                "VALUES "
                "(1, 'tenant-a', 1, 'SOURCE', 'Source location', 'SHELF', 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "(2, 'tenant-a', 2, 'TARGET', 'Target location', 'SHELF', 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_lots "
                "(id, tenant_id, spare_part_id, lot_code, manufacture_date, received_date, expiry_date, quality_status, is_frozen, freeze_reason, version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 1, 'LOT-OP-1', NULL, '2026-08-01', '2027-08-01', 'AVAILABLE', 0, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_balances "
                "(id, tenant_id, warehouse_id, location_id, spare_part_id, lot_id, on_hand_quantity, reserved_quantity, damaged_quantity, quarantined_quantity, in_transit_quantity, version, created_at, updated_at) "
                "VALUES "
                "(1, 'tenant-a', 1, 1, 1, 1, 10.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "(2, 'tenant-a', 2, 2, 1, 1, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_transactions "
                "(id, tenant_id, operation_type, status, idempotency_key, request_hash, response_snapshot_json, reference_type, reference_id, reason, confirmation_token_hash, confirmation_expires_at, actor_user_id, actor_roles_json, request_id, reversed_transaction_id, version, created_at, updated_at, completed_at, failed_at) "
                "VALUES (1, 'tenant-a', 'OPENING', 'COMPLETED', 'plan05-4b-baseline', "
                "'1111111111111111111111111111111111111111111111111111111111111111', "
                ":response_snapshot_json, 'PREFLIGHT', 'baseline', 'baseline inventory', NULL, NULL, "
                "'admin-a', :actor_roles_json, 'request-baseline', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)"
            ),
            {
                "response_snapshot_json": json.dumps({"transaction_id": 1}),
                "actor_roles_json": json.dumps(["admin"]),
            },
        )
        connection.execute(
            text(
                "INSERT INTO inventory_ledger_entries "
                "(id, tenant_id, transaction_id, balance_id, spare_part_id, warehouse_id, location_id, lot_id, serial_item_id, on_hand_delta, reserved_delta, damaged_delta, quarantined_delta, in_transit_delta, state_before_json, state_after_json, before_balance_version, resulting_balance_version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 1, 1, 1, 1, 1, 1, NULL, 10.0000, 0.0000, 0.0000, 0.0000, 0.0000, "
                ":state_before_json, :state_after_json, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "state_before_json": json.dumps({"on_hand": "0.0000"}),
                "state_after_json": json.dumps({"on_hand": "10.0000"}),
            },
        )


def _facts_hash(engine) -> str:
    payload: dict[str, list[dict[str, str]]] = {}
    with engine.connect() as connection:
        for table_name in (
            "warehouse_locations",
            "inventory_lots",
            "inventory_balances",
            "inventory_transactions",
            "inventory_ledger_entries",
        ):
            rows = connection.execute(
                text(f"SELECT * FROM {table_name} ORDER BY id")
            ).mappings()
            payload[table_name] = [
                {key: str(value) for key, value in row.items()} for row in rows
            ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_names(inspector, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
        if constraint["name"] is not None
    }


def _index_names(inspector, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index["name"] is not None
    }


def _unique_column_sets(inspector, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _insert_operation_samples(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text(
                "INSERT INTO inventory_reservations "
                "(id, tenant_id, owner_type, owner_id, status, expires_at, allow_partial, actor_user_id, actor_roles_json, request_id, version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 'MANUAL', 'reservation-1', 'ACTIVE', '2026-08-05 00:00:00', 0, 'contributor-a', '[\"contributor\"]', 'request-reservation-1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_reservation_lines "
                "(id, tenant_id, reservation_id, spare_part_id, balance_id, lot_id, serial_item_id, requested_quantity, reserved_quantity, issued_quantity, released_quantity, expected_balance_version, fefo_rank, fefo_override_reason, recommended_selection_json, actual_selection_json, version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 1, 1, 1, 1, NULL, 4.0000, 4.0000, 1.0000, 0.0000, 1, 1, NULL, NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_transfers "
                "(id, tenant_id, status, source_warehouse_id, source_location_id, target_warehouse_id, target_location_id, reference_type, reference_id, reason, actor_user_id, actor_roles_json, request_id, version, created_at, updated_at, dispatched_at, completed_at, cancelled_at) "
                "VALUES (1, 'tenant-a', 'DISPATCHED', 1, 1, 2, 2, 'MANUAL', 'transfer-1', 'replenishment', 'admin-a', '[\"admin\"]', 'request-transfer-1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inventory_transfer_lines "
                "(id, tenant_id, transfer_id, spare_part_id, source_balance_id, target_balance_id, lot_id, serial_item_id, requested_quantity, dispatched_quantity, received_quantity, expected_source_version, expected_target_version, version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 1, 1, 1, 2, 1, NULL, 3.0000, 3.0000, 1.0000, 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stocktakes "
                "(id, tenant_id, warehouse_id, location_id, status, snapshot_at, actor_user_id, actor_roles_json, request_id, version, created_at, updated_at, confirmed_at, cancelled_at) "
                "VALUES (1, 'tenant-a', 1, 1, 'REVIEWING', CURRENT_TIMESTAMP, 'contributor-a', '[\"contributor\"]', 'request-stocktake-1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stocktake_lines "
                "(id, tenant_id, stocktake_id, balance_id, spare_part_id, lot_id, serial_item_id, system_quantity, counted_quantity, variance_quantity, snapshot_balance_version, confirmed_transaction_id, resolution, conflict_details_json, version, created_at, updated_at) "
                "VALUES (1, 'tenant-a', 1, 1, 1, 1, NULL, 10.0000, 9.0000, -1.0000, 1, NULL, 'PENDING', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )


def _delete_operation_samples(engine) -> None:
    with engine.begin() as connection:
        for table_name in (
            "stocktake_lines",
            "stocktakes",
            "inventory_transfer_lines",
            "inventory_transfers",
            "inventory_reservation_lines",
            "inventory_reservations",
        ):
            connection.execute(text(f"DELETE FROM {table_name}"))


def test_inventory_operations_revision_chain() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(REVISION)
    assert revision.revision == REVISION
    assert revision.down_revision == PREVIOUS_REVISION


def test_inventory_operations_upgrade_constraints_and_round_trip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(tmp_path / "inventory-operations.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    _seed_05_4a_facts(engine)
    before_hash = _facts_hash(engine)

    command.upgrade(config, REVISION)
    inspector = inspect(engine)
    assert OPERATION_TABLES <= set(inspector.get_table_names())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert expected_columns <= actual_columns
    assert ("tenant_id", "id") in _unique_column_sets(
        inspector, "inventory_reservations"
    )
    assert ("tenant_id", "id") in _unique_column_sets(
        inspector, "inventory_transfers"
    )
    assert ("tenant_id", "id") in _unique_column_sets(inspector, "stocktakes")
    assert {
        "ck_inventory_reservation_status",
    } <= _check_names(inspector, "inventory_reservations")
    assert {
        "ck_inventory_reservation_line_lifecycle",
        "ck_inventory_reservation_line_serial_quantities",
    } <= _check_names(inspector, "inventory_reservation_lines")
    assert {
        "ck_inventory_transfer_status",
        "ck_inventory_transfer_distinct_locations",
    } <= _check_names(inspector, "inventory_transfers")
    assert {
        "ck_inventory_transfer_line_dispatch_lifecycle",
        "ck_inventory_transfer_line_receive_lifecycle",
        "ck_inventory_transfer_line_serial_quantities",
    } <= _check_names(inspector, "inventory_transfer_lines")
    assert {"ck_inventory_stocktake_status"} <= _check_names(inspector, "stocktakes")
    assert {
        "ck_inventory_stocktake_line_resolution",
        "ck_inventory_stocktake_line_variance",
    } <= _check_names(inspector, "stocktake_lines")
    assert {
        "ix_inventory_reservations_tenant_status_expires",
    } <= _index_names(inspector, "inventory_reservations")
    assert {"ix_inventory_transfers_tenant_status"} <= _index_names(
        inspector, "inventory_transfers"
    )
    assert {"ix_stocktakes_tenant_status"} <= _index_names(inspector, "stocktakes")

    _insert_operation_samples(engine)
    _delete_operation_samples(engine)
    command.downgrade(config, PREVIOUS_REVISION)
    assert OPERATION_TABLES.isdisjoint(inspect(engine).get_table_names())
    assert _facts_hash(engine) == before_hash

    command.upgrade(config, REVISION)
    assert OPERATION_TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        current_revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert current_revision == REVISION
    assert _facts_hash(engine) == before_hash

    engine.dispose()
    get_settings.cache_clear()


def test_inventory_operations_downgrade_rejects_business_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(tmp_path / "inventory-operations-downgrade.db", monkeypatch)
    command.upgrade(config, REVISION)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO inventory_reservations "
                "(tenant_id, owner_type, owner_id, status, expires_at, allow_partial, actor_user_id, actor_roles_json, request_id, version, created_at, updated_at) "
                "VALUES ('tenant-a', 'MANUAL', 'downgrade-blocker', 'ACTIVE', NULL, 0, 'contributor-a', '[\"contributor\"]', 'request-downgrade-blocker', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    with pytest.raises(
        CommandError,
        match="cannot downgrade inventory operations while 05-4B business data exists",
    ):
        command.downgrade(config, PREVIOUS_REVISION)

    assert "inventory_reservations" in inspect(engine).get_table_names()
    engine.dispose()
    get_settings.cache_clear()


def test_inventory_operations_revision_renders_postgresql_boolean_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://plan05_4b:plan05_4b@localhost/plan05_4b",
    )
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "plan05-4b-task1-offline-postgresql-secret",
    )
    get_settings.cache_clear()
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    try:
        command.upgrade(
            config,
            f"{PREVIOUS_REVISION}:{REVISION}",
            sql=True,
        )
    finally:
        get_settings.cache_clear()

    sql = output.getvalue()
    assert "allow_partial BOOLEAN DEFAULT false NOT NULL" in sql
    assert "BOOLEAN DEFAULT 0" not in sql


def test_inventory_operation_tables_compile_for_postgresql() -> None:
    assert OPERATION_TABLES <= set(Base.metadata.tables)
    for table_name in sorted(OPERATION_TABLES):
        table = Base.metadata.tables[table_name]
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CHECK" in ddl
        if table_name != "inventory_reservations":
            assert "FOREIGN KEY" in ddl
        if table_name.endswith("_lines"):
            assert "NUMERIC(18, 4)" in ddl
        if table_name == "inventory_reservations":
            assert "allow_partial BOOLEAN DEFAULT false NOT NULL" in ddl
            assert "BOOLEAN DEFAULT 0" not in ddl
        for index in table.indexes:
            index_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
            assert table_name in index_ddl
