from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType

import pytest
from app.core.exceptions import AppException
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.security.actor import MaintenanceRole
from sqlalchemy import func, select


def _reservation_api() -> tuple[ModuleType, ModuleType]:
    try:
        schema_api = importlib.import_module("app.schemas.inventory_reservation")
        service_api = importlib.import_module(
            "app.services.inventory_reservation_service"
        )
    except ModuleNotFoundError as exc:
        if exc.name in {
            "app.schemas.inventory_reservation",
            "app.services.inventory_reservation_service",
        }:
            pytest.fail("Task 4 requires reservation schemas and service")
        raise
    return schema_api, service_api


def _seed_inventory(
    session,
    *,
    tenant_id: str = "tenant-a",
    suffix: str,
    quantities: tuple[str, ...] = ("5.0000", "4.0000"),
    serial: bool = False,
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    balances: list[InventoryBalance] = []
    serial_item = None
    for index, quantity in enumerate(quantities):
        location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code=f"LOC-{suffix}-{index}",
            name=f"Location {suffix} {index}",
            location_type="SHELF",
        )
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare_part.id,
            lot_code=f"LOT-{suffix}-{index}",
            received_date=date(2026, 7, index + 1),
            expiry_date=date(2026, 8, 10 + index),
            quality_status="AVAILABLE",
        )
        session.add_all([location, lot])
        session.flush()
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare_part.id,
            lot_id=lot.id,
            on_hand_quantity=Decimal(quantity),
            reserved_quantity=Decimal("0.0000"),
            damaged_quantity=Decimal("0.0000"),
            quarantined_quantity=Decimal("0.0000"),
            in_transit_quantity=Decimal("0.0000"),
        )
        session.add(balance)
        session.flush()
        balances.append(balance)
        if serial and index == 0:
            serial_item = SerializedItem(
                tenant_id=tenant_id,
                spare_part_id=spare_part.id,
                serial_number=f"SER-{suffix}",
                lot_id=lot.id,
                warehouse_id=warehouse.id,
                location_id=location.id,
                status="IN_STOCK",
            )
            session.add(serial_item)
            session.flush()
    return warehouse, spare_part, balances, serial_item


def _reserve_command(schema_api, warehouse, spare_part, balances, **overrides):
    values = {
        "owner_type": "MANUAL",
        "owner_id": "job-100",
        "spare_part_id": spare_part.id,
        "warehouse_id": warehouse.id,
        "requested_quantity": "7.0000",
        "allow_partial": False,
        "expected_balance_versions": {
            balance.id: balance.version for balance in balances
        },
        "as_of": date(2026, 8, 6),
    }
    values.update(overrides)
    return schema_api.ReserveCommand(**values)


def _reserve(session, actor, *, suffix: str, quantity: str = "5.0000"):
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix=suffix)
    service = service_api.InventoryReservationService()
    reservation = service.reserve(
        session,
        actor,
        command=_reserve_command(
            schema_api,
            warehouse,
            spare_part,
            balances,
            requested_quantity=quantity,
        ),
        idempotency_key=f"reserve-{suffix}",
    )
    return schema_api, service, reservation, balances


def test_reserve_uses_fefo_and_only_increases_reserved(
    session, actor_contributor
) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix="FEFO")
    before_on_hand = [balance.on_hand_quantity for balance in balances]

    result = service_api.InventoryReservationService().reserve(
        session,
        actor_contributor,
        command=_reserve_command(schema_api, warehouse, spare_part, balances),
        idempotency_key="reserve-fefo",
    )

    session.expire_all()
    assert [(line.balance_id, line.reserved_quantity) for line in result.lines] == [
        (balances[0].id, Decimal("5.0000")),
        (balances[1].id, Decimal("2.0000")),
    ]
    assert [balance.on_hand_quantity for balance in balances] == before_on_hand
    assert [balance.reserved_quantity for balance in balances] == [
        Decimal("5.0000"),
        Decimal("2.0000"),
    ]


def test_reserve_is_all_or_nothing_by_default(session, actor_contributor) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(
        session,
        suffix="ATOMIC",
        quantities=("2.0000", "1.0000"),
    )

    with pytest.raises(AppException) as raised:
        service_api.InventoryReservationService().reserve(
            session,
            actor_contributor,
            command=_reserve_command(
                schema_api,
                warehouse,
                spare_part,
                balances,
                requested_quantity="4.0000",
            ),
            idempotency_key="reserve-atomic",
        )

    assert raised.value.code == "INSUFFICIENT_AVAILABLE_INVENTORY"
    session.expire_all()
    assert all(balance.reserved_quantity == 0 for balance in balances)
    assert session.scalar(select(func.count(InventoryReservation.id))) == 0


def test_reserve_allows_explicit_partial_and_reports_unfilled(
    session, actor_contributor
) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(
        session,
        suffix="PARTIAL",
        quantities=("2.0000", "1.0000"),
    )

    result = service_api.InventoryReservationService().reserve(
        session,
        actor_contributor,
        command=_reserve_command(
            schema_api,
            warehouse,
            spare_part,
            balances,
            requested_quantity="4.0000",
            allow_partial=True,
        ),
        idempotency_key="reserve-partial",
    )

    assert result.reserved_quantity == Decimal("3.0000")
    assert result.unfilled_quantity == Decimal("1.0000")
    assert result.line_errors


