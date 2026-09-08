# Add strict allocation rule publish receipt
# Revision ID: 20260827_15
# Revises: 20260825_14

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_15"
down_revision: str | None = "20260825_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLISH_RECEIPT_INDEX = (
    "uq_allocation_rule_versions_tenant_publish_idempotency"
)


def upgrade() -> None:
    # PLAN05_4D_TASK6_GREEN_A: nullable fields preserve historical rows.
    with op.batch_alter_table("allocation_rule_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "publish_idempotency_key",
                sa.String(length=128),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "publish_request_hash",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "publish_response_snapshot_json",
                sa.JSON(),
                nullable=True,
            )
        )

    op.create_index(
        PUBLISH_RECEIPT_INDEX,
        "allocation_rule_versions",
        ["tenant_id", "publish_idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        PUBLISH_RECEIPT_INDEX,
        table_name="allocation_rule_versions",
    )

    with op.batch_alter_table("allocation_rule_versions") as batch_op:
        batch_op.drop_column("publish_response_snapshot_json")
        batch_op.drop_column("publish_request_hash")
        batch_op.drop_column("publish_idempotency_key")
