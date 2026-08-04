"""persist import execution principal

Revision ID: 20260803_10
Revises: 20260803_09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_10"
down_revision: str | None = "20260803_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    sa.Column("execution_user_id", sa.String(length=64), nullable=True),
    sa.Column("execution_roles_json", sa.JSON(), nullable=True),
    sa.Column("execution_request_id", sa.String(length=128), nullable=True),
    sa.Column("execution_token_id", sa.String(length=128), nullable=True),
    sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column("master_data_import_tasks", column)


def downgrade() -> None:
    with op.batch_alter_table("master_data_import_tasks") as batch_op:
        for column in reversed(_COLUMNS):
            batch_op.drop_column(column.name)
