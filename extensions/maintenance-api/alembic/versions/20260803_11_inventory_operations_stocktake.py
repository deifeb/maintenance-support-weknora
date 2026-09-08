"""add inventory operations and stocktake persistence

Revision ID: 20260803_11
Revises: 20260803_10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic.util.exc import CommandError

revision: str = "20260803_11"
down_revision: str | None = "20260803_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPERATION_TABLES = (
    "inventory_reservation_lines",
    "inventory_reservations",
    "inventory_transfer_lines",
    "inventory_transfers",
    "stocktake_lines",
    "stocktakes",
)


def upgrade() -> None:
    op.create_table(
        "inventory_reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("owner_type", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "allow_partial",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'PARTIALLY_ISSUED', 'FULFILLED', "
            "'RELEASED', 'CANCELLED', 'EXPIRED')",
            name="ck_inventory_reservation_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_reservation_tenant_id",
        ),
    )
    op.create_index(
        "ix_inventory_reservations_tenant_id",
        "inventory_reservations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inventory_reservations_tenant_status_expires",
        "inventory_reservations",
        ["tenant_id", "status", "expires_at"],
    )

    op.create_table(
        "inventory_reservation_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("balance_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("serial_item_id", sa.Integer(), nullable=True),
        sa.Column("requested_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "issued_quantity",
            sa.Numeric(18, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "released_quantity",
            sa.Numeric(18, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("expected_balance_version", sa.Integer(), nullable=False),
        sa.Column("fefo_rank", sa.Integer(), nullable=False),
        sa.Column("fefo_override_reason", sa.String(length=500), nullable=True),
        sa.Column("recommended_selection_json", sa.JSON(), nullable=True),
        sa.Column("actual_selection_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "requested_quantity >= 0",
            name="ck_inventory_reservation_line_requested_nonnegative",
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_inventory_reservation_line_reserved_nonnegative",
        ),
        sa.CheckConstraint(
            "issued_quantity >= 0",
            name="ck_inventory_reservation_line_issued_nonnegative",
        ),
        sa.CheckConstraint(
            "released_quantity >= 0",
            name="ck_inventory_reservation_line_released_nonnegative",
        ),
        sa.CheckConstraint(
            "ROUND(issued_quantity + released_quantity, 4) <= "
            "ROUND(reserved_quantity, 4)",
            name="ck_inventory_reservation_line_lifecycle",
        ),
        sa.CheckConstraint(
            "serial_item_id IS NULL OR ("
            "requested_quantity IN (0, 1) AND "
            "reserved_quantity IN (0, 1) AND "
            "issued_quantity IN (0, 1) AND "
            "released_quantity IN (0, 1))",
            name="ck_inventory_reservation_line_serial_quantities",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["inventory_reservations.tenant_id", "inventory_reservations.id"],
            name="fk_inventory_reservation_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["spare_part_id"],
            ["spare_parts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["balance_id"],
            ["inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["inventory_lots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["serial_item_id"],
            ["serialized_items.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_reservation_lines_tenant_id",
        "inventory_reservation_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inventory_reservation_lines_tenant_reservation",
        "inventory_reservation_lines",
        ["tenant_id", "reservation_id"],
    )
    op.create_index(
        "ix_inventory_reservation_lines_tenant_balance",
        "inventory_reservation_lines",
        ["tenant_id", "balance_id"],
    )

    op.create_table(
        "inventory_transfers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("source_location_id", sa.Integer(), nullable=False),
        sa.Column("target_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("target_location_id", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'DISPATCHED', 'PARTIALLY_RECEIVED', "
            "'COMPLETED', 'CANCELLED')",
            name="ck_inventory_transfer_status",
        ),
        sa.CheckConstraint(
            "source_location_id <> target_location_id",
            name="ck_inventory_transfer_distinct_locations",
        ),
        sa.ForeignKeyConstraint(
            ["source_warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_location_id"],
            ["warehouse_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_location_id"],
            ["warehouse_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_transfer_tenant_id",
        ),
    )
    op.create_index(
        "ix_inventory_transfers_tenant_id",
        "inventory_transfers",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inventory_transfers_tenant_status",
        "inventory_transfers",
        ["tenant_id", "status"],
    )

    op.create_table(
        "inventory_transfer_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("source_balance_id", sa.Integer(), nullable=False),
        sa.Column("target_balance_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("serial_item_id", sa.Integer(), nullable=True),
        sa.Column("requested_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "dispatched_quantity",
            sa.Numeric(18, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "received_quantity",
            sa.Numeric(18, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("expected_source_version", sa.Integer(), nullable=False),
        sa.Column("expected_target_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "requested_quantity >= 0",
            name="ck_inventory_transfer_line_requested_nonnegative",
        ),
        sa.CheckConstraint(
            "dispatched_quantity >= 0",
            name="ck_inventory_transfer_line_dispatched_nonnegative",
        ),
        sa.CheckConstraint(
            "received_quantity >= 0",
            name="ck_inventory_transfer_line_received_nonnegative",
        ),
        sa.CheckConstraint(
            "dispatched_quantity <= requested_quantity",
            name="ck_inventory_transfer_line_dispatch_lifecycle",
        ),
        sa.CheckConstraint(
            "received_quantity <= dispatched_quantity",
            name="ck_inventory_transfer_line_receive_lifecycle",
        ),
        sa.CheckConstraint(
            "serial_item_id IS NULL OR ("
            "requested_quantity IN (0, 1) AND "
            "dispatched_quantity IN (0, 1) AND "
            "received_quantity IN (0, 1))",
            name="ck_inventory_transfer_line_serial_quantities",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["inventory_transfers.tenant_id", "inventory_transfers.id"],
            name="fk_inventory_transfer_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["spare_part_id"],
            ["spare_parts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_balance_id"],
            ["inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_balance_id"],
            ["inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["inventory_lots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["serial_item_id"],
            ["serialized_items.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_transfer_lines_tenant_id",
        "inventory_transfer_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inventory_transfer_lines_tenant_transfer",
        "inventory_transfer_lines",
        ["tenant_id", "transfer_id"],
    )
    op.create_index(
        "ix_inventory_transfer_lines_source_balance",
        "inventory_transfer_lines",
        ["source_balance_id"],
    )
    op.create_index(
        "ix_inventory_transfer_lines_target_balance",
        "inventory_transfer_lines",
        ["target_balance_id"],
    )

    op.create_table(
        "stocktakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'COUNTING', 'REVIEWING', 'CONFIRMED', "
            "'CONFLICTED', 'CANCELLED')",
            name="ck_inventory_stocktake_status",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["warehouse_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_stocktake_tenant_id",
        ),
    )
    op.create_index(
        "ix_stocktakes_tenant_id",
        "stocktakes",
        ["tenant_id"],
    )
    op.create_index(
        "ix_stocktakes_tenant_status",
        "stocktakes",
        ["tenant_id", "status"],
    )

    op.create_table(
        "stocktake_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("stocktake_id", sa.Integer(), nullable=False),
        sa.Column("balance_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("serial_item_id", sa.Integer(), nullable=True),
        sa.Column("system_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("variance_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("snapshot_balance_version", sa.Integer(), nullable=False),
        sa.Column("confirmed_transaction_id", sa.Integer(), nullable=True),
        sa.Column(
            "resolution",
            sa.String(length=24),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("conflict_details_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "system_quantity >= 0",
            name="ck_inventory_stocktake_line_system_nonnegative",
        ),
        sa.CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name="ck_inventory_stocktake_line_counted_nonnegative",
        ),
        sa.CheckConstraint(
            "resolution IN ('PENDING', 'ADJUSTED', 'CONFLICTED', "
            "'RECOUNT_REQUIRED', 'BASELINE_ACCEPTED')",
            name="ck_inventory_stocktake_line_resolution",
        ),
        sa.CheckConstraint(
            "(counted_quantity IS NULL AND variance_quantity IS NULL) OR "
            "(counted_quantity IS NOT NULL AND "
            "ROUND(variance_quantity, 4) = "
            "ROUND(counted_quantity - system_quantity, 4))",
            name="ck_inventory_stocktake_line_variance",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "stocktake_id"],
            ["stocktakes.tenant_id", "stocktakes.id"],
            name="fk_inventory_stocktake_line_tenant_parent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["balance_id"],
            ["inventory_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["spare_part_id"],
            ["spare_parts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["inventory_lots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["serial_item_id"],
            ["serialized_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_transaction_id"],
            ["inventory_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stocktake_lines_tenant_id",
        "stocktake_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_stocktake_lines_tenant_stocktake",
        "stocktake_lines",
        ["tenant_id", "stocktake_id"],
    )
    op.create_index(
        "ix_stocktake_lines_balance",
        "stocktake_lines",
        ["balance_id"],
    )


def _assert_no_inventory_operation_data() -> None:
    bind = op.get_bind()
    for table_name in _OPERATION_TABLES:
        count = bind.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
        if int(count or 0) > 0:
            raise CommandError(
                "cannot downgrade inventory operations while 05-4B business data exists"
            )


def downgrade() -> None:
    _assert_no_inventory_operation_data()

    op.drop_index("ix_stocktake_lines_balance", table_name="stocktake_lines")
    op.drop_index(
        "ix_stocktake_lines_tenant_stocktake",
        table_name="stocktake_lines",
    )
    op.drop_index("ix_stocktake_lines_tenant_id", table_name="stocktake_lines")
    op.drop_table("stocktake_lines")

    op.drop_index("ix_stocktakes_tenant_status", table_name="stocktakes")
    op.drop_index("ix_stocktakes_tenant_id", table_name="stocktakes")
    op.drop_table("stocktakes")

    op.drop_index(
        "ix_inventory_transfer_lines_target_balance",
        table_name="inventory_transfer_lines",
    )
    op.drop_index(
        "ix_inventory_transfer_lines_source_balance",
        table_name="inventory_transfer_lines",
    )
    op.drop_index(
        "ix_inventory_transfer_lines_tenant_transfer",
        table_name="inventory_transfer_lines",
    )
    op.drop_index(
        "ix_inventory_transfer_lines_tenant_id",
        table_name="inventory_transfer_lines",
    )
    op.drop_table("inventory_transfer_lines")

    op.drop_index(
        "ix_inventory_transfers_tenant_status",
        table_name="inventory_transfers",
    )
    op.drop_index(
        "ix_inventory_transfers_tenant_id",
        table_name="inventory_transfers",
    )
    op.drop_table("inventory_transfers")

    op.drop_index(
        "ix_inventory_reservation_lines_tenant_balance",
        table_name="inventory_reservation_lines",
    )
    op.drop_index(
        "ix_inventory_reservation_lines_tenant_reservation",
        table_name="inventory_reservation_lines",
    )
    op.drop_index(
        "ix_inventory_reservation_lines_tenant_id",
        table_name="inventory_reservation_lines",
    )
    op.drop_table("inventory_reservation_lines")

    op.drop_index(
        "ix_inventory_reservations_tenant_status_expires",
        table_name="inventory_reservations",
    )
    op.drop_index(
        "ix_inventory_reservations_tenant_id",
        table_name="inventory_reservations",
    )
    op.drop_table("inventory_reservations")
