from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.db.base import Base
from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryReservation,
    InventoryReservationLine,
    InventoryStocktake,
    InventoryStocktakeLine,
    InventoryTransfer,
    InventoryTransferLine,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.inventory_ledger import (
    RESERVATION_STATUSES,
    STOCKTAKE_LINE_RESOLUTIONS,
    STOCKTAKE_STATUSES,
    TRANSFER_STATUSES,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric, UniqueConstraint, text
from sqlalchemy.exc import IntegrityError

OPERATION_TABLES = {
    "inventory_reservations",
    "inventory_reservation_lines",
    "inventory_transfers",
    "inventory_transfer_lines",
    "stocktakes",
    "stocktake_lines",
}


def _constraint_names(table_name: str, kind: type) -> set[str]:
    return {
        constraint.name
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, kind) and constraint.name is not None
    }


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.columns.keys())
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_column_sets(table_name: str) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    result: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for constraint in Base.metadata.tables[table_name].constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        local_columns = tuple(constraint.columns.keys())
        remote_columns = tuple(element.target_fullname for element in constraint.elements)
        result.add((local_columns, remote_columns))
    return result


def _assert_numeric_18_4(table_name: str, *column_names: str) -> None:
    table = Base.metadata.tables[table_name]
    for column_name in column_names:
        column_type = table.c[column_name].type
        assert isinstance(column_type, Numeric)
        assert column_type.precision == 18
        assert column_type.scale == 4


def _enable_foreign_keys(session) -> None:
    session.execute(text("PRAGMA foreign_keys = ON"))


