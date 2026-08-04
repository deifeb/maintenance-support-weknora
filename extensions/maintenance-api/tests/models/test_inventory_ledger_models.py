from decimal import Decimal

from app.db.base import Base
from app.models.inventory_ledger import (
    InventoryBalance,
    InventoryExpiryRule,
    InventoryLedgerEntry,
    InventoryTransaction,
    SerializedItem,
)
from sqlalchemy import CheckConstraint, UniqueConstraint


LEDGER_TABLES = {
    "warehouse_locations",
    "inventory_policies",
    "inventory_expiry_rules",
    "inventory_lots",
    "serialized_items",
    "inventory_balances",
    "inventory_transactions",
    "inventory_ledger_entries",
}


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_inventory_ledger_models_register_authoritative_tables_and_keys() -> None:
    assert LEDGER_TABLES <= set(Base.metadata.tables)
    assert ("tenant_id", "warehouse_id", "code") in _unique_column_sets(
        "warehouse_locations"
    )
    assert ("tenant_id", "warehouse_id", "spare_part_id") in _unique_column_sets(
        "inventory_policies"
    )
    assert ("tenant_id", "spare_part_id", "lot_code") in _unique_column_sets(
        "inventory_lots"
    )
    assert ("tenant_id", "serial_number") in _unique_column_sets("serialized_items")
    assert (
        "tenant_id",
        "operation_type",
        "idempotency_key",
    ) in _unique_column_sets("inventory_transactions")


def test_inventory_ledger_models_define_exact_quantities_and_transaction_links() -> None:
    balance = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=1,
        location_id=1,
        spare_part_id=1,
        lot_id=None,
        on_hand_quantity=Decimal("12.5000"),
        reserved_quantity=Decimal("2.0000"),
        damaged_quantity=Decimal("1.0000"),
        quarantined_quantity=Decimal("0.5000"),
        in_transit_quantity=Decimal("3.0000"),
    )
    assert balance.available_quantity == Decimal("9.0000")

    assert InventoryTransaction.__table__.c.status.type.enums == [
        "PREVIEWED",
        "COMPLETED",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "EXPIRED",
        "REVERSED",
    ]
    assert SerializedItem.__table__.c.status.type.enums == [
        "IN_STOCK",
        "RESERVED",
        "ISSUED",
        "INSTALLED",
        "AWAITING_REPAIR",
        "IN_REPAIR",
        "REPAIRED",
        "SCRAPPED",
        "FROZEN",
    ]
    assert InventoryExpiryRule.__table__.c.scope_type.type.enums == [
        "TENANT",
        "CATEGORY",
        "SPARE_PART",
    ]
    assert any(
        index.unique
        and tuple(index.columns.keys())
        == ("tenant_id", "warehouse_id", "location_id", "spare_part_id")
        and index.dialect_options["sqlite"].get("where") is not None
        for index in InventoryBalance.__table__.indexes
    )
    assert InventoryLedgerEntry.__table__.c.transaction_id.foreign_keys
    assert any(
        "reserved_quantity + damaged_quantity + quarantined_quantity <= on_hand_quantity"
        in str(constraint.sqltext)
        for constraint in InventoryBalance.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )
