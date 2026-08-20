from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text

FEATURE_MISSING = "PLAN05_4D_TASK1_FEATURE_MISSING"
REVISION = "20260803_13"
PREVIOUS_REVISION = "20260803_12"
BALANCE_PARENT_INDEX = "uq_inventory_balances_tenant_id_id"

ALLOCATION_TABLES = {
    "allocation_rule_versions",
    "allocation_simulations",
    "allocation_simulation_results",
    "allocation_plans",
    "allocation_plan_lines",
    "allocation_plan_events",
}

RULE_STATUSES = ("DRAFT", "SIMULATED", "PUBLISHED", "RETIRED")
SIMULATION_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
PLAN_STATUSES = (
    "DRAFT",
    "PREVIEWED",
    "CONFIRMED",
    "EXECUTING",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "VOIDED",
)

PRESERVED_TABLES = (
    "demand_lists",
    "demand_list_items",
    "demand_list_reviews",
    "inventory_transactions",
    "inventory_reservations",
)


def _feature_missing(message: str) -> None:
    pytest.fail(f"{FEATURE_MISSING}: {message}", pytrace=False)


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "plan05-4d-task1-red-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def _revision(config: Config):
    script = ScriptDirectory.from_config(config)
    try:
        revision = script.get_revision(REVISION)
    except Exception:
        revision = None
    if revision is None:
        _feature_missing(
            "Alembic revision "
            "20260803_13_allocation_assurance.py does not exist"
        )
    return revision


def _unique_index_columns(inspector, table_name: str) -> dict[str, tuple[str, ...]]:
    return {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes(table_name)
        if index.get("unique") and index.get("name")
    }


def _unique_column_sets(inspector, table_name: str) -> set[tuple[str, ...]]:
    result = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints(table_name)
    }
    result.update(_unique_index_columns(inspector, table_name).values())
    return result


def _foreign_key_sets(
    inspector,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            tuple(item["referred_columns"]),
        )
        for item in inspector.get_foreign_keys(table_name)
    }


def _column_signature(inspector, table_name: str) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            column["name"],
            str(column["type"]),
            bool(column["nullable"]),
        )
        for column in inspector.get_columns(table_name)
    )


def _normalized_sql(value) -> str:
    return " ".join(str(value).upper().split())


def _check_sql(inspector, table_name: str) -> tuple[str, ...]:
    return tuple(
        _normalized_sql(item["sqltext"])
        for item in inspector.get_check_constraints(table_name)
        if item.get("sqltext")
    )


def _assert_status_allowlist(
    inspector,
    table_name: str,
    expected: tuple[str, ...],
) -> None:
    checks = _check_sql(inspector, table_name)
    matching = [
        sql
        for sql in checks
        if "STATUS" in sql
        and all(
            f"'{value}'" in sql or f'"{value}"' in sql
            for value in expected
        )
    ]
    assert matching, f"{table_name}.status must enforce {expected}"


