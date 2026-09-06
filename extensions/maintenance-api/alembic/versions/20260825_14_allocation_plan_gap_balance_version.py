"""allow gap-only allocation plan lines

Revision ID: 20260825_14
Revises: 20260803_13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_14"
down_revision: str | None = "20260803_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAIR_CONSTRAINT = "ck_allocation_plan_line_balance_version_pair"


def upgrade() -> None:
    with op.batch_alter_table("allocation_plan_lines") as batch_op:
        batch_op.alter_column(
            "expected_balance_version",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_check_constraint(
            PAIR_CONSTRAINT,
            "("
            "recommended_balance_id IS NULL "
            "AND expected_balance_version IS NULL"
            ") OR ("
            "recommended_balance_id IS NOT NULL "
            "AND expected_balance_version IS NOT NULL"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("allocation_plan_lines") as batch_op:
        batch_op.drop_constraint(PAIR_CONSTRAINT, type_="check")
        batch_op.alter_column(
            "expected_balance_version",
            existing_type=sa.Integer(),
            nullable=False,
        )
