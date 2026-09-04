# Add AI report source references
# Revision ID: 20260904_17
# Revises: 20260830_16

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260904_17"
down_revision: str | None = "20260830_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_INDEX = "ix_ai_report_source_refs_tenant_id"
TENANT_SOURCE_INDEX = "ix_ai_report_source_refs_tenant_source"
VERSION_ORDINAL_INDEX = "ix_ai_report_source_refs_version_ordinal"


def upgrade() -> None:
    op.create_table(
        "ai_report_source_refs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("report_version_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column("source_lineage_id", sa.String(length=128), nullable=True),
        sa.Column("source_digest", sa.String(length=64), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_version_id"],
            ["ai_report_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_version_id",
            "source_type",
            "source_id",
            "source_version",
            name="uq_ai_report_source_ref_version_source",
        ),
    )
    op.create_index(TENANT_INDEX, "ai_report_source_refs", ["tenant_id"])
    op.create_index(
        TENANT_SOURCE_INDEX,
        "ai_report_source_refs",
        ["tenant_id", "source_type", "source_id"],
    )
    op.create_index(
        VERSION_ORDINAL_INDEX,
        "ai_report_source_refs",
        ["report_version_id", "ordinal"],
    )


def downgrade() -> None:
    op.drop_index(VERSION_ORDINAL_INDEX, table_name="ai_report_source_refs")
    op.drop_index(TENANT_SOURCE_INDEX, table_name="ai_report_source_refs")
    op.drop_index(TENANT_INDEX, table_name="ai_report_source_refs")
    op.drop_table("ai_report_source_refs")