def _source_fact_hash(engine) -> str:
    payload: dict[str, list[dict[str, str]]] = {}
    with engine.connect() as connection:
        for table_name in PRESERVED_TABLES:
            rows = connection.execute(
                text(f"SELECT * FROM {table_name} ORDER BY id")
            ).mappings()
            payload[table_name] = [
                {key: str(value) for key, value in row.items()}
                for row in rows
            ]

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seed_source_facts(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO demand_lists ("
                "id, name, description, lineage_id, version_number, "
                "derived_from_id, scenario_version_id, calculation_group_id, "
                "status, is_current, superseded_by_id, superseded_at, version, "
                "created_by_user_id, created_by_request_id, "
                "submitted_by_user_id, submitted_by_request_id, submitted_at, "
                "confirmed_by_user_id, confirmed_by_request_id, confirmed_at, "
                "published_by_user_id, published_by_request_id, published_at, "
                "voided_by_user_id, voided_by_request_id, voided_at, "
                "tenant_id, created_at, updated_at"
                ") VALUES ("
                "101, 'Task 1 source', 'allocation preservation fixture', "
                "'11111111-1111-1111-1111-111111111111', 1, "
                "NULL, 9001, 9002, 'PUBLISHED', 1, NULL, NULL, 3, "
                "'admin-a', 'request-create-source', "
                "'contributor-a', 'request-submit-source', CURRENT_TIMESTAMP, "
                "'admin-a', 'request-confirm-source', CURRENT_TIMESTAMP, "
                "'admin-a', 'request-publish-source', CURRENT_TIMESTAMP, "
                "NULL, NULL, NULL, "
                "'tenant-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            )
        )

        connection.execute(
            text(
                "INSERT INTO demand_list_items ("
                "id, demand_list_id, spare_part_id, "
                "spare_part_code_snapshot, spare_part_name_snapshot, "
                "spare_part_unit_snapshot, criticality_level_snapshot, "
                "source_calculation_group_id, source_group_child_id, "
                "source_calculation_id, source_calculation_run_id, "
                "source_result_id, reliability_model, execution_mode, "
                "original_quantity, final_quantity, decision_type, "
                "decision_reason, decision_risk, "
                "requires_admin_confirmation, confirmed_by_admin, "
                "risk_rule_version, source_snapshot_json, "
                "decision_snapshot_json, interval_snapshot_json, "
                "parameter_snapshot_json, warning_snapshot_json, "
                "inventory_snapshot_json, version, tenant_id, "
                "created_at, updated_at"
                ") VALUES ("
                "1001, 101, 5001, "
                "'SP-TASK1', 'Task 1 spare', 'EA', 'HIGH', "
                "NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
                "10.000000, 10.000000, NULL, NULL, NULL, "
                "0, 0, 'risk-v1', :source_snapshot, "
                "NULL, NULL, NULL, NULL, :inventory_snapshot, "
                "2, 'tenant-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "source_snapshot": json.dumps(
                    {"fixture": "task1", "spare_part_id": 5001},
                    sort_keys=True,
                ),
                "inventory_snapshot": json.dumps(
                    {"available": "8.0000"},
                    sort_keys=True,
                ),
            },
        )

        connection.execute(
            text(
                "INSERT INTO demand_list_reviews ("
                "id, source_demand_list_id, source_demand_list_version, "
                "source_lineage_id, source_version_number, status, "
                "rule_set_version, input_hash, source_snapshot_json, "
                "total_finding_count, blocking_finding_count, "
                "pending_finding_count, pending_blocking_finding_count, "
                "derived_demand_list_id, failure_code, failure_summary, "
                "version, tenant_id, created_at, updated_at"
                ") VALUES ("
                "201, 101, 3, "
                "'11111111-1111-1111-1111-111111111111', 1, 'OPEN', "
                "'review-rules-v1', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                ":review_snapshot, 0, 0, 0, 0, NULL, NULL, NULL, "
                "1, 'tenant-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "review_snapshot": json.dumps(
                    {"demand_list_id": 101, "fixture": "allocation-task1"},
                    sort_keys=True,
                ),
            },
        )

        connection.execute(
            text(
                "INSERT INTO inventory_transactions ("
                "id, tenant_id, operation_type, status, "
                "idempotency_key, request_hash, response_snapshot_json, "
                "reference_type, reference_id, reason, "
                "confirmation_token_hash, confirmation_expires_at, "
                "actor_user_id, actor_roles_json, request_id, "
                "reversed_transaction_id, version, created_at, updated_at, "
                "completed_at, failed_at"
                ") VALUES ("
                "7001, 'tenant-a', 'OPENING', 'COMPLETED', "
                "'allocation-task1-inventory', "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                ":response_snapshot, 'ALLOCATION_TASK1', 'source-101', "
                "'Allocation Task 1 preservation fixture', NULL, NULL, "
                "'admin-a', :actor_roles, 'request-inventory-source', "
                "NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, NULL"
                ")"
            ),
            {
                "response_snapshot": json.dumps(
                    {"transaction_id": 7001},
                    sort_keys=True,
                ),
                "actor_roles": json.dumps(["admin"]),
            },
        )

        connection.execute(
            text(
                "INSERT INTO inventory_reservations ("
                "id, tenant_id, owner_type, owner_id, status, expires_at, "
                "allow_partial, actor_user_id, actor_roles_json, request_id, "
                "version, created_at, updated_at"
                ") VALUES ("
                "8001, 'tenant-a', 'DEMAND_LIST', '101', 'ACTIVE', NULL, "
                "1, 'contributor-a', :reservation_roles, "
                "'request-reservation-source', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "reservation_roles": json.dumps(["contributor"]),
            },
        )


