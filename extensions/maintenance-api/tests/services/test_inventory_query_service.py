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
from app.services.inventory_query_service import inventory_query_service
from sqlalchemy import select


def seed_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    warehouse: Warehouse | None = None,
    part: SparePart | None = None,
    on_hand: str = "8",
    reserved: str = "0",
    damaged: str = "0",
    quarantined: str = "0",
    in_transit: str = "0",
    with_serial: bool = False,
) -> tuple[InventoryBalance, SerializedItem | None]:
    warehouse = warehouse or Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    part = part or SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()
    lot = None
    if with_serial:
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=part.id,
            lot_code=f"LOT-{suffix}",
        )
        session.add(lot)
        session.flush()
    if session.scalar(
        select(InventoryPolicy.id).where(
            InventoryPolicy.tenant_id == tenant_id,
            InventoryPolicy.warehouse_id == warehouse.id,
            InventoryPolicy.spare_part_id == part.id,
        )
    ) is None:
        session.add(
            InventoryPolicy(
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                spare_part_id=part.id,
                safety_stock=Decimal("2"),
                reorder_point=Decimal("4"),
                maximum_stock=Decimal("12"),
            )
        )
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=part.id,
        lot_id=lot.id if lot else None,
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
            spare_part_id=part.id,
            serial_number=f"SER-{suffix}",
            lot_id=lot.id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            status="IN_STOCK",
        )
        session.add(serial)
        session.flush()
    return balance, serial


def test_summary_aggregates_only_actor_tenant(session, actor_context) -> None:
    seed_balance(session, tenant_id="tenant-a", suffix="A", on_hand="8")
    seed_balance(session, tenant_id="tenant-b", suffix="B", on_hand="99")

    page = inventory_query_service.list_summaries(
        session,
        actor_context(tenant_id="tenant-a"),
        page=1,
        page_size=20,
    )

    assert page.total == 1
    assert page.pages == 1
    assert page.items[0].on_hand_quantity == Decimal("8")


def test_summary_aggregates_balance_quantities_and_legacy_policy(session, actor_context) -> None:
    warehouse = Warehouse(tenant_id="tenant-a", code="WH-AGG", name="Aggregate")
    part = SparePart(tenant_id="tenant-a", code="SP-AGG", name="Aggregate part")
    first, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="AGG-ONE",
        warehouse=warehouse,
        part=part,
        on_hand="8",
        reserved="1",
        damaged="2",
        quarantined="1",
        in_transit="3",
    )
    second, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="AGG-TWO",
        warehouse=warehouse,
        part=part,
        on_hand="5",
        reserved="1",
        damaged="0",
        quarantined="0",
        in_transit="2",
    )

    page = inventory_query_service.list_summaries(
        session,
        actor_context(),
        page=1,
        page_size=20,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
    )

    assert page.total == 1
    summary = page.items[0]
    assert second.warehouse_id == summary.warehouse_id
    assert summary.on_hand_quantity == Decimal("13")
    assert summary.reserved_quantity == Decimal("2")
    assert summary.damaged_quantity == Decimal("2")
    assert summary.quarantined_quantity == Decimal("1")
    assert summary.in_transit_quantity == Decimal("5")
    assert summary.available_quantity == Decimal("8")
    assert summary.safety_stock == Decimal("2")
    assert summary.reorder_point == Decimal("4")
    assert summary.maximum_stock == Decimal("12")


def test_balance_page_filters_by_serial_and_paginates(session, actor_context) -> None:
    first, serial = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="SERIAL",
        with_serial=True,
    )
    second, _ = seed_balance(session, tenant_id="tenant-a", suffix="SECOND")
    seed_balance(session, tenant_id="tenant-b", suffix="OTHER")

    page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
        location_id=first.location_id,
        lot_id=first.lot_id,
        serial_item_id=serial.id,
    )

    assert second.id != first.id
    assert page.total == 1
    assert page.pages == 1
    assert page.items[0].id == first.id
    assert page.items[0].serial_item_ids == [serial.id]
    assert page.items[0].available_quantity == Decimal("8")
    assert page.items[0].version == 1
