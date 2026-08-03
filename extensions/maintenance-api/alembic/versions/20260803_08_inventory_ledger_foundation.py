"""add inventory ledger foundation

Revision ID: 20260803_08
Revises: 20260731_07
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from alembic.util.exc import CommandError


revision: str = "20260803_08"
down_revision: str | None = "20260731_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRANSACTION_STATUSES = (
    "PREVIEWED",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "EXPIRED",
    "REVERSED",
)
LOT_QUALITY_STATUSES = ("AVAILABLE", "QUARANTINED", "DAMAGED", "REJECTED")
EXPIRY_RULE_SCOPE_TYPES = ("TENANT", "CATEGORY", "SPARE_PART")
SERIAL_ITEM_STATUSES = (
    "IN_STOCK",
    "RESERVED",
    "ISSUED",
    "INSTALLED",
    "AWAITING_REPAIR",
    "IN_REPAIR",
    "REPAIRED",
    "SCRAPPED",
    "FROZEN",
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _quantity_state(row: sa.RowMapping) -> dict[str, str]:
    return {
        key: format(Decimal(str(row[key])).quantize(Decimal("0.0001")), ".4f")
        for key in (
            "on_hand_quantity",
            "reserved_quantity",
            "damaged_quantity",
            "quarantined_quantity",
            "in_transit_quantity",
        )
    }


def _create_ledger_tables() -> None:
    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location_type", sa.String(32), nullable=False),
        sa.Column("is_pickable", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_warehouse_location_code"),
    )
    op.create_index("ix_warehouse_locations_tenant_id", "warehouse_locations", ["tenant_id"])
    op.create_index("ix_warehouse_locations_warehouse_id", "warehouse_locations", ["warehouse_id"])

    op.create_table(
        "inventory_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=False),
        sa.Column("reorder_point", sa.Numeric(18, 4), nullable=False),
        sa.Column("maximum_stock", sa.Numeric(18, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("safety_stock >= 0", name="ck_inventory_policy_safety_nonnegative"),
        sa.CheckConstraint("reorder_point >= 0", name="ck_inventory_policy_reorder_nonnegative"),
        sa.CheckConstraint("maximum_stock IS NULL OR maximum_stock >= 0", name="ck_inventory_policy_max_nonnegative"),
        sa.CheckConstraint("reorder_point >= safety_stock", name="ck_inventory_policy_reorder_ge_safety"),
        sa.CheckConstraint("maximum_stock IS NULL OR maximum_stock >= reorder_point", name="ck_inventory_policy_max_ge_reorder"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "spare_part_id", name="uq_inventory_policy_warehouse_spare"),
    )
    op.create_index("ix_inventory_policies_tenant_id", "inventory_policies", ["tenant_id"])

    op.create_table(
        "inventory_expiry_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.Enum(*EXPIRY_RULE_SCOPE_TYPES, name="inventoryexpiryrulescopetype", native_enum=False, length=16), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("spare_part_id", sa.Integer(), nullable=True),
        sa.Column("warning_days_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "scope_type", "category", "spare_part_id", name="uq_inventory_expiry_rule_scope"),
    )
    op.create_index("ix_inventory_expiry_rules_tenant_id", "inventory_expiry_rules", ["tenant_id"])

    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("lot_code", sa.String(128), nullable=False),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("quality_status", sa.Enum(*LOT_QUALITY_STATUSES, name="inventorylotqualitystatus", native_enum=False, length=16), nullable=False),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("freeze_reason", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "spare_part_id", "lot_code", name="uq_inventory_lot_code"),
    )
    op.create_index("ix_inventory_lots_tenant_id", "inventory_lots", ["tenant_id"])

    op.create_table(
        "serialized_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum(*SERIAL_ITEM_STATUSES, name="serializeditemstatus", native_enum=False, length=24), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("installation_position", sa.String(128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["lot_id"], ["inventory_lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["warehouse_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "serial_number", name="uq_serialized_item_number"),
    )
    op.create_index("ix_serialized_items_tenant_id", "serialized_items", ["tenant_id"])

    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("on_hand_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("quarantined_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("on_hand_quantity >= 0", name="ck_inventory_balance_on_hand_nonnegative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventory_balance_reserved_nonnegative"),
        sa.CheckConstraint("damaged_quantity >= 0", name="ck_inventory_balance_damaged_nonnegative"),
        sa.CheckConstraint("quarantined_quantity >= 0", name="ck_inventory_balance_quarantined_nonnegative"),
        sa.CheckConstraint("in_transit_quantity >= 0", name="ck_inventory_balance_in_transit_nonnegative"),
        sa.CheckConstraint("reserved_quantity + damaged_quantity + quarantined_quantity <= on_hand_quantity", name="ck_inventory_balance_allocated_not_exceed_on_hand"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["warehouse_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["inventory_lots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "warehouse_id", "location_id", "spare_part_id", "lot_id", name="uq_inventory_balance_identity"),
    )
    op.create_index("ix_inventory_balances_tenant_id", "inventory_balances", ["tenant_id"])
    op.create_index(
        "uq_inventory_balance_default_identity",
        "inventory_balances",
        ["tenant_id", "warehouse_id", "location_id", "spare_part_id"],
        unique=True,
        sqlite_where=sa.text("lot_id IS NULL"),
        postgresql_where=sa.text("lot_id IS NULL"),
    )

    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("status", sa.Enum(*TRANSACTION_STATUSES, name="inventorytransactionstatus", native_enum=False, length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=True),
        sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("actor_roles_json", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("reversed_transaction_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reversed_transaction_id"], ["inventory_transactions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "operation_type", "idempotency_key", name="uq_inventory_tx_tenant_operation_idempotency"),
    )
    op.create_index("ix_inventory_transactions_tenant_id", "inventory_transactions", ["tenant_id"])

    op.create_table(
        "inventory_ledger_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("balance_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("serial_item_id", sa.Integer(), nullable=True),
        sa.Column("on_hand_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("reserved_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("damaged_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("quarantined_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("in_transit_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("state_before_json", sa.JSON(), nullable=False),
        sa.Column("state_after_json", sa.JSON(), nullable=False),
        sa.Column("before_balance_version", sa.Integer(), nullable=False),
        sa.Column("resulting_balance_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["inventory_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["balance_id"], ["inventory_balances.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_ledger_entries_tenant_id", "inventory_ledger_entries", ["tenant_id"])


def _backfill_legacy_inventory() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT * FROM warehouse_inventories ORDER BY id")).mappings().all()
    locations: dict[tuple[str, int], int] = {}
    warehouses = bind.execute(
        sa.text("SELECT id, tenant_id, created_at, updated_at FROM warehouses ORDER BY id")
    ).mappings()
    for warehouse in warehouses:
        key = (warehouse["tenant_id"], warehouse["id"])
        bind.execute(
            sa.text(
                "INSERT INTO warehouse_locations "
                "(tenant_id, warehouse_id, code, name, location_type, is_pickable, is_active, version, created_at, updated_at) "
                "VALUES (:tenant_id, :warehouse_id, 'DEFAULT', 'Default location', 'DEFAULT', :is_pickable, :is_active, 1, :created_at, :updated_at)"
            ),
            {
                "tenant_id": warehouse["tenant_id"],
                "warehouse_id": warehouse["id"],
                "is_pickable": True,
                "is_active": True,
                "created_at": warehouse["created_at"],
                "updated_at": warehouse["updated_at"],
            },
        )
        location_id = bind.execute(
            sa.text(
                "SELECT id FROM warehouse_locations "
                "WHERE tenant_id = :tenant_id AND warehouse_id = :warehouse_id AND code = 'DEFAULT'"
            ),
            {"tenant_id": warehouse["tenant_id"], "warehouse_id": warehouse["id"]},
        ).scalar_one()
        locations[key] = location_id
    for row in rows:
        key = (row["tenant_id"], row["warehouse_id"])
        location_id = locations[key]
        bind.execute(
            sa.text(
                "INSERT INTO inventory_policies "
                "(tenant_id, warehouse_id, spare_part_id, safety_stock, reorder_point, maximum_stock, notes, version, created_at, updated_at) "
                "VALUES (:tenant_id, :warehouse_id, :spare_part_id, :safety_stock, :reorder_point, :maximum_stock, :notes, :version, :created_at, :updated_at)"
            ),
            dict(row),
        )
        bind.execute(
            sa.text(
                "INSERT INTO inventory_balances "
                "(tenant_id, warehouse_id, location_id, spare_part_id, lot_id, on_hand_quantity, reserved_quantity, damaged_quantity, quarantined_quantity, in_transit_quantity, version, created_at, updated_at) "
                "VALUES (:tenant_id, :warehouse_id, :location_id, :spare_part_id, NULL, :on_hand_quantity, :reserved_quantity, :damaged_quantity, :quarantined_quantity, :in_transit_quantity, :version, :created_at, :updated_at)"
            ),
            {**dict(row), "location_id": location_id},
        )
        balance_id = bind.execute(
            sa.text(
                "SELECT id FROM inventory_balances WHERE tenant_id = :tenant_id "
                "AND warehouse_id = :warehouse_id AND location_id = :location_id "
                "AND spare_part_id = :spare_part_id AND lot_id IS NULL"
            ),
            {**dict(row), "location_id": location_id},
        ).scalar_one()
        state_after = _quantity_state(row)
        state_before = {key: "0.0000" for key in state_after}
        idempotency_key = f"migration-opening-{row['id']}"
        bind.execute(
            sa.text(
                "INSERT INTO inventory_transactions "
                "(tenant_id, operation_type, status, idempotency_key, request_hash, response_snapshot_json, reference_type, reference_id, reason, confirmation_token_hash, confirmation_expires_at, actor_user_id, actor_roles_json, request_id, reversed_transaction_id, version, created_at, updated_at, completed_at, failed_at) "
                "VALUES (:tenant_id, 'MIGRATION_OPENING', 'COMPLETED', :idempotency_key, :request_hash, NULL, 'warehouse_inventories', :reference_id, 'legacy inventory migration opening balance', NULL, NULL, 'system-migration', :actor_roles_json, :request_id, NULL, 1, :created_at, :updated_at, :completed_at, NULL)"
            ),
            {
                "tenant_id": row["tenant_id"],
                "idempotency_key": idempotency_key,
                "request_hash": "0" * 64,
                "reference_id": str(row["id"]),
                "actor_roles_json": json.dumps(["SYSTEM"]),
                "request_id": f"migration-20260803-08-{row['id']}",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row["updated_at"],
            },
        )
        transaction_id = bind.execute(
            sa.text(
                "SELECT id FROM inventory_transactions WHERE tenant_id = :tenant_id "
                "AND operation_type = 'MIGRATION_OPENING' AND idempotency_key = :idempotency_key"
            ),
            {"tenant_id": row["tenant_id"], "idempotency_key": idempotency_key},
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO inventory_ledger_entries "
                "(tenant_id, transaction_id, balance_id, spare_part_id, warehouse_id, location_id, lot_id, serial_item_id, on_hand_delta, reserved_delta, damaged_delta, quarantined_delta, in_transit_delta, state_before_json, state_after_json, before_balance_version, resulting_balance_version, created_at, updated_at) "
                "VALUES (:tenant_id, :transaction_id, :balance_id, :spare_part_id, :warehouse_id, :location_id, NULL, NULL, :on_hand_quantity, :reserved_quantity, :damaged_quantity, :quarantined_quantity, :in_transit_quantity, :state_before_json, :state_after_json, 0, :resulting_balance_version, :created_at, :updated_at)"
            ),
            {
                **dict(row),
                "transaction_id": transaction_id,
                "balance_id": balance_id,
                "location_id": location_id,
                "state_before_json": json.dumps(state_before, sort_keys=True),
                "state_after_json": json.dumps(state_after, sort_keys=True),
                "resulting_balance_version": row["version"],
            },
        )


def upgrade() -> None:
    _create_ledger_tables()
    _backfill_legacy_inventory()
    op.drop_table("warehouse_inventories")


def _has_granular_facts() -> bool:
    bind = op.get_bind()
    queries = (
        "SELECT 1 FROM warehouse_locations WHERE code <> 'DEFAULT' LIMIT 1",
        "SELECT 1 FROM inventory_lots LIMIT 1",
        "SELECT 1 FROM serialized_items LIMIT 1",
        "SELECT 1 FROM inventory_balances WHERE lot_id IS NOT NULL LIMIT 1",
    )
    return any(bind.execute(sa.text(query)).first() is not None for query in queries)


def _create_legacy_inventory_table() -> None:
    op.create_table(
        "warehouse_inventories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("on_hand_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("reserved_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("damaged_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("quarantined_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("in_transit_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=False),
        sa.Column("reorder_point", sa.Numeric(18, 4), nullable=False),
        sa.Column("maximum_stock", sa.Numeric(18, 4), nullable=True),
        sa.Column("last_counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("on_hand_quantity >= 0", name="ck_inventory_on_hand_nonnegative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved_nonnegative"),
        sa.CheckConstraint("damaged_quantity >= 0", name="ck_inventory_damaged_nonnegative"),
        sa.CheckConstraint("quarantined_quantity >= 0", name="ck_inventory_quarantined_nonnegative"),
        sa.CheckConstraint("in_transit_quantity >= 0", name="ck_inventory_in_transit_nonnegative"),
        sa.CheckConstraint("safety_stock >= 0", name="ck_inventory_safety_nonnegative"),
        sa.CheckConstraint("reorder_point >= 0", name="ck_inventory_reorder_nonnegative"),
        sa.CheckConstraint("maximum_stock IS NULL OR maximum_stock >= 0", name="ck_inventory_max_nonnegative"),
        sa.CheckConstraint("reserved_quantity + damaged_quantity + quarantined_quantity <= on_hand_quantity", name="ck_inventory_allocated_not_exceed_on_hand"),
        sa.CheckConstraint("reorder_point >= safety_stock", name="ck_inventory_reorder_ge_safety"),
        sa.CheckConstraint("maximum_stock IS NULL OR maximum_stock >= reorder_point", name="ck_inventory_max_ge_reorder"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", "spare_part_id", name="uq_inventory_warehouse_spare"),
    )
    op.create_index("ix_warehouse_inventories_warehouse_id", "warehouse_inventories", ["warehouse_id"])
    op.create_index("ix_warehouse_inventories_spare_part_id", "warehouse_inventories", ["spare_part_id"])
    op.create_index("ix_warehouse_inventories_tenant_id", "warehouse_inventories", ["tenant_id"])


def _backfill_legacy_from_balances() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT b.tenant_id, b.warehouse_id, b.spare_part_id, "
            "SUM(b.on_hand_quantity) AS on_hand_quantity, "
            "SUM(b.reserved_quantity) AS reserved_quantity, "
            "SUM(b.damaged_quantity) AS damaged_quantity, "
            "SUM(b.quarantined_quantity) AS quarantined_quantity, "
            "SUM(b.in_transit_quantity) AS in_transit_quantity, "
            "MAX(b.version) AS version, MAX(b.created_at) AS created_at, MAX(b.updated_at) AS updated_at, "
            "MAX(p.safety_stock) AS safety_stock, MAX(p.reorder_point) AS reorder_point, "
            "MAX(p.maximum_stock) AS maximum_stock, MAX(p.notes) AS notes "
            "FROM inventory_balances b "
            "JOIN warehouse_locations l ON l.id = b.location_id "
            "LEFT JOIN inventory_policies p ON p.tenant_id = b.tenant_id "
            "AND p.warehouse_id = b.warehouse_id AND p.spare_part_id = b.spare_part_id "
            "WHERE l.code = 'DEFAULT' AND b.lot_id IS NULL "
            "GROUP BY b.tenant_id, b.warehouse_id, b.spare_part_id"
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO warehouse_inventories "
                "(warehouse_id, spare_part_id, on_hand_quantity, reserved_quantity, damaged_quantity, quarantined_quantity, in_transit_quantity, safety_stock, reorder_point, maximum_stock, last_counted_at, notes, tenant_id, version, created_at, updated_at) "
                "VALUES (:warehouse_id, :spare_part_id, :on_hand_quantity, :reserved_quantity, :damaged_quantity, :quarantined_quantity, :in_transit_quantity, :safety_stock, :reorder_point, :maximum_stock, NULL, :notes, :tenant_id, :version, :created_at, :updated_at)"
            ),
            dict(row),
        )


def downgrade() -> None:
    if _has_granular_facts():
        raise CommandError("inventory ledger contains granular facts")
    _create_legacy_inventory_table()
    _backfill_legacy_from_balances()
    op.drop_table("inventory_ledger_entries")
    op.drop_table("inventory_transactions")
    op.drop_table("inventory_balances")
    op.drop_table("serialized_items")
    op.drop_table("inventory_lots")
    op.drop_table("inventory_expiry_rules")
    op.drop_table("inventory_policies")
    op.drop_table("warehouse_locations")
