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

FEATURE_MISSING = "PLAN05_4C_TASK1_FEATURE_MISSING"
REVISION = "20260803_12"
PREVIOUS_REVISION = "20260803_11"
REVIEW_TABLES = {
    "demand_list_reviews",
    "demand_list_review_findings",
    "demand_list_review_decisions",
    "demand_list_review_events",
}
PARENT_INDEXES = {
    "demand_lists": "uq_demand_lists_tenant_id_id",
    "demand_list_items": "uq_demand_list_items_tenant_id_id",
}


def _feature_missing(message: str) -> None:
    pytest.fail(f"{FEATURE_MISSING}: {message}", pytrace=False)


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "plan05-4c-task1-red-migration-secret-0001",
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
            "Alembic revision 20260803_12_authoritative_demand_review.py "
            "does not exist"
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


def _source_fact_hash(engine) -> str:
    payload: dict[str, list[dict[str, str]]] = {}
    with engine.connect() as connection:
        for table_name in (
            "demand_lists",
            "demand_list_items",
            "inventory_transactions",
        ):
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
                "101, 'Task 1 source', 'preservation fixture', "
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
                "'task1-preservation-inventory', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                ":response_snapshot, 'TASK1_RED', 'source-101', "
                "'Task 1 preservation fixture', NULL, NULL, "
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


def _assert_review_schema(inspector) -> None:
    assert REVIEW_TABLES <= set(inspector.get_table_names())

    assert PARENT_INDEXES["demand_lists"] in _unique_index_columns(
        inspector,
        "demand_lists",
    )
    assert _unique_index_columns(
        inspector,
        "demand_lists",
    )[PARENT_INDEXES["demand_lists"]] == ("tenant_id", "id")

    assert PARENT_INDEXES["demand_list_items"] in _unique_index_columns(
        inspector,
        "demand_list_items",
    )
    assert _unique_index_columns(
        inspector,
        "demand_list_items",
    )[PARENT_INDEXES["demand_list_items"]] == ("tenant_id", "id")

    assert ("tenant_id", "id") in _unique_column_sets(
        inspector,
        "demand_list_reviews",
    )
    assert ("tenant_id", "id") in _unique_column_sets(
        inspector,
        "demand_list_review_findings",
    )

    review_fks = _foreign_key_sets(inspector, "demand_list_reviews")
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in review_fks
    assert (
        ("tenant_id", "derived_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in review_fks

    finding_fks = _foreign_key_sets(
        inspector,
        "demand_list_review_findings",
    )
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in finding_fks
    assert (
        ("tenant_id", "source_demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in finding_fks

    decision_fks = _foreign_key_sets(
        inspector,
        "demand_list_review_decisions",
    )
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in decision_fks
    assert (
        ("tenant_id", "finding_id"),
        "demand_list_review_findings",
        ("tenant_id", "id"),
    ) in decision_fks

    event_fks = _foreign_key_sets(
        inspector,
        "demand_list_review_events",
    )
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in event_fks


def test_demand_review_revision_chain_is_exact() -> None:
    config = Config("alembic.ini")
    revision = _revision(config)
    assert revision.revision == REVISION
    assert revision.down_revision == PREVIOUS_REVISION



def test_demand_review_upgrade_roundtrip_preserves_source_facts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(tmp_path / "demand-review-task1.db", monkeypatch)
    _revision(config)

    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)

    before_inspector = inspect(engine)
    assert PARENT_INDEXES["demand_lists"] not in _unique_index_columns(
        before_inspector,
        "demand_lists",
    )
    assert PARENT_INDEXES["demand_list_items"] not in _unique_index_columns(
        before_inspector,
        "demand_list_items",
    )

    before_list_columns = _column_signature(before_inspector, "demand_lists")
    before_item_columns = _column_signature(
        before_inspector,
        "demand_list_items",
    )

    _seed_source_facts(engine)
    before_hash = _source_fact_hash(engine)

    command.upgrade(config, REVISION)
    upgraded = inspect(engine)
    _assert_review_schema(upgraded)

    assert _column_signature(upgraded, "demand_lists") == before_list_columns
    assert _column_signature(
        upgraded,
        "demand_list_items",
    ) == before_item_columns
    assert _source_fact_hash(engine) == before_hash

    command.downgrade(config, PREVIOUS_REVISION)
    downgraded = inspect(engine)
    assert REVIEW_TABLES.isdisjoint(set(downgraded.get_table_names()))
    assert PARENT_INDEXES["demand_lists"] not in _unique_index_columns(
        downgraded,
        "demand_lists",
    )
    assert PARENT_INDEXES["demand_list_items"] not in _unique_index_columns(
        downgraded,
        "demand_list_items",
    )
    assert _column_signature(downgraded, "demand_lists") == before_list_columns
    assert _column_signature(
        downgraded,
        "demand_list_items",
    ) == before_item_columns
    assert _source_fact_hash(engine) == before_hash

    command.upgrade(config, REVISION)
    reupgraded = inspect(engine)
    _assert_review_schema(reupgraded)
    assert _source_fact_hash(engine) == before_hash
    with engine.connect() as connection:
        current_revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert current_revision == REVISION

    engine.dispose()
    get_settings.cache_clear()


def test_demand_review_revision_does_not_touch_inventory_or_ai_review_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, url = _config(tmp_path / "demand-review-scope.db", monkeypatch)
    _revision(config)

    command.upgrade(config, PREVIOUS_REVISION)
    engine = create_engine(url)
    before = inspect(engine)

    protected_tables = sorted(
        table_name
        for table_name in before.get_table_names()
        if table_name.startswith("inventory_")
        or table_name.startswith("ai_review")
    )
    before_columns = {
        table_name: _column_signature(before, table_name)
        for table_name in protected_tables
    }

    command.upgrade(config, REVISION)
    after = inspect(engine)
    assert {
        table_name: _column_signature(after, table_name)
        for table_name in protected_tables
    } == before_columns

    engine.dispose()
    get_settings.cache_clear()
