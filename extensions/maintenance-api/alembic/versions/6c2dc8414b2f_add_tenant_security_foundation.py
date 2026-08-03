from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c2dc8414b2f"
down_revision: str | None = "20260724_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_inventories",
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
)

VERSIONED_TABLES = (
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_inventories",
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
)

UNIQUE_INDEX_REPLACEMENTS = (
    ("equipment_models", "code", "ix_equipment_models_code", "uq_equipment_models_tenant_code"),
    ("parts", "code", "ix_parts_code", "uq_parts_tenant_code"),
    ("spare_parts", "code", "ix_spare_parts_code", "uq_spare_parts_tenant_code"),
    ("warehouses", "code", "ix_warehouses_code", "uq_warehouses_tenant_code"),
    ("suppliers", "code", "ix_suppliers_code", "uq_suppliers_tenant_code"),
    (
        "supplier_offers",
        "offer_code",
        "ix_supplier_offers_offer_code",
        "uq_supplier_offers_tenant_offer_code",
    ),
    (
        "reliability_profiles",
        "profile_code",
        "ix_reliability_profiles_profile_code",
        "uq_reliability_profiles_tenant_profile_code",
    ),
    (
        "repair_profiles",
        "profile_code",
        "ix_repair_profiles_profile_code",
        "uq_repair_profiles_tenant_profile_code",
    ),
    (
        "demand_scenario_templates",
        "code",
        "ix_demand_scenario_templates_code",
        "uq_demand_scenario_templates_tenant_code",
    ),
    (
        "demand_calculations",
        "calculation_code",
        "ix_demand_calculations_calculation_code",
        "uq_demand_calculations_tenant_code",
    ),
    (
        "demand_calculations",
        "idempotency_key",
        "ix_demand_calculations_idempotency_key",
        "uq_demand_calculations_tenant_idempotency",
    ),
    (
        "ai_sessions",
        "session_code",
        "ix_ai_sessions_session_code",
        "uq_ai_sessions_tenant_code",
    ),
    (
        "ai_model_calls",
        "request_id",
        "ix_ai_model_calls_request_id",
        "uq_ai_model_calls_tenant_request",
    ),
    (
        "ai_tool_calls",
        "idempotency_key",
        "ix_ai_tool_calls_idempotency_key",
        "uq_ai_tool_calls_tenant_idempotency",
    ),
    (
        "ai_report_jobs",
        "report_code",
        "ix_ai_report_jobs_report_code",
        "uq_ai_report_jobs_tenant_code",
    ),
)


def _column_details(table_name: str) -> dict[str, dict[str, object]]:
    inspector = sa.inspect(op.get_bind())
    return {
        column["name"]: column
        for column in inspector.get_columns(table_name)
    }


def _indexes(table_name: str) -> dict[str, dict[str, object]]:
    inspector = sa.inspect(op.get_bind())
    return {
        index["name"]: index
        for index in inspector.get_indexes(table_name)
    }


def _quote(identifier: str) -> str:
    return op.get_bind().dialect.identifier_preparer.quote(identifier)


def _table_has_unassigned_rows(table_name: str) -> bool:
    columns = _column_details(table_name)
    table = _quote(table_name)

    if "tenant_id" in columns:
        query = (
            f"SELECT 1 FROM {table} "
            "WHERE tenant_id IS NULL LIMIT 1"
        )
    else:
        query = f"SELECT 1 FROM {table} LIMIT 1"

    return op.get_bind().execute(sa.text(query)).first() is not None


def _legacy_tenant_id() -> str | None:
    value = os.getenv("MAINTENANCE_LEGACY_TENANT_ID", "").strip()
    if not value:
        return None
    if len(value) > 64:
        raise RuntimeError(
            "MAINTENANCE_LEGACY_TENANT_ID must contain "
            "at most 64 characters"
        )
    return value


def _require_backfill_tenant() -> str | None:
    tenant_id = _legacy_tenant_id()
    populated = [
        table_name
        for table_name in TENANT_TABLES
        if _table_has_unassigned_rows(table_name)
    ]

    if populated and tenant_id is None:
        joined = ", ".join(populated)
        raise RuntimeError(
            "MAINTENANCE_LEGACY_TENANT_ID is required because "
            f"legacy rows need tenant assignment in: {joined}"
        )

    return tenant_id


def _backfill_tenant(table_name: str, tenant_id: str) -> None:
    table = sa.table(
        table_name,
        sa.column("tenant_id", sa.String(length=64)),
    )
    op.execute(
        table.update()
        .where(table.c.tenant_id.is_(None))
        .values(tenant_id=tenant_id)
    )