def _seed_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    serialized: bool = False,
) -> tuple[InventoryBalance, InventoryLot | None, SerializedItem | None]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-OP-{suffix}",
        name=f"Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-OP-{suffix}",
        name=f"Spare {suffix}",
        unit="EA",
        is_serialized=serialized,
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-OP-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()

    lot = InventoryLot(
        tenant_id=tenant_id,
        spare_part_id=spare_part.id,
        lot_code=f"LOT-OP-{suffix}",
        received_date=datetime(2026, 8, 1, tzinfo=timezone.utc).date(),
        expiry_date=datetime(2027, 8, 1, tzinfo=timezone.utc).date(),
        quality_status="AVAILABLE",
    )
    session.add(lot)
    session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_part.id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("10.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()

    serial_item = None
    if serialized:
        serial_item = SerializedItem(
            tenant_id=tenant_id,
            spare_part_id=spare_part.id,
            serial_number=f"SER-OP-{suffix}",
            lot_id=lot.id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            status="IN_STOCK",
        )
        session.add(serial_item)
        session.flush()

    return balance, lot, serial_item


def _reservation(*, tenant_id: str, owner_id: str) -> InventoryReservation:
    return InventoryReservation(
        tenant_id=tenant_id,
        owner_type="MANUAL",
        owner_id=owner_id,
        status="ACTIVE",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        allow_partial=False,
        actor_user_id="contributor-a",
        actor_roles_json=["contributor"],
        request_id=f"request-{owner_id}",
    )


def test_inventory_operation_models_register_tables_statuses_and_tenant_parent_keys() -> None:
    assert OPERATION_TABLES <= set(Base.metadata.tables)
    assert RESERVATION_STATUSES == (
        "ACTIVE",
        "PARTIALLY_ISSUED",
        "FULFILLED",
        "RELEASED",
        "CANCELLED",
        "EXPIRED",
    )
    assert TRANSFER_STATUSES == (
        "DRAFT",
        "DISPATCHED",
        "PARTIALLY_RECEIVED",
        "COMPLETED",
        "CANCELLED",
    )
    assert STOCKTAKE_STATUSES == (
        "DRAFT",
        "COUNTING",
        "REVIEWING",
        "CONFIRMED",
        "CONFLICTED",
        "CANCELLED",
    )
    assert STOCKTAKE_LINE_RESOLUTIONS == (
        "PENDING",
        "ADJUSTED",
        "CONFLICTED",
        "RECOUNT_REQUIRED",
        "BASELINE_ACCEPTED",
    )

    assert ("tenant_id", "id") in _unique_column_sets("inventory_reservations")
    assert ("tenant_id", "id") in _unique_column_sets("inventory_transfers")
    assert ("tenant_id", "id") in _unique_column_sets("stocktakes")

    assert (
        ("tenant_id", "reservation_id"),
        (
            "inventory_reservations.tenant_id",
            "inventory_reservations.id",
        ),
    ) in _foreign_key_column_sets("inventory_reservation_lines")
    assert (
        ("tenant_id", "transfer_id"),
        ("inventory_transfers.tenant_id", "inventory_transfers.id"),
    ) in _foreign_key_column_sets("inventory_transfer_lines")
    assert (
        ("tenant_id", "stocktake_id"),
        ("stocktakes.tenant_id", "stocktakes.id"),
    ) in _foreign_key_column_sets("stocktake_lines")


def test_inventory_operation_models_define_exact_quantities_and_database_checks() -> None:
    _assert_numeric_18_4(
        "inventory_reservation_lines",
        "requested_quantity",
        "reserved_quantity",
        "issued_quantity",
        "released_quantity",
    )
    _assert_numeric_18_4(
        "inventory_transfer_lines",
        "requested_quantity",
        "dispatched_quantity",
        "received_quantity",
    )
    _assert_numeric_18_4(
        "stocktake_lines",
        "system_quantity",
        "counted_quantity",
        "variance_quantity",
    )

    assert {
        "ck_inventory_reservation_status",
    } <= _constraint_names("inventory_reservations", CheckConstraint)
    assert {
        "ck_inventory_reservation_line_requested_nonnegative",
        "ck_inventory_reservation_line_reserved_nonnegative",
        "ck_inventory_reservation_line_issued_nonnegative",
        "ck_inventory_reservation_line_released_nonnegative",
        "ck_inventory_reservation_line_lifecycle",
        "ck_inventory_reservation_line_serial_quantities",
    } <= _constraint_names("inventory_reservation_lines", CheckConstraint)
    assert {
        "ck_inventory_transfer_status",
        "ck_inventory_transfer_distinct_locations",
    } <= _constraint_names("inventory_transfers", CheckConstraint)
    assert {
        "ck_inventory_transfer_line_requested_nonnegative",
        "ck_inventory_transfer_line_dispatched_nonnegative",
        "ck_inventory_transfer_line_received_nonnegative",
        "ck_inventory_transfer_line_dispatch_lifecycle",
        "ck_inventory_transfer_line_receive_lifecycle",
        "ck_inventory_transfer_line_serial_quantities",
    } <= _constraint_names("inventory_transfer_lines", CheckConstraint)
    assert {"ck_inventory_stocktake_status"} <= _constraint_names(
        "stocktakes", CheckConstraint
    )
    assert {
        "ck_inventory_stocktake_line_system_nonnegative",
        "ck_inventory_stocktake_line_counted_nonnegative",
        "ck_inventory_stocktake_line_resolution",
        "ck_inventory_stocktake_line_variance",
    } <= _constraint_names("stocktake_lines", CheckConstraint)


def test_reservation_line_rejects_issued_plus_released_above_reserved(session) -> None:
    _enable_foreign_keys(session)
    balance, lot, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RES-LIFECYCLE",
    )
    reservation = _reservation(tenant_id="tenant-a", owner_id="res-lifecycle")
    session.add(reservation)
    session.flush()

    session.add(
        InventoryReservationLine(
            tenant_id="tenant-a",
            reservation_id=reservation.id,
            spare_part_id=balance.spare_part_id,
            balance_id=balance.id,
            lot_id=lot.id,
            serial_item_id=None,
            requested_quantity=Decimal("5.0000"),
            reserved_quantity=Decimal("4.0000"),
            issued_quantity=Decimal("3.0000"),
            released_quantity=Decimal("2.0000"),
            expected_balance_version=balance.version,
            fefo_rank=1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_reservation_line_accepts_four_decimal_lifecycle_on_sqlite(session) -> None:
    _enable_foreign_keys(session)
    balance, lot, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RES-DECIMAL",
    )
    reservation = _reservation(tenant_id="tenant-a", owner_id="res-decimal")
    session.add(reservation)
    session.flush()

    line = InventoryReservationLine(
        tenant_id="tenant-a",
        reservation_id=reservation.id,
        spare_part_id=balance.spare_part_id,
        balance_id=balance.id,
        lot_id=lot.id,
        serial_item_id=None,
        requested_quantity=Decimal("0.3000"),
        reserved_quantity=Decimal("0.3000"),
        issued_quantity=Decimal("0.1000"),
        released_quantity=Decimal("0.2000"),
        expected_balance_version=balance.version,
        fefo_rank=1,
    )
    session.add(line)
    session.commit()

    assert line.issued_quantity + line.released_quantity == line.reserved_quantity


def test_serial_reservation_line_rejects_quantities_outside_zero_or_one(session) -> None:
    _enable_foreign_keys(session)
    balance, lot, serial_item = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RES-SERIAL",
        serialized=True,
    )
    reservation = _reservation(tenant_id="tenant-a", owner_id="res-serial")
    session.add(reservation)
    session.flush()

    session.add(
        InventoryReservationLine(
            tenant_id="tenant-a",
            reservation_id=reservation.id,
            spare_part_id=balance.spare_part_id,
            balance_id=balance.id,
            lot_id=lot.id,
            serial_item_id=serial_item.id,
            requested_quantity=Decimal("2.0000"),
            reserved_quantity=Decimal("2.0000"),
            issued_quantity=Decimal("0.0000"),
            released_quantity=Decimal("0.0000"),
            expected_balance_version=balance.version,
            fefo_rank=1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_reservation_line_rejects_cross_tenant_parent_reference(session) -> None:
    _enable_foreign_keys(session)
    tenant_a_balance, _, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RES-TENANT-A",
    )
    tenant_b_balance, tenant_b_lot, _ = _seed_balance(
        session,
        tenant_id="tenant-b",
        suffix="RES-TENANT-B",
    )
    reservation = _reservation(tenant_id="tenant-a", owner_id="res-tenant")
    session.add(reservation)
    session.flush()

    session.add(
        InventoryReservationLine(
            tenant_id="tenant-b",
            reservation_id=reservation.id,
            spare_part_id=tenant_b_balance.spare_part_id,
            balance_id=tenant_b_balance.id,
            lot_id=tenant_b_lot.id,
            serial_item_id=None,
            requested_quantity=Decimal("1.0000"),
            reserved_quantity=Decimal("1.0000"),
            issued_quantity=Decimal("0.0000"),
            released_quantity=Decimal("0.0000"),
            expected_balance_version=tenant_a_balance.version,
            fefo_rank=1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_transfer_line_rejects_receipt_above_dispatched_quantity(session) -> None:
    _enable_foreign_keys(session)
    source, source_lot, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="TRANSFER-SOURCE",
    )
    target, _, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="TRANSFER-TARGET",
    )
    transfer = InventoryTransfer(
        tenant_id="tenant-a",
        status="DISPATCHED",
        source_warehouse_id=source.warehouse_id,
        source_location_id=source.location_id,
        target_warehouse_id=target.warehouse_id,
        target_location_id=target.location_id,
        reference_type="MANUAL",
        reference_id="transfer-over-receipt",
        reason="warehouse replenishment",
        actor_user_id="admin-a",
        actor_roles_json=["admin"],
        request_id="request-transfer-over-receipt",
        dispatched_at=datetime.now(timezone.utc),
    )
    session.add(transfer)
    session.flush()

    session.add(
        InventoryTransferLine(
            tenant_id="tenant-a",
            transfer_id=transfer.id,
            spare_part_id=source.spare_part_id,
            source_balance_id=source.id,
            target_balance_id=target.id,
            lot_id=source_lot.id,
            serial_item_id=None,
            requested_quantity=Decimal("5.0000"),
            dispatched_quantity=Decimal("4.0000"),
            received_quantity=Decimal("5.0000"),
            expected_source_version=source.version,
            expected_target_version=target.version,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_stocktake_line_accepts_four_decimal_variance_on_sqlite(session) -> None:
    _enable_foreign_keys(session)
    balance, lot, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="STOCKTAKE-DECIMAL",
    )
    stocktake = InventoryStocktake(
        tenant_id="tenant-a",
        warehouse_id=balance.warehouse_id,
        location_id=balance.location_id,
        status="COUNTING",
        snapshot_at=datetime.now(timezone.utc),
        actor_user_id="contributor-a",
        actor_roles_json=["contributor"],
        request_id="request-stocktake-decimal",
    )
    session.add(stocktake)
    session.flush()

    line = InventoryStocktakeLine(
        tenant_id="tenant-a",
        stocktake_id=stocktake.id,
        balance_id=balance.id,
        spare_part_id=balance.spare_part_id,
        lot_id=lot.id,
        serial_item_id=None,
        system_quantity=Decimal("0.3000"),
        counted_quantity=Decimal("0.2000"),
        variance_quantity=Decimal("-0.1000"),
        snapshot_balance_version=balance.version,
        resolution="PENDING",
    )
    session.add(line)
    session.commit()

    assert line.variance_quantity == Decimal("-0.1000")


def test_stocktake_line_rejects_invalid_resolution(session) -> None:
    _enable_foreign_keys(session)
    balance, lot, _ = _seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="STOCKTAKE-RESOLUTION",
    )
    stocktake = InventoryStocktake(
        tenant_id="tenant-a",
        warehouse_id=balance.warehouse_id,
        location_id=balance.location_id,
        status="COUNTING",
        snapshot_at=datetime.now(timezone.utc),
        actor_user_id="contributor-a",
        actor_roles_json=["contributor"],
        request_id="request-stocktake-resolution",
    )
    session.add(stocktake)
    session.flush()

    session.add(
        InventoryStocktakeLine(
            tenant_id="tenant-a",
            stocktake_id=stocktake.id,
            balance_id=balance.id,
            spare_part_id=balance.spare_part_id,
            lot_id=lot.id,
            serial_item_id=None,
            system_quantity=Decimal("10.0000"),
            counted_quantity=Decimal("9.0000"),
            variance_quantity=Decimal("-1.0000"),
            snapshot_balance_version=balance.version,
            resolution="INVALID",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