def _assert_allocation_schema(inspector) -> None:
    assert ALLOCATION_TABLES <= set(inspector.get_table_names())

    balance_indexes = _unique_index_columns(
        inspector,
        "inventory_balances",
    )
    assert balance_indexes[BALANCE_PARENT_INDEX] == ("tenant_id", "id")

    rule_unique = _unique_column_sets(
        inspector,
        "allocation_rule_versions",
    )
    assert ("tenant_id", "id") in rule_unique
    assert ("tenant_id", "lineage_id", "version_number") in rule_unique

    simulation_unique = _unique_column_sets(
        inspector,
        "allocation_simulations",
    )
    assert ("tenant_id", "id") in simulation_unique
    assert ("tenant_id", "idempotency_key") in simulation_unique

    plan_unique = _unique_column_sets(
        inspector,
        "allocation_plans",
    )
    assert ("tenant_id", "id") in plan_unique
    assert ("tenant_id", "idempotency_key") in plan_unique

    _assert_status_allowlist(
        inspector,
        "allocation_rule_versions",
        RULE_STATUSES,
    )
    _assert_status_allowlist(
        inspector,
        "allocation_simulations",
        SIMULATION_STATUSES,
    )
    _assert_status_allowlist(
        inspector,
        "allocation_plans",
        PLAN_STATUSES,
    )

    simulation_fks = _foreign_key_sets(
        inspector,
        "allocation_simulations",
    )
    assert (
        ("tenant_id", "candidate_rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in simulation_fks
    assert (
        ("tenant_id", "baseline_rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in simulation_fks
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in simulation_fks

    result_fks = _foreign_key_sets(
        inspector,
        "allocation_simulation_results",
    )
    assert (
        ("tenant_id", "simulation_id"),
        "allocation_simulations",
        ("tenant_id", "id"),
    ) in result_fks
    assert (
        ("tenant_id", "demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in result_fks
    assert (
        ("tenant_id", "candidate_balance_id"),
        "inventory_balances",
        ("tenant_id", "id"),
    ) in result_fks

    plan_fks = _foreign_key_sets(
        inspector,
        "allocation_plans",
    )
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in plan_fks
    assert (
        ("tenant_id", "rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in plan_fks

    line_fks = _foreign_key_sets(
        inspector,
        "allocation_plan_lines",
    )
    assert (
        ("tenant_id", "plan_id"),
        "allocation_plans",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "recommended_balance_id"),
        "inventory_balances",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "reservation_id"),
        "inventory_reservations",
        ("tenant_id", "id"),
    ) in line_fks

    event_fks = _foreign_key_sets(
        inspector,
        "allocation_plan_events",
    )
    assert (
        ("tenant_id", "plan_id"),
        "allocation_plans",
        ("tenant_id", "id"),
    ) in event_fks


def test_allocation_revision_chain_is_exact() -> None:
    config = Config("alembic.ini")
    revision = _revision(config)

    assert revision.revision == REVISION
    assert revision.down_revision == PREVIOUS_REVISION

    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [REVISION]


def test_allocation_upgrade_roundtrip_preserves_demand_review_inventory_facts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(
        tmp_path / "allocation-task1.db",
        monkeypatch,
    )
    _revision(config)

    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)

    try:
        before = inspect(engine)
        assert BALANCE_PARENT_INDEX not in _unique_index_columns(
            before,
            "inventory_balances",
        )

        before_columns = {
            table_name: _column_signature(before, table_name)
            for table_name in PRESERVED_TABLES
        }

        _seed_source_facts(engine)
        before_hash = _source_fact_hash(engine)

        command.upgrade(config, REVISION)
        upgraded = inspect(engine)
        _assert_allocation_schema(upgraded)

        assert {
            table_name: _column_signature(upgraded, table_name)
            for table_name in PRESERVED_TABLES
        } == before_columns
        assert _source_fact_hash(engine) == before_hash

        command.downgrade(config, PREVIOUS_REVISION)
        downgraded = inspect(engine)

        assert ALLOCATION_TABLES.isdisjoint(
            set(downgraded.get_table_names())
        )
        assert BALANCE_PARENT_INDEX not in _unique_index_columns(
            downgraded,
            "inventory_balances",
        )
        assert {
            table_name: _column_signature(downgraded, table_name)
            for table_name in PRESERVED_TABLES
        } == before_columns
        assert _source_fact_hash(engine) == before_hash

        command.upgrade(config, REVISION)
        reupgraded = inspect(engine)
        _assert_allocation_schema(reupgraded)
        assert _source_fact_hash(engine) == before_hash

        current_revision = engine.connect().execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert current_revision == REVISION
    finally:
        engine.dispose()
        get_settings.cache_clear()
