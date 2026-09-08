# Add report version lineage and provenance
# Revision ID: 20260830_16
# Revises: 20260827_15

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_16"
down_revision: str | None = "20260827_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT_INDEX = "ix_ai_report_versions_parent_version_id"
PARENT_FK = "fk_ai_report_versions_parent_version"
GENERATION_MODE_CHECK = "ck_ai_report_version_generation_mode"

_REQUIRED_COLUMNS = {
    "parent_version_id",
    "source_snapshot_json",
    "input_digest",
    "generation_mode",
    "generated_at",
}
_CHECK_SQL = (
    "generation_mode IS NULL OR "
    "generation_mode IN ('LLM', 'RULE_FALLBACK')"
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _generation_mode_checks(
    inspector: sa.Inspector,
) -> list[dict[str, object]]:
    return [
        constraint
        for constraint in inspector.get_check_constraints(
            "ai_report_versions"
        )
        if (
            constraint.get("name") == GENERATION_MODE_CHECK
            or "generation_mode"
            in str(constraint.get("sqltext") or "")
        )
    ]


def _parent_foreign_keys(
    inspector: sa.Inspector,
) -> list[dict[str, object]]:
    return [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(
            "ai_report_versions"
        )
        if (
            foreign_key.get("constrained_columns")
            == ["parent_version_id"]
            and foreign_key.get("referred_table")
            == "ai_report_versions"
            and foreign_key.get("referred_columns") == ["id"]
        )
    ]


def _require_parent_schema(inspector: sa.Inspector) -> None:
    foreign_keys = _parent_foreign_keys(inspector)
    if len(foreign_keys) != 1:
        raise RuntimeError(
            "ai_report_versions parent self-FK must exist exactly once"
        )

    options = foreign_keys[0].get("options") or {}
    ondelete = str(options.get("ondelete") or "").upper()
    if ondelete != "RESTRICT":
        raise RuntimeError(
            "ai_report_versions parent self-FK must use ON DELETE RESTRICT"
        )

    indexes = [
        index
        for index in inspector.get_indexes("ai_report_versions")
        if index.get("name") == PARENT_INDEX
    ]
    if len(indexes) != 1:
        raise RuntimeError(
            "ai_report_versions parent index must exist exactly once"
        )

    index = indexes[0]
    if index.get("column_names") != ["parent_version_id"]:
        raise RuntimeError(
            "ai_report_versions parent index must cover only "
            "parent_version_id"
        )
    if bool(index.get("unique")):
        raise RuntimeError(
            "ai_report_versions parent index must be non-unique"
        )


def _pre_upgrade_state() -> Literal[
    "MIGRATION_CREATES_SCHEMA",
    "HISTORICAL_METADATA_SCHEMA",
]:
    inspector = _inspector()
    column_names = {
        column["name"]
        for column in inspector.get_columns("ai_report_versions")
    }
    present = _REQUIRED_COLUMNS & column_names

    if present and present != _REQUIRED_COLUMNS:
        raise RuntimeError(
            "partial report-version lineage schema detected; "
            "refusing automatic repair"
        )

    if _generation_mode_checks(inspector):
        raise RuntimeError(
            "generation-mode CHECK already exists before 20260830_16; "
            "revision ownership is ambiguous"
        )

    if not present:
        return "MIGRATION_CREATES_SCHEMA"

    _require_parent_schema(inspector)
    return "HISTORICAL_METADATA_SCHEMA"


def _migration_owns_lineage_schema() -> bool:
    inspector = _inspector()
    column_names = {
        column["name"]
        for column in inspector.get_columns("ai_report_versions")
    }
    if not _REQUIRED_COLUMNS <= column_names:
        raise RuntimeError(
            "report-version lineage schema is incomplete during downgrade"
        )

    checks = _generation_mode_checks(inspector)
    if len(checks) != 1:
        raise RuntimeError(
            "20260830_16 generation-mode CHECK must exist exactly once"
        )

    _require_parent_schema(inspector)
    foreign_key = _parent_foreign_keys(inspector)[0]
    return foreign_key.get("name") == PARENT_FK


def upgrade() -> None:
    state = _pre_upgrade_state()

    if state == "MIGRATION_CREATES_SCHEMA":
        with op.batch_alter_table("ai_report_versions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "parent_version_id",
                    sa.Integer(),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "source_snapshot_json",
                    sa.JSON(),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "input_digest",
                    sa.String(length=64),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "generation_mode",
                    sa.String(length=24),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "generated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                )
            )
            batch_op.create_foreign_key(
                PARENT_FK,
                "ai_report_versions",
                ["parent_version_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_check_constraint(
                GENERATION_MODE_CHECK,
                _CHECK_SQL,
            )

        op.create_index(
            PARENT_INDEX,
            "ai_report_versions",
            ["parent_version_id"],
            unique=False,
        )
        return

    with op.batch_alter_table("ai_report_versions") as batch_op:
        batch_op.create_check_constraint(
            GENERATION_MODE_CHECK,
            _CHECK_SQL,
        )


def downgrade() -> None:
    migration_owns_schema = _migration_owns_lineage_schema()

    if not migration_owns_schema:
        with op.batch_alter_table("ai_report_versions") as batch_op:
            batch_op.drop_constraint(
                GENERATION_MODE_CHECK,
                type_="check",
            )
        return

    op.drop_index(PARENT_INDEX, table_name="ai_report_versions")
    with op.batch_alter_table("ai_report_versions") as batch_op:
        batch_op.drop_constraint(GENERATION_MODE_CHECK, type_="check")
        batch_op.drop_constraint(PARENT_FK, type_="foreignkey")
        batch_op.drop_column("generated_at")
        batch_op.drop_column("generation_mode")
        batch_op.drop_column("input_digest")
        batch_op.drop_column("source_snapshot_json")
        batch_op.drop_column("parent_version_id")
