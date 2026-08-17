from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import (
    InventoryBalance,
    InventoryLot,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository


def _seed_candidate(
    session,
    *,
    tenant_id: str,
    suffix: str,
    spare_part_id: int | None = None,
    location_active: bool = True,
    location_pickable: bool = True,
    lot: bool = True,
    lot_frozen: bool = False,
    lot_quality: str = "AVAILABLE",
    serial_status: str | None = None,
    on_hand: str = "10.0000",
    reserved: str = "2.0000",
    damaged: str = "1.0000",
    quarantined: str = "1.0000",
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    session.add(warehouse)
    session.flush()

    if spare_part_id is None:
        spare_part = SparePart(
            tenant_id=tenant_id,
            code=f"SP-{suffix}",
            name=f"Spare {suffix}",
        )
        session.add(spare_part)
        session.flush()
        spare_part_id = spare_part.id

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
        is_active=location_active,
        is_pickable=location_pickable,
    )
    session.add(location)
    session.flush()

    inventory_lot = None
    if lot:
        inventory_lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare_part_id,
            lot_code=f"LOT-{suffix}",
            received_date=date(2026, 7, 1),
            expiry_date=date(2026, 8, 20),
            quality_status=lot_quality,
            is_frozen=lot_frozen,
        )
        session.add(inventory_lot)
        session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_part_id,
        lot_id=inventory_lot.id if inventory_lot is not None else None,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        damaged_quantity=Decimal(damaged),
        quarantined_quantity=Decimal(quarantined),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()

    serial = None
    if serial_status is not None:
        serial = SerializedItem(
            tenant_id=tenant_id,
            spare_part_id=spare_part_id,
            serial_number=f"SER-{suffix}",
            lot_id=inventory_lot.id if inventory_lot is not None else None,
            warehouse_id=warehouse.id,
            location_id=location.id,
            status=serial_status,
        )
        session.add(serial)
        session.flush()

    return balance, location, inventory_lot, serial


def test_fefo_candidates_are_tenant_scoped(session) -> None:
    repository = InventoryLedgerRepository()
    balance_a, _, _, _ = _seed_candidate(
        session,
        tenant_id="tenant-a",
        suffix="TENANT-A",
    )
    balance_b, _, _, _ = _seed_candidate(
        session,
        tenant_id="tenant-b",
        suffix="TENANT-B",
        spare_part_id=balance_a.spare_part_id,
    )

    rows = repository.list_fefo_candidates(
        session,
        "tenant-a",
        spare_part_id=balance_a.spare_part_id,
        warehouse_id=balance_a.warehouse_id,
    )

    assert [row.balance_id for row in rows] == [balance_a.id]
    assert balance_b.id not in [row.balance_id for row in rows]


def test_fefo_candidates_join_lot_serial_and_preserve_decimal_available(session) -> None:
    repository = InventoryLedgerRepository()
    balance, location, lot, serial = _seed_candidate(
        session,
        tenant_id="tenant-a",
        suffix="JOIN",
        serial_status="IN_STOCK",
    )

    rows = repository.list_fefo_candidates(
        session,
        "tenant-a",
        spare_part_id=balance.spare_part_id,
        warehouse_id=balance.warehouse_id,
    )

    assert len(rows) == 1
    candidate = rows[0]
    assert candidate.balance_id == balance.id
    assert candidate.location_id == location.id
    assert candidate.lot_id == lot.id
    assert candidate.serial_item_id == serial.id
    assert candidate.expiry_date == date(2026, 8, 20)
    assert candidate.received_date == date(2026, 7, 1)
    assert candidate.available_quantity == Decimal("6.0000")
    assert isinstance(candidate.available_quantity, Decimal)
    assert candidate.exclusion_facts == ()


def test_fefo_candidates_return_exclusion_facts_instead_of_hiding_rows(session) -> None:
    repository = InventoryLedgerRepository()
    balance, _, _, _ = _seed_candidate(
        session,
        tenant_id="tenant-a",
        suffix="FACTS",
        location_active=False,
        location_pickable=False,
        lot_frozen=True,
        lot_quality="QUARANTINED",
        serial_status="RESERVED",
        on_hand="4.0000",
        reserved="2.0000",
        damaged="1.0000",
        quarantined="1.0000",
    )

    rows = repository.list_fefo_candidates(
        session,
        "tenant-a",
        spare_part_id=balance.spare_part_id,
        warehouse_id=balance.warehouse_id,
    )

    assert len(rows) == 1
    candidate = rows[0]
    assert candidate.available_quantity == Decimal("0.0000")
    assert set(candidate.exclusion_facts) == {
        "LOCATION_INACTIVE",
        "LOCATION_NOT_PICKABLE",
        "LOT_FROZEN",
        "LOT_QUALITY_QUARANTINED",
        "SERIAL_STATUS_RESERVED",
    }
