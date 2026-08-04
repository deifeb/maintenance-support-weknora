from decimal import Decimal

from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryPolicy,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository
from sqlalchemy.dialects import postgresql, sqlite


def seed_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    warehouse_id: int | None = None,
    spare_part_id: int | None = None,
    location_id: int | None = None,
    lot_id: int | None = None,
    on_hand: str = "8",
    reserved: str = "0",
    damaged: str = "0",
    quarantined: str = "0",
    in_transit: str = "0",
    with_serial: bool = False,
) -> tuple[InventoryBalance, SerializedItem | None]:
    if warehouse_id is None:
        warehouse = Warehouse(tenant_id=tenant_id, code=f"WH-{suffix}", name=f"Warehouse {suffix}")
        session.add(warehouse)
        session.flush()
        warehouse_id = warehouse.id
    if spare_part_id is None:
        part = SparePart(tenant_id=tenant_id, code=f"SP-{suffix}", name=f"Spare {suffix}")
        session.add(part)
        session.flush()
        spare_part_id = part.id
    if location_id is None:
        location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=f"LOC-{suffix}",
            name=f"Location {suffix}",
            location_type="SHELF",
        )
        session.add(location)
        session.flush()
        location_id = location.id
    if lot_id is None and with_serial:
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare_part_id,
            lot_code=f"LOT-{suffix}",
        )
        session.add(lot)
        session.flush()
        lot_id = lot.id
    policy = InventoryPolicy(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        spare_part_id=spare_part_id,
        safety_stock=Decimal("2"),
        reorder_point=Decimal("4"),
        maximum_stock=Decimal("12"),
    )
    session.add(policy)
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        spare_part_id=spare_part_id,
        lot_id=lot_id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        damaged_quantity=Decimal(damaged),
        quarantined_quantity=Decimal(quarantined),
        in_transit_quantity=Decimal(in_transit),
    )
    session.add(balance)
    session.flush()
    serial = None
    if with_serial:
        serial = SerializedItem(
            tenant_id=tenant_id,
            spare_part_id=spare_part_id,
            serial_number=f"SER-{suffix}",
            lot_id=lot_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            status="IN_STOCK",
        )
        session.add(serial)
        session.flush()
    return balance, serial


def test_list_balances_scopes_tenant_and_all_identity_filters(session) -> None:
    repository = InventoryLedgerRepository()
    balance_a, serial_a = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="A",
        with_serial=True,
    )
    balance_b, _ = seed_balance(
        session,
        tenant_id="tenant-b",
        suffix="B",
        with_serial=True,
    )

    rows, total = repository.list_balances(
        session,
        "tenant-a",
        warehouse_id=balance_a.warehouse_id,
        spare_part_id=balance_a.spare_part_id,
        location_id=balance_a.location_id,
        lot_id=balance_a.lot_id,
        serial_item_id=serial_a.id,
    )

    assert total == 1
    assert [row.id for row in rows] == [balance_a.id]
    assert balance_b.id not in [row.id for row in rows]


def test_lock_balances_sorts_ids_and_compiles_postgresql_lock(session) -> None:
    repository = InventoryLedgerRepository()
    first, _ = seed_balance(session, tenant_id="tenant-a", suffix="ONE")
    second, _ = seed_balance(session, tenant_id="tenant-a", suffix="TWO")

    locked = repository.lock_balances(session, "tenant-a", [second.id, first.id, second.id])
    statement = repository.lock_balances_statement("tenant-a", [second.id, first.id])
    sqlite_sql = str(statement.compile(dialect=sqlite.dialect()))
    postgres_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert [balance.id for balance in locked] == sorted([first.id, second.id])
    assert "ORDER BY inventory_balances.id" in sqlite_sql
    assert "FOR UPDATE" in postgres_sql


def test_repository_queries_do_not_commit(session) -> None:
    balance, _ = seed_balance(session, tenant_id="tenant-a", suffix="ROLLBACK")

    InventoryLedgerRepository().get_balance(session, "tenant-a", balance.id)
    assert session.in_transaction()
    session.rollback()

    assert InventoryLedgerRepository().get_balance(session, "tenant-a", balance.id) is None
