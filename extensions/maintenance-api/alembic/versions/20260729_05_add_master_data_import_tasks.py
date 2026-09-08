"""add master data import tasks

Revision ID: 20260729_05
Revises: 6c2dc8414b2f
Create Date: 2026-07-29 21:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_05"
down_revision: str | None = "6c2dc8414b2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = (
    "UPLOADED",
    "PREVIEWING",
    "PREVIEW_VALID",
    "PREVIEW_INVALID",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "EXPIRED",
)


def upgrade() -> None:
    op.create_table(
        "master_data_import_tasks",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_by_request_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "file_path",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "file_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "template_version",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                *_STATUS_VALUES,
                name="importtaskstatus",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "mapping_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "sheet_summary_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "preview_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "errors_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "warnings_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "error_workbook_path",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_master_data_import_tasks_expires_at",
        "master_data_import_tasks",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_master_data_import_tasks_tenant_user_status",
        "master_data_import_tasks",
        [
            "tenant_id",
            "created_by_user_id",
            "status",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_master_data_import_tasks_tenant_user_status",
        table_name="master_data_import_tasks",
    )
    op.drop_index(
        "ix_master_data_import_tasks_expires_at",
        table_name="master_data_import_tasks",
    )
    op.drop_table("master_data_import_tasks")