def test_partial_issue_decrements_on_hand_and_reserved(
    session, actor_contributor
) -> None:
    schema_api, service, reservation, balances = _reserve(
        session,
        actor_contributor,
        suffix="ISSUE",
    )
    line = reservation.lines[0]

    result = service.issue(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.IssueCommand(
            expected_version=reservation.version,
            lines=(
                schema_api.ReservationQuantityLine(
                    reservation_line_id=line.id,
                    quantity="2.0000",
                ),
            ),
        ),
        idempotency_key="issue-partial",
    )

    session.expire_all()
    assert result.status == "PARTIALLY_ISSUED"
    assert result.lines[0].issued_quantity == Decimal("2.0000")
    assert balances[0].on_hand_quantity == Decimal("3.0000")
    assert balances[0].reserved_quantity == Decimal("3.0000")


def test_full_issue_marks_reservation_fulfilled(session, actor_contributor) -> None:
    schema_api, service, reservation, _ = _reserve(
        session,
        actor_contributor,
        suffix="FULFILL",
    )

    result = service.issue(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.IssueCommand(
            expected_version=reservation.version,
            lines=tuple(
                schema_api.ReservationQuantityLine(
                    reservation_line_id=line.id,
                    quantity=line.reserved_quantity,
                )
                for line in reservation.lines
            ),
        ),
        idempotency_key="issue-full",
    )

    assert result.status == "FULFILLED"


def test_release_only_decrements_reserved(session, actor_contributor) -> None:
    schema_api, service, reservation, balances = _reserve(
        session,
        actor_contributor,
        suffix="RELEASE",
    )
    before_on_hand = [balance.on_hand_quantity for balance in balances]

    result = service.release(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.ReleaseCommand(
            expected_version=reservation.version,
            lines=(),
        ),
        idempotency_key="release-all",
    )

    session.expire_all()
    assert result.status == "RELEASED"
    assert [balance.on_hand_quantity for balance in balances] == before_on_hand
    assert all(balance.reserved_quantity == 0 for balance in balances)


def test_return_increases_on_hand_and_references_original_issue(
    session, actor_contributor
) -> None:
    schema_api, service, reservation, balances = _reserve(
        session,
        actor_contributor,
        suffix="RETURN",
    )
    line = reservation.lines[0]
    issued = service.issue(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.IssueCommand(
            expected_version=reservation.version,
            lines=(
                schema_api.ReservationQuantityLine(
                    reservation_line_id=line.id,
                    quantity="2.0000",
                ),
            ),
        ),
        idempotency_key="issue-before-return",
    )
    issue_tx = session.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.operation_type == "ISSUE")
        .order_by(InventoryTransaction.id.desc())
    )
    before_reserved = balances[0].reserved_quantity

    result = service.return_items(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.ReturnCommand(
            expected_version=issued.version,
            lines=(
                schema_api.ReturnLine(
                    reservation_line_id=line.id,
                    issue_transaction_id=issue_tx.id,
                    quantity="1.0000",
                ),
            ),
        ),
        idempotency_key="return-one",
    )

    session.expire_all()
    return_tx = session.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.operation_type == "RETURN")
        .order_by(InventoryTransaction.id.desc())
    )
    assert result.lines[0].issued_quantity == Decimal("2.0000")
    assert balances[0].on_hand_quantity == Decimal("4.0000")
    assert balances[0].reserved_quantity == before_reserved
    assert return_tx.reference_type == "INVENTORY_TRANSACTION"
    assert return_tx.reference_id == str(issue_tx.id)


def test_cancel_releases_remaining_and_marks_cancelled(
    session, actor_contributor
) -> None:
    schema_api, service, reservation, balances = _reserve(
        session,
        actor_contributor,
        suffix="CANCEL",
    )

    result = service.cancel(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.CancelCommand(expected_version=reservation.version),
        idempotency_key="cancel-one",
    )

    session.expire_all()
    assert result.status == "CANCELLED"
    assert all(balance.reserved_quantity == 0 for balance in balances)


def test_expire_releases_unissued_quantity_and_preserves_issued(
    session, actor_contributor
) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix="EXPIRE")
    service = service_api.InventoryReservationService()
    reservation = service.reserve(
        session,
        actor_contributor,
        command=_reserve_command(
            schema_api,
            warehouse,
            spare_part,
            balances,
            requested_quantity="5.0000",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ),
        idempotency_key="reserve-expire",
    )
    reservation = service.issue(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.IssueCommand(
            expected_version=reservation.version,
            lines=(
                schema_api.ReservationQuantityLine(
                    reservation_line_id=reservation.lines[0].id,
                    quantity="2.0000",
                ),
            ),
        ),
        idempotency_key="issue-before-expire",
    )

    result = service.expire(
        session,
        actor_contributor,
        reservation.id,
        command=schema_api.ExpireCommand(
            observed_version=reservation.version,
            as_of=datetime.now(timezone.utc),
        ),
        idempotency_key=(
            f"reservation-expire:tenant-a:{reservation.id}:{reservation.version}"
        ),
    )

    assert result.status == "EXPIRED"
    assert result.lines[0].issued_quantity == Decimal("2.0000")
    assert result.lines[0].released_quantity == Decimal("3.0000")


