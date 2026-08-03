from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import SERVICE_ROOT, get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

TENANT_SECURITY_REVISION = "6c2dc8414b2f"

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
    "inventory_ledger_entries",
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
}

VERSIONED_TABLES = {
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
}


def migration_config(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Config:
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "unit-five-internal-jwt-secret-0001",
    )
    get_settings.cache_clear()

    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(SERVICE_ROOT / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def previous_revision(config: Config) -> str:
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(TENANT_SECURITY_REVISION)
    assert revision is not None
    assert isinstance(revision.down_revision, str)
    return revision.down_revision


def insert_legacy_equipment(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        now = datetime.now(timezone.utc)
        connection.execute(
            text(
                "INSERT INTO equipment_models "
                "(code, name, is_active, created_at, updated_at) "
                "VALUES "
                "(:code, :name, :is_active, :created_at, :updated_at)"
            ),
            {
                "code": "LEGACY-EQ",
                "name": "Legacy equipment",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        )
    engine.dispose()


def assert_tenant_schema(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)

    for table_name in TENANT_TABLES:
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

    for table_name in VERSIONED_TABLES:
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table_name)
        }
        assert columns["version"]["nullable"] is False

    unique_indexes = {
        (
            table_name,
            frozenset(index["column_names"]),
        )
        for table_name in TENANT_TABLES
        for index in inspector.get_indexes(table_name)
        if index["unique"]
    }
    assert TENANT_UNIQUE_INDEXES <= unique_indexes
    engine.dispose()


def test_upgrade_refuses_implicit_legacy_tenant_before_ddl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "refuse.db"
    config = migration_config(database_path, monkeypatch)
    previous = previous_revision(config)
    command.upgrade(config, previous)
    insert_legacy_equipment(database_path)
    monkeypatch.delenv("MAINTENANCE_LEGACY_TENANT_ID", raising=False)
    get_settings.cache_clear()

    with pytest.raises(
        RuntimeError,
        match="MAINTENANCE_LEGACY_TENANT_ID is required",
    ):
        command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("equipment_models")
    }
    assert "tenant_id" not in columns
    assert "version" not in columns
    engine.dispose()


def test_upgrade_backfills_and_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "round-trip.db"
    config = migration_config(database_path, monkeypatch)
    previous = previous_revision(config)
    command.upgrade(config, previous)
    insert_legacy_equipment(database_path)
    monkeypatch.setenv(
        "MAINTENANCE_LEGACY_TENANT_ID",
        "legacy-tenant",
    )
    get_settings.cache_clear()

    command.upgrade(config, "head")
    assert_tenant_schema(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        tenant_id = connection.scalar(
            text(
                "SELECT tenant_id FROM equipment_models "
                "WHERE code = 'LEGACY-EQ'"
            )
        )
        version = connection.scalar(
            text(
                "SELECT version FROM equipment_models "
                "WHERE code = 'LEGACY-EQ'"
            )
        )
    assert tenant_id == "legacy-tenant"
    assert version == 1
    engine.dispose()

    command.downgrade(config, previous)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("equipment_models")
    }
    assert "tenant_id" not in columns
    assert "version" not in columns
    old_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("equipment_models")
    }
    assert bool(old_indexes["ix_equipment_models_code"]["unique"])
    engine.dispose()

    command.upgrade(config, "head")
    assert_tenant_schema(database_path)


def test_migrated_unique_indexes_allow_cross_tenant_codes_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "tenant-unique.db"
    config = migration_config(database_path, monkeypatch)
    monkeypatch.delenv("MAINTENANCE_LEGACY_TENANT_ID", raising=False)
    get_settings.cache_clear()
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    now = datetime.now(timezone.utc)
    statement = text(
        "INSERT INTO equipment_models "
        "(tenant_id, version, code, name, is_active, "
        "created_at, updated_at) VALUES "
        "(:tenant_id, 1, :code, :name, 1, :now, :now)"
    )

    with engine.begin() as connection:
        connection.execute(
            statement,
            {
                "tenant_id": "tenant-a",
                "code": "EQ",
                "name": "A",
                "now": now,
            },
        )
        connection.execute(
            statement,
            {
                "tenant_id": "tenant-b",
                "code": "EQ",
                "name": "B",
                "now": now,
            },
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                statement,
                {
                    "tenant_id": "tenant-a",
                    "code": "EQ",
                    "name": "Duplicate",
                    "now": now,
                },
            )

    engine.dispose()


def test_downgrade_refuses_multi_tenant_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "multi-tenant.db"
    config = migration_config(database_path, monkeypatch)
    monkeypatch.delenv("MAINTENANCE_LEGACY_TENANT_ID", raising=False)
    get_settings.cache_clear()
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO equipment_models "
                "(tenant_id, version, code, name, is_active, "
                "created_at, updated_at) VALUES "
                "(:tenant_id, 1, :code, :name, 1, :now, :now)"
            ),
            [
                {
                    "tenant_id": "tenant-a",
                    "code": "EQ-A",
                    "name": "A",
                    "now": now,
                },
                {
                    "tenant_id": "tenant-b",
                    "code": "EQ-B",
                    "name": "B",
                    "now": now,
                },
            ],
        )
    engine.dispose()

    with pytest.raises(
        RuntimeError,
        match="multiple tenants",
    ):
        command.downgrade(config, previous_revision(config))