def _ensure_tenant_column(
    table_name: str,
    tenant_id: str | None,
) -> None:
    columns = _column_details(table_name)

    if "tenant_id" not in columns:
        op.add_column(
            table_name,
            sa.Column(
                "tenant_id",
                sa.String(length=64),
                nullable=True,
            ),
        )

    if tenant_id is not None:
        _backfill_tenant(table_name, tenant_id)

    columns = _column_details(table_name)
    tenant_column = columns["tenant_id"]
    if tenant_column["nullable"]:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "tenant_id",
                existing_type=sa.String(length=64),
                nullable=False,
            )

    tenant_index = f"ix_{table_name}_tenant_id"
    if tenant_index not in _indexes(table_name):
        op.create_index(
            tenant_index,
            table_name,
            ["tenant_id"],
            unique=False,
        )


def _ensure_version_column(table_name: str) -> None:
    columns = _column_details(table_name)

    if "version" not in columns:
        op.add_column(
            table_name,
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
        return

    version_column = columns["version"]
    if version_column["nullable"]:
        table = sa.table(
            table_name,
            sa.column("version", sa.Integer()),
        )
        op.execute(
            table.update()
            .where(table.c.version.is_(None))
            .values(version=1)
        )
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "version",
                existing_type=sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )


def _ensure_tenant_unique_index(
    table_name: str,
    column_name: str,
    old_index_name: str,
    new_index_name: str,
) -> None:
    indexes = _indexes(table_name)

    if new_index_name not in indexes:
        op.create_index(
            new_index_name,
            table_name,
            ["tenant_id", column_name],
            unique=True,
        )

    indexes = _indexes(table_name)
    old_index = indexes.get(old_index_name)

    if old_index is None:
        op.create_index(
            old_index_name,
            table_name,
            [column_name],
            unique=False,
        )
    elif old_index["unique"]:
        op.drop_index(old_index_name, table_name=table_name)
        op.create_index(
            old_index_name,
            table_name,
            [column_name],
            unique=False,
        )


def upgrade() -> None:
    tenant_id = _require_backfill_tenant()

    for table_name in TENANT_TABLES:
        _ensure_tenant_column(table_name, tenant_id)

    for table_name in VERSIONED_TABLES:
        _ensure_version_column(table_name)

    for (
        table_name,
        column_name,
        old_index_name,
        new_index_name,
    ) in UNIQUE_INDEX_REPLACEMENTS:
        _ensure_tenant_unique_index(
            table_name,
            column_name,
            old_index_name,
            new_index_name,
        )


def _distinct_tenants() -> set[str]:
    tenants: set[str] = set()

    for table_name in TENANT_TABLES:
        columns = _column_details(table_name)
        if "tenant_id" not in columns:
            continue

        table = _quote(table_name)
        rows = op.get_bind().execute(
            sa.text(
                f"SELECT DISTINCT tenant_id FROM {table} "
                "WHERE tenant_id IS NOT NULL"
            )
        )
        tenants.update(row[0] for row in rows)

    return tenants


def _assert_global_unique(
    table_name: str,
    column_name: str,
) -> None:
    table = _quote(table_name)
    column = _quote(column_name)

    duplicate = op.get_bind().execute(
        sa.text(
            f"SELECT {column}, COUNT(*) FROM {table} "
            f"WHERE {column} IS NOT NULL "
            f"GROUP BY {column} HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()

    if duplicate is not None:
        raise RuntimeError(
            "cannot downgrade tenant security because restoring "
            f"global uniqueness would conflict on "
            f"{table_name}.{column_name}"
        )


def _restore_global_unique_index(
    table_name: str,
    column_name: str,
    old_index_name: str,
    new_index_name: str,
) -> None:
    indexes = _indexes(table_name)

    if new_index_name in indexes:
        op.drop_index(new_index_name, table_name=table_name)

    indexes = _indexes(table_name)
    if old_index_name in indexes:
        op.drop_index(old_index_name, table_name=table_name)

    op.create_index(
        old_index_name,
        table_name,
        [column_name],
        unique=True,
    )


def downgrade() -> None:
    tenants = _distinct_tenants()
    if len(tenants) > 1:
        raise RuntimeError(
            "cannot downgrade tenant security while multiple tenants exist"
        )

    for (
        table_name,
        column_name,
        _old_index_name,
        _new_index_name,
    ) in UNIQUE_INDEX_REPLACEMENTS:
        _assert_global_unique(table_name, column_name)

    for (
        table_name,
        column_name,
        old_index_name,
        new_index_name,
    ) in reversed(UNIQUE_INDEX_REPLACEMENTS):
        _restore_global_unique_index(
            table_name,
            column_name,
            old_index_name,
            new_index_name,
        )

    for table_name in reversed(VERSIONED_TABLES):
        if "version" in _column_details(table_name):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_column("version")

    for table_name in reversed(TENANT_TABLES):
        columns = _column_details(table_name)
        if "tenant_id" not in columns:
            continue

        tenant_index = f"ix_{table_name}_tenant_id"
        if tenant_index in _indexes(table_name):
            op.drop_index(
                tenant_index,
                table_name=table_name,
            )

        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("tenant_id")
