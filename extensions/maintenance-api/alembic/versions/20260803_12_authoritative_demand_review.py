"""add authoritative demand review persistence

Revision ID: 20260803_12
Revises: 20260803_11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_12"
down_revision: str | None = "20260803_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVIEW_STATUSES = (
    "CREATED",
    "RUNNING",
    "OPEN",
    "READY_TO_DERIVE",
    "DERIVED",
    "FAILED",
    "VOIDED",
)
REVIEW_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
DECISION_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "EDIT_ACCEPTED")
COMMAND_TYPES = ("RUN", "DECIDE_FINDING", "BATCH_DECIDE", "DERIVE", "VOID")
EVENT_TYPES = (
    "CREATED",
    "RUNNING",
    "OPENED",
    "FAILED",
    "DECIDED",
    "BATCH_DECIDED",
    "READY_TO_DERIVE",
    "DERIVED",
    "VOIDED",
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_index(
        "uq_demand_lists_tenant_id_id",
        "demand_lists",
        ["tenant_id", "id"],
        unique=True,
    )
    op.create_index(
        "uq_demand_list_items_tenant_id_id",
        "demand_list_items",
        ["tenant_id", "id"],
        unique=True,
    )

    op.create_table(
        "demand_list_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_demand_list_id", sa.Integer(), nullable=False),
        sa.Column("source_demand_list_version", sa.Integer(), nullable=False),
        sa.Column("source_lineage_id", sa.String(length=36), nullable=False),
        sa.Column("source_version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *REVIEW_STATUSES,
                name="demandreviewstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rule_set_version", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("total_finding_count", sa.Integer(), nullable=False),
        sa.Column("blocking_finding_count", sa.Integer(), nullable=False),
        sa.Column("pending_finding_count", sa.Integer(), nullable=False),
        sa.Column("pending_blocking_finding_count", sa.Integer(), nullable=False),
        sa.Column("derived_demand_list_id", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_demand_review_version"),
        sa.CheckConstraint(
            "source_demand_list_version >= 1",
            name="ck_demand_review_source_version",
        ),
        sa.CheckConstraint(
            "source_version_number >= 1",
            name="ck_demand_review_source_version_number",
        ),
        sa.CheckConstraint(
            "total_finding_count >= 0",
            name="ck_demand_review_total_count",
        ),
        sa.CheckConstraint(
            "blocking_finding_count >= 0",
            name="ck_demand_review_blocking_count",
        ),
        sa.CheckConstraint(
            "pending_finding_count >= 0",
            name="ck_demand_review_pending_count",
        ),
        sa.CheckConstraint(
            "pending_blocking_finding_count >= 0",
            name="ck_demand_review_pending_blocking_count",
        ),
        sa.CheckConstraint(
            "blocking_finding_count <= total_finding_count",
            name="ck_demand_review_blocking_le_total",
        ),
        sa.CheckConstraint(
            "pending_finding_count <= total_finding_count",
            name="ck_demand_review_pending_le_total",
        ),
        sa.CheckConstraint(
            "pending_blocking_finding_count <= blocking_finding_count "
            "AND pending_blocking_finding_count <= pending_finding_count",
            name="ck_demand_review_pending_blocking_bounds",
        ),
        sa.CheckConstraint(
            "(status = 'DERIVED' AND derived_demand_list_id IS NOT NULL) "
            "OR (status <> 'DERIVED' AND derived_demand_list_id IS NULL)",
            name="ck_demand_review_derived_state",
        ),
        sa.CheckConstraint(
            "status = 'FAILED' OR "
            "(failure_code IS NULL AND failure_summary IS NULL)",
            name="ck_demand_review_failure_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "derived_demand_list_id"],
            ["demand_lists.tenant_id", "demand_lists.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_demand_list_review_tenant_id",
        ),
    )
    op.create_index(
        "ix_demand_list_reviews_tenant_id",
        "demand_list_reviews",
        ["tenant_id"],
    )
    op.create_index(
        "ix_demand_list_reviews_tenant_status",
        "demand_list_reviews",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_demand_list_reviews_tenant_source",
        "demand_list_reviews",
        ["tenant_id", "source_demand_list_id"],
    )

    op.create_table(
        "demand_list_review_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("finding_key", sa.String(length=200), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                *REVIEW_SEVERITIES,
                name="demandreviewseverity",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("requires_admin_acceptance", sa.Boolean(), nullable=False),
        sa.Column("source_demand_list_item_id", sa.Integer(), nullable=True),
        sa.Column("effect_key", sa.String(length=200), nullable=True),
        sa.Column("evidence_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("suggestion_snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "decision_status",
            sa.Enum(
                *DECISION_STATUSES,
                name="demandreviewdecisionstatus",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_demand_review_finding_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_demand_list_item_id"],
            ["demand_list_items.tenant_id", "demand_list_items.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_demand_list_review_finding_tenant_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "review_id",
            "finding_key",
            name="uq_demand_review_finding_key",
        ),
    )
    op.create_index(
        "ix_demand_list_review_findings_tenant_id",
        "demand_list_review_findings",
        ["tenant_id"],
    )
    op.create_index(
        "uq_demand_review_finding_effect",
        "demand_list_review_findings",
        ["tenant_id", "review_id", "effect_key"],
        unique=True,
        sqlite_where=sa.text("effect_key IS NOT NULL"),
        postgresql_where=sa.text("effect_key IS NOT NULL"),
    )
    op.create_index(
        "ix_demand_review_findings_tenant_review",
        "demand_list_review_findings",
        ["tenant_id", "review_id"],
    )

    op.create_table(
        "demand_list_review_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("finding_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("suggested_quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("final_quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("review_version_before", sa.Integer(), nullable=False),
        sa.Column("review_version_after", sa.Integer(), nullable=False),
        sa.Column("finding_version_before", sa.Integer(), nullable=False),
        sa.Column("finding_version_after", sa.Integer(), nullable=False),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "action IN ('ACCEPTED', 'REJECTED', 'EDIT_ACCEPTED')",
            name="ck_demand_review_decision_action",
        ),
        sa.CheckConstraint(
            "suggested_quantity IS NULL OR suggested_quantity >= 0",
            name="ck_demand_review_decision_suggested_quantity",
        ),
        sa.CheckConstraint(
            "final_quantity IS NULL OR final_quantity >= 0",
            name="ck_demand_review_decision_final_quantity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            [
                "demand_list_review_findings.tenant_id",
                "demand_list_review_findings.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_demand_list_review_decisions_tenant_id",
        "demand_list_review_decisions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_demand_review_decisions_tenant_review",
        "demand_list_review_decisions",
        ["tenant_id", "review_id"],
    )
    op.create_index(
        "ix_demand_review_decisions_tenant_finding",
        "demand_list_review_decisions",
        ["tenant_id", "finding_id"],
    )

    op.create_table(
        "demand_list_review_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                *EVENT_TYPES,
                name="demandrevieweventtype",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "command_type",
            sa.Enum(
                *COMMAND_TYPES,
                name="demandreviewcommandtype",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=True,
        ),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("before_summary_json", sa.JSON(), nullable=True),
        sa.Column("after_summary_json", sa.JSON(), nullable=True),
        sa.Column("response_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["demand_list_reviews.tenant_id", "demand_list_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(command_type IS NULL AND idempotency_key IS NULL) OR "
            "(command_type IS NOT NULL AND idempotency_key IS NOT NULL "
            "AND request_hash IS NOT NULL)",
            name="ck_demand_review_event_command_receipt",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_demand_list_review_events_tenant_id",
        "demand_list_review_events",
        ["tenant_id"],
    )
    op.create_index(
        "uq_demand_review_event_command_key",
        "demand_list_review_events",
        ["tenant_id", "command_type", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_demand_review_events_tenant_review",
        "demand_list_review_events",
        ["tenant_id", "review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demand_review_events_tenant_review",
        table_name="demand_list_review_events",
    )
    op.drop_index(
        "uq_demand_review_event_command_key",
        table_name="demand_list_review_events",
    )
    op.drop_index(
        "ix_demand_list_review_events_tenant_id",
        table_name="demand_list_review_events",
    )
    op.drop_table("demand_list_review_events")

    op.drop_index(
        "ix_demand_review_decisions_tenant_finding",
        table_name="demand_list_review_decisions",
    )
    op.drop_index(
        "ix_demand_review_decisions_tenant_review",
        table_name="demand_list_review_decisions",
    )
    op.drop_index(
        "ix_demand_list_review_decisions_tenant_id",
        table_name="demand_list_review_decisions",
    )
    op.drop_table("demand_list_review_decisions")

    op.drop_index(
        "ix_demand_review_findings_tenant_review",
        table_name="demand_list_review_findings",
    )
    op.drop_index(
        "uq_demand_review_finding_effect",
        table_name="demand_list_review_findings",
    )
    op.drop_index(
        "ix_demand_list_review_findings_tenant_id",
        table_name="demand_list_review_findings",
    )
    op.drop_table("demand_list_review_findings")

    op.drop_index(
        "ix_demand_list_reviews_tenant_source",
        table_name="demand_list_reviews",
    )
    op.drop_index(
        "ix_demand_list_reviews_tenant_status",
        table_name="demand_list_reviews",
    )
    op.drop_index(
        "ix_demand_list_reviews_tenant_id",
        table_name="demand_list_reviews",
    )
    op.drop_table("demand_list_reviews")

    op.drop_index(
        "uq_demand_list_items_tenant_id_id",
        table_name="demand_list_items",
    )
    op.drop_index(
        "uq_demand_lists_tenant_id_id",
        table_name="demand_lists",
    )
