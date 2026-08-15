from __future__ import annotations

from collections.abc import Iterator

import app.models  # noqa: F401
import pytest
from app.db.base import Base
from app.models.equipment import EquipmentModel
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

TENANT_TABLES = {
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_locations",
    "inventory_policies",
    "inventory_expiry_rules",
    "inventory_lots",
    "serialized_items",
    "inventory_balances",
    "inventory_transactions",
    "inventory_target_receipts",
    "inventory_ledger_entries",
    "inventory_reservations",
    "inventory_reservation_lines",
    "inventory_transfers",
    "inventory_transfer_lines",
    "stocktakes",
    "stocktake_lines",
    "suppliers",
    "supplier_offers",
    "repair_profiles",
    "demand_scenario_templates",
    "demand_scenario_versions",
    "demand_scenario_stages",
    "demand_fleet_groups",
    "demand_age_groups",
    "demand_stage_fleet_usages",
    "demand_parameter_overrides",
    "demand_common_shock_rules",
    "demand_calculations",
    "demand_calculation_runs",
    "demand_run_item_results",
    "demand_run_contributions",
    "ai_sessions",
    "ai_messages",
    "ai_session_snapshots",
    "ai_events",
    "ai_model_calls",
    "ai_execution_plans",
    "ai_plan_steps",
    "ai_tool_calls",
    "ai_confirmation_requests",
    "ai_evidence_packages",
    "ai_evidence_items",
    "ai_review_runs",
    "ai_review_findings",
    "ai_report_jobs",
    "ai_report_versions",
    "ai_report_sections",
    "ai_report_citations",
    "ai_report_validation_findings",
    "ai_report_exports",
    "master_data_import_tasks",
    "inventory_target_receipts",
    "calculation_groups",
    "calculation_group_children",
    "calculation_group_events",
    "calculation_item_decisions",
    "demand_lists",
    "demand_list_items",
    "demand_list_events",
}

VERSIONED_TABLES = {
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "suppliers",
    "supplier_offers",
    "repair_profiles",
    "demand_scenario_templates",
    "demand_scenario_versions",
    "demand_calculations",
    "ai_sessions",
    "ai_execution_plans",
    "ai_review_runs",
    "ai_report_jobs",
    "master_data_import_tasks",
    "calculation_groups",
    "calculation_item_decisions",
    "demand_lists",
    "demand_list_items",
}

TENANT_UNIQUE_INDEXES = {
    ("equipment_models", frozenset({"tenant_id", "code"})),
    ("parts", frozenset({"tenant_id", "code"})),
    ("spare_parts", frozenset({"tenant_id", "code"})),
    ("warehouses", frozenset({"tenant_id", "code"})),
    ("suppliers", frozenset({"tenant_id", "code"})),
    ("supplier_offers", frozenset({"tenant_id", "offer_code"})),
    (
        "reliability_profiles",
        frozenset({"tenant_id", "profile_code"}),
    ),
    ("repair_profiles", frozenset({"tenant_id", "profile_code"})),
    (
        "demand_scenario_templates",
        frozenset({"tenant_id", "code"}),
    ),
    (
        "demand_calculations",
        frozenset({"tenant_id", "calculation_code"}),
    ),
    (
        "demand_calculations",
        frozenset({"tenant_id", "idempotency_key"}),
    ),
    ("ai_sessions", frozenset({"tenant_id", "session_code"})),
    ("ai_model_calls", frozenset({"tenant_id", "request_id"})),
    (
        "ai_tool_calls",
        frozenset({"tenant_id", "idempotency_key"}),
    ),
    ("ai_report_jobs", frozenset({"tenant_id", "report_code"})),
    (
        "warehouse_locations",
        frozenset({"tenant_id", "warehouse_id", "code"}),
    ),
    (
        "inventory_policies",
        frozenset({"tenant_id", "warehouse_id", "spare_part_id"}),
    ),
    (
        "inventory_lots",
        frozenset({"tenant_id", "spare_part_id", "lot_code"}),
    ),
    ("serialized_items", frozenset({"tenant_id", "serial_number"})),
    (
        "inventory_transactions",
        frozenset({"tenant_id", "operation_type", "idempotency_key"}),
    ),
    (
        "inventory_target_receipts",
        frozenset({"tenant_id", "idempotency_key"}),
    ),
}


@pytest.fixture()
def engine() -> Iterator[Engine]:
    current = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(current)
    try:
        yield current
    finally:
        current.dispose()


def test_model_registry_matches_the_tenant_contract() -> None:
    assert set(Base.metadata.tables) == TENANT_TABLES


def test_every_business_table_has_non_null_indexed_tenant_id(
    engine: Engine,
) -> None:
    inspector = inspect(engine)

    for table_name in sorted(TENANT_TABLES):
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table_name)
        }
        assert columns["tenant_id"]["nullable"] is False

        indexed_columns = {
            column_name
            for index in inspector.get_indexes(table_name)
            for column_name in index["column_names"]
        }
        assert "tenant_id" in indexed_columns


def test_selected_aggregate_roots_have_version_one(
    engine: Engine,
) -> None:
    inspector = inspect(engine)

    for table_name in sorted(VERSIONED_TABLES):
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table_name)
        }
        assert columns["version"]["nullable"] is False
        assert columns["version"]["default"] is not None


def test_global_business_keys_are_unique_per_tenant(
    engine: Engine,
) -> None:
    inspector = inspect(engine)

    indexes_by_table = {
        table_name: {
            frozenset(item["column_names"])
            for item in (
                [
                    index
                    for index in inspector.get_indexes(table_name)
                    if index["unique"]
                ]
                + inspector.get_unique_constraints(table_name)
            )
        }
        for table_name in TENANT_TABLES
    }

    for table_name, expected_columns in TENANT_UNIQUE_INDEXES:
        assert expected_columns in indexes_by_table[table_name]


def test_same_equipment_code_is_allowed_in_different_tenants(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        session.add_all(
            [
                EquipmentModel(
                    tenant_id="tenant-a",
                    code="EQ-001",
                    name="Tenant A equipment",
                ),
                EquipmentModel(
                    tenant_id="tenant-b",
                    code="EQ-001",
                    name="Tenant B equipment",
                ),
            ]
        )
        session.commit()


def test_duplicate_equipment_code_is_rejected_inside_one_tenant(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        session.add_all(
            [
                EquipmentModel(
                    tenant_id="tenant-a",
                    code="EQ-001",
                    name="First",
                ),
                EquipmentModel(
                    tenant_id="tenant-a",
                    code="EQ-001",
                    name="Second",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_version_defaults_to_one_on_insert(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        row = EquipmentModel(
            tenant_id="tenant-a",
            code="EQ-001",
            name="Equipment",
        )
        session.add(row)
        session.flush()

        assert row.version == 1
