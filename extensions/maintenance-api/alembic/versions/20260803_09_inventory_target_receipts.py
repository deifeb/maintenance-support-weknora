"""add atomic inventory target receipts

Revision ID: 20260803_09
Revises: 20260803_08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_09"
down_revision: str | None = "20260803_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_target_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED')",
            name="ck_inventory_target_receipt_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND result_json IS NULL AND completed_at IS NULL) "
            "OR (status = 'COMPLETED' AND result_json IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_inventory_target_receipt_state",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_inventory_target_receipt_source_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_inventory_target_receipt_tenant_key",
        ),
    )
    op.create_index(
        "ix_inventory_target_receipts_tenant_id",
        "inventory_target_receipts",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_target_receipts_tenant_id",
        table_name="inventory_target_receipts",
    )
    op.drop_table("inventory_target_receipts")