def test_serial_reservation_is_single_item(session, actor_contributor) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, serial = _seed_inventory(
        session,
        suffix="SERIAL",
        quantities=("1.0000",),
        serial=True,
    )

    result = service_api.InventoryReservationService().reserve(
        session,
        actor_contributor,
        command=_reserve_command(
            schema_api,
            warehouse,
            spare_part,
            balances,
            requested_quantity="1.0000",
            serial_item_id=serial.id,
        ),
        idempotency_key="reserve-serial",
    )

    assert result.lines[0].serial_item_id == serial.id
    assert result.lines[0].reserved_quantity == Decimal("1.0000")


def test_same_idempotency_key_replays_without_double_reserving(
    session, actor_contributor
) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix="REPLAY")
    service = service_api.InventoryReservationService()
    command = _reserve_command(
        schema_api,
        warehouse,
        spare_part,
        balances,
        requested_quantity="3.0000",
    )

    first = service.reserve(
        session,
        actor_contributor,
        command=command,
        idempotency_key="reserve-replay",
    )
    second = service.reserve(
        session,
        actor_contributor,
        command=command,
        idempotency_key="reserve-replay",
    )

    assert first == second
    assert balances[0].reserved_quantity == Decimal("3.0000")
    assert session.scalar(select(func.count(InventoryTransaction.id))) == 1


def test_same_idempotency_key_with_changed_request_is_rejected(
    session, actor_contributor
) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix="REUSE")
    service = service_api.InventoryReservationService()
    service.reserve(
        session,
        actor_contributor,
        command=_reserve_command(
            schema_api,
            warehouse,
            spare_part,
            balances,
            requested_quantity="2.0000",
        ),
        idempotency_key="reserve-reused",
    )

    with pytest.raises(AppException) as raised:
        service.reserve(
            session,
            actor_contributor,
            command=_reserve_command(
                schema_api,
                warehouse,
                spare_part,
                balances,
                requested_quantity="3.0000",
            ),
            idempotency_key="reserve-reused",
        )

    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_expected_version_conflict_rolls_back(session, actor_contributor) -> None:
    schema_api, service, reservation, balances = _reserve(
        session,
        actor_contributor,
        suffix="VERSION",
    )
    before = [balance.reserved_quantity for balance in balances]

    with pytest.raises(AppException) as raised:
        service.release(
            session,
            actor_contributor,
            reservation.id,
            command=schema_api.ReleaseCommand(
                expected_version=reservation.version + 1,
                lines=(),
            ),
            idempotency_key="release-conflict",
        )

    assert raised.value.code == "RESOURCE_CONFLICT"
    session.expire_all()
    assert [balance.reserved_quantity for balance in balances] == before


def test_cross_tenant_reservation_is_not_mutable(session, actor_context) -> None:
    schema_api, service, reservation, _ = _reserve(
        session,
        actor_context(tenant_id="tenant-a"),
        suffix="TENANT",
    )

    with pytest.raises(AppException) as raised:
        service.release(
            session,
            actor_context(tenant_id="tenant-b"),
            reservation.id,
            command=schema_api.ReleaseCommand(
                expected_version=reservation.version,
                lines=(),
            ),
            idempotency_key="cross-tenant-release",
        )

    assert raised.value.code == "RESOURCE_NOT_FOUND"


def test_viewer_cannot_create_reservation(session, actor_context) -> None:
    schema_api, service_api = _reservation_api()
    warehouse, spare_part, balances, _ = _seed_inventory(session, suffix="ROLE")

    with pytest.raises(AppException) as raised:
        service_api.InventoryReservationService().reserve(
            session,
            actor_context(role=MaintenanceRole.VIEWER),
            command=_reserve_command(schema_api, warehouse, spare_part, balances),
            idempotency_key="reserve-viewer",
        )

    assert raised.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_reserve_ledger_entries_match_reservation_lines(
    session, actor_contributor
) -> None:
    _, _, reservation, _ = _reserve(
        session,
        actor_contributor,
        suffix="LINK",
    )
    transaction = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.operation_type == "RESERVE"
        )
    )
    entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(InventoryLedgerEntry.transaction_id == transaction.id)
            .order_by(InventoryLedgerEntry.balance_id)
        ).all()
    )
    lines = list(
        session.scalars(
            select(InventoryReservationLine)
            .where(InventoryReservationLine.reservation_id == reservation.id)
            .order_by(InventoryReservationLine.balance_id)
        ).all()
    )

    assert [entry.balance_id for entry in entries] == [line.balance_id for line in lines]
    assert all(entry.reserved_delta > 0 for entry in entries)
