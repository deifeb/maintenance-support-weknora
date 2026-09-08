"""add demand lists

Revision ID: 20260731_07
Revises: 20260731_06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_07"
down_revision: str | None = "20260731_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIST_STATUSES = (
    "DRAFT",
    "PENDING_CONFIRMATION",
    "CONFIRMED",
    "PUBLISHED",
    "VOIDED",
)
EVENT_TYPES = (
    "CREATED",
    "ITEM_UPDATED",
    "SUBMITTED",
    "CONFIRMED",
    "PUBLISHED",
    "DERIVED",
    "VOIDED",
)
RELIABILITY_MODELS = (
    "EXPONENTIAL",
    "WEIBULL",
    "BINOMIAL",
    "NEGATIVE_BINOMIAL",
    "EMPIRICAL",
)
EXECUTION_MODES = (
    "AUTO",
    "ANALYTICAL",
    "MONTE_CARLO",
    "COMPARE",
)
DECISION_TYPES = (
    "SYSTEM_RECOMMENDATION",
    "ALTERNATIVE_CANDIDATE",
    "MANUAL_QUANTITY",
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _index(
    name: str,
    table: str,
    *columns: str,
) -> None:
    op.create_index(name, table, list(columns), unique=False)


def upgrade() -> None:
    op.create_table(
        "demand_lists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lineage_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("derived_from_id", sa.Integer(), nullable=True),
        sa.Column("scenario_version_id", sa.Integer(), nullable=False),
        sa.Column("calculation_group_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *LIST_STATUSES,
                name="demandliststatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("created_by_request_id", sa.String(128), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(64), nullable=True),
        sa.Column("submitted_by_request_id", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.String(64), nullable=True),
        sa.Column("confirmed_by_request_id", sa.String(128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.String(64), nullable=True),
        sa.Column("published_by_request_id", sa.String(128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.String(64), nullable=True),
        sa.Column("voided_by_request_id", sa.String(128), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_demand_list_version_number",
        ),
        sa.ForeignKeyConstraint(
            ["derived_from_id"],
            ["demand_lists.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["demand_scenario_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_group_id"],
            ["calculation_groups.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["demand_lists.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "lineage_id",
            "version_number",
            name="uq_demand_list_lineage_version",
        ),
    )
    _index("ix_demand_lists_tenant_id", "demand_lists", "tenant_id")
    _index("ix_demand_lists_lineage_id", "demand_lists", "lineage_id")
    _index("ix_demand_lists_status", "demand_lists", "status")
    _index("ix_demand_lists_is_current", "demand_lists", "is_current")
    _index(
        "ix_demand_lists_scenario_version_id",
        "demand_lists",
        "scenario_version_id",
    )
    _index(
        "ix_demand_lists_calculation_group_id",
        "demand_lists",
        "calculation_group_id",
    )
    op.create_index(
        "uq_demand_lists_current_published_lineage",
        "demand_lists",
        ["tenant_id", "lineage_id"],
        unique=True,
        sqlite_where=sa.text(
            "status = 'PUBLISHED' AND is_current = 1"
        ),
        postgresql_where=sa.text(
            "status = 'PUBLISHED' AND is_current"
        ),
    )

    op.create_table(
        "demand_list_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("demand_list_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_code_snapshot", sa.String(64), nullable=False),
        sa.Column("spare_part_name_snapshot", sa.String(200), nullable=False),
        sa.Column("spare_part_unit_snapshot", sa.String(40), nullable=False),
        sa.Column("criticality_level_snapshot", sa.String(20), nullable=True),
        sa.Column("source_calculation_group_id", sa.Integer(), nullable=True),
        sa.Column("source_group_child_id", sa.Integer(), nullable=True),
        sa.Column("source_calculation_id", sa.Integer(), nullable=True),
        sa.Column("source_calculation_run_id", sa.Integer(), nullable=True),
        sa.Column("source_result_id", sa.Integer(), nullable=True),
        sa.Column(
            "reliability_model",
            sa.Enum(
                *RELIABILITY_MODELS,
                name="reliabilitymodeltype",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "execution_mode",
            sa.Enum(
                *EXECUTION_MODES,
                name="demandexecutionmode",
                native_enum=False,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("original_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("final_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "decision_type",
            sa.Enum(
                *DECISION_TYPES,
                name="calculationdecisiontype",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decision_risk", sa.String(20), nullable=True),
        sa.Column("requires_admin_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by_admin", sa.Boolean(), nullable=False),
        sa.Column("risk_rule_version", sa.String(64), nullable=True),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("decision_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("interval_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("parameter_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("warning_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("inventory_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "original_quantity >= 0",
            name="ck_demand_list_item_original_quantity",
        ),
        sa.CheckConstraint(
            "final_quantity >= 0",
            name="ck_demand_list_item_final_quantity",
        ),
        sa.ForeignKeyConstraint(
            ["demand_list_id"],
            ["demand_lists.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["spare_part_id"],
            ["spare_parts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_calculation_group_id"],
            ["calculation_groups.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_group_child_id"],
            ["calculation_group_children.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_calculation_id"],
            ["demand_calculations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_calculation_run_id"],
            ["demand_calculation_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_result_id"],
            ["demand_run_item_results.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "demand_list_id",
            "spare_part_id",
            name="uq_demand_list_item",
        ),
    )
    _index(
        "ix_demand_list_items_tenant_id",
        "demand_list_items",
        "tenant_id",
    )
    _index(
        "ix_demand_list_items_demand_list_id",
        "demand_list_items",
        "demand_list_id",
    )
    _index(
        "ix_demand_list_items_spare_part_id",
        "demand_list_items",
        "spare_part_id",
    )

    op.create_table(
        "demand_list_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("demand_list_id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                *EVENT_TYPES,
                name="demandlisteventtype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("before_summary_json", sa.JSON(), nullable=True),
        sa.Column("after_summary_json", sa.JSON(), nullable=True),
        sa.Column("response_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["demand_list_id"],
            ["demand_lists.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index(
        "ix_demand_list_events_tenant_id",
        "demand_list_events",
        "tenant_id",
    )
    _index(
        "ix_demand_list_events_demand_list_id",
        "demand_list_events",
        "demand_list_id",
    )
    _index(
        "ix_demand_list_events_event_type",
        "demand_list_events",
        "event_type",
    )
    op.create_index(
        "uq_demand_list_events_tenant_idempotency",
        "demand_list_events",
        ["tenant_id", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("demand_list_events")
    op.drop_table("demand_list_items")
    op.drop_table("demand_lists")
