"""add allocation assurance persistence

Revision ID: 20260803_13
Revises: 20260803_12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_13"
down_revision: str | None = "20260803_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_index(
        "uq_inventory_balances_tenant_id_id",
        "inventory_balances",
        ["tenant_id", "id"],
        unique=True,
    )

    op.create_table(
        "allocation_rule_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lineage_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *RULE_STATUSES,
                name="allocationrulestatus",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hard_rules_json", sa.JSON(), nullable=False),
        sa.Column("weights_json", sa.JSON(), nullable=False),
        sa.Column("normalization_json", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("published_by_user_id", sa.String(length=128), nullable=True),
        sa.Column("published_by_request_id", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_allocation_rule_version"),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_allocation_rule_version_number",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL "
            "OR effective_to > effective_from",
            name="ck_allocation_rule_effective_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_allocation_rule_version_tenant_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "lineage_id",
            "version_number",
            name="uq_allocation_rule_lineage_version",
        ),
    )
    op.create_index(
        "ix_allocation_rule_versions_tenant_id",
        "allocation_rule_versions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_rule_versions_tenant_status",
        "allocation_rule_versions",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_allocation_rule_versions_tenant_effective",
        "allocation_rule_versions",
        ["tenant_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "allocation_simulations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_rule_id", sa.Integer(), nullable=False),
        sa.Column("baseline_rule_id", sa.Integer(), nullable=True),
        sa.Column("source_demand_list_id", sa.Integer(), nullable=False),
        sa.Column("sample_ref", sa.String(length=128), nullable=True),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("inventory_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *SIMULATION_STATUSES,
                name="allocationsimulationstatus",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_allocation_simulation_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "candidate_rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "baseline_rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_allocation_simulation_tenant_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_allocation_simulation_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_allocation_simulations_tenant_id",
        "allocation_simulations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_simulations_tenant_status",
        "allocation_simulations",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_allocation_simulations_tenant_candidate",
        "allocation_simulations",
        ["tenant_id", "candidate_rule_id"],
    )

    op.create_table(
        "allocation_simulation_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_id", sa.Integer(), nullable=False),
        sa.Column("demand_list_item_id", sa.Integer(), nullable=False),
        sa.Column("candidate_balance_id", sa.Integer(), nullable=True),
        sa.Column("baseline_rank", sa.Integer(), nullable=True),
        sa.Column("candidate_rank", sa.Integer(), nullable=True),
        sa.Column("baseline_score", sa.Numeric(20, 6), nullable=True),
        sa.Column("candidate_score", sa.Numeric(20, 6), nullable=True),
        sa.Column("score_delta", sa.Numeric(20, 6), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "baseline_rank IS NULL OR baseline_rank >= 1",
            name="ck_allocation_simulation_result_baseline_rank",
        ),
        sa.CheckConstraint(
            "candidate_rank IS NULL OR candidate_rank >= 1",
            name="ck_allocation_simulation_result_candidate_rank",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "simulation_id"],
            ["allocation_simulations.tenant_id", "allocation_simulations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "candidate_balance_id"],
            ["inventory_balances.tenant_id", "inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_allocation_simulation_result_tenant_id",
        ),
    )
    op.create_index(
        "ix_allocation_simulation_results_tenant_id",
        "allocation_simulation_results",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_simulation_results_tenant_simulation",
        "allocation_simulation_results",
        ["tenant_id", "simulation_id"],
    )

    op.create_table(
        "allocation_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_demand_list_id", sa.Integer(), nullable=False),
        sa.Column("source_demand_list_version", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("inventory_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *PLAN_STATUSES,
                name="allocationplanstatus",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_allocation_plan_version"),
        sa.CheckConstraint(
            "source_demand_list_version >= 1",
            name="ck_allocation_plan_source_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["allocation_rule_versions.tenant_id", "allocation_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_allocation_plan_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_allocation_plan_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_allocation_plans_tenant_id",
        "allocation_plans",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_plans_tenant_status",
        "allocation_plans",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_allocation_plans_tenant_source",
        "allocation_plans",
        ["tenant_id", "source_demand_list_id"],
    )

    op.create_table(
        "allocation_plan_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("demand_list_item_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("recommended_balance_id", sa.Integer(), nullable=True),
        sa.Column("recommended_lot_id", sa.Integer(), nullable=True),
        sa.Column("recommended_serial_item_id", sa.Integer(), nullable=True),
        sa.Column("demand_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("allocated_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("gap_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("risks_json", sa.JSON(), nullable=False),
        sa.Column("manual_override_json", sa.JSON(), nullable=True),
        sa.Column("expected_balance_version", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_allocation_plan_line_version"),
        sa.CheckConstraint(
            "demand_quantity >= 0",
            name="ck_allocation_plan_line_demand_nonnegative",
        ),
        sa.CheckConstraint(
            "allocated_quantity >= 0",
            name="ck_allocation_plan_line_allocated_nonnegative",
        ),
        sa.CheckConstraint(
            "gap_quantity >= 0",
            name="ck_allocation_plan_line_gap_nonnegative",
        ),
        sa.CheckConstraint(
            "expected_balance_version >= 1",
            name="ck_allocation_plan_line_expected_balance_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "plan_id"],
            ["allocation_plans.tenant_id", "allocation_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recommended_balance_id"],
            ["inventory_balances.tenant_id", "inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["inventory_reservations.tenant_id", "inventory_reservations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_allocation_plan_line_tenant_id",
        ),
    )
    op.create_index(
        "ix_allocation_plan_lines_tenant_id",
        "allocation_plan_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_plan_lines_tenant_plan",
        "allocation_plan_lines",
        ["tenant_id", "plan_id"],
    )

    op.create_table(
        "allocation_plan_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("response_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "plan_id"],
            ["allocation_plans.tenant_id", "allocation_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_allocation_plan_events_tenant_id",
        "allocation_plan_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_allocation_plan_events_tenant_plan",
        "allocation_plan_events",
        ["tenant_id", "plan_id"],
    )
    op.create_index(
        "ix_allocation_plan_events_tenant_request",
        "allocation_plan_events",
        ["tenant_id", "request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_allocation_plan_events_tenant_request",
        table_name="allocation_plan_events",
    )
    op.drop_index(
        "ix_allocation_plan_events_tenant_plan",
        table_name="allocation_plan_events",
    )
    op.drop_index(
        "ix_allocation_plan_events_tenant_id",
        table_name="allocation_plan_events",
    )
    op.drop_table("allocation_plan_events")

    op.drop_index(
        "ix_allocation_plan_lines_tenant_plan",
        table_name="allocation_plan_lines",
    )
    op.drop_index(
        "ix_allocation_plan_lines_tenant_id",
        table_name="allocation_plan_lines",
    )
    op.drop_table("allocation_plan_lines")

    op.drop_index(
        "ix_allocation_plans_tenant_source",
        table_name="allocation_plans",
    )
    op.drop_index(
        "ix_allocation_plans_tenant_status",
        table_name="allocation_plans",
    )
    op.drop_index(
        "ix_allocation_plans_tenant_id",
        table_name="allocation_plans",
    )
    op.drop_table("allocation_plans")

    op.drop_index(
        "ix_allocation_simulation_results_tenant_simulation",
        table_name="allocation_simulation_results",
    )
    op.drop_index(
        "ix_allocation_simulation_results_tenant_id",
        table_name="allocation_simulation_results",
    )
    op.drop_table("allocation_simulation_results")

    op.drop_index(
        "ix_allocation_simulations_tenant_candidate",
        table_name="allocation_simulations",
    )
    op.drop_index(
        "ix_allocation_simulations_tenant_status",
        table_name="allocation_simulations",
    )
    op.drop_index(
        "ix_allocation_simulations_tenant_id",
        table_name="allocation_simulations",
    )
    op.drop_table("allocation_simulations")

    op.drop_index(
        "ix_allocation_rule_versions_tenant_effective",
        table_name="allocation_rule_versions",
    )
    op.drop_index(
        "ix_allocation_rule_versions_tenant_status",
        table_name="allocation_rule_versions",
    )
    op.drop_index(
        "ix_allocation_rule_versions_tenant_id",
        table_name="allocation_rule_versions",
    )
    op.drop_table("allocation_rule_versions")

    op.drop_index(
        "uq_inventory_balances_tenant_id_id",
        table_name="inventory_balances",
    )
