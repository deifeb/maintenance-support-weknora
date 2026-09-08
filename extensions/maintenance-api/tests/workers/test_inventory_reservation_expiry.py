from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType

import pytest
from app.core.exceptions import AppException, NotFoundError
from app.db.session import SessionLocal
from app.models import (
    InventoryBalance,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_reservation import ReleaseCommand
from app.services.inventory_reservation_service import InventoryReservationService
from sqlalchemy import func, select


def _expiry_api() -> ModuleType:
    try:
        return importlib.import_module("app.workers.inventory_reservation_expiry")
    except ModuleNotFoundError as exc:
        if exc.name == "app.workers.inventory_reservation_expiry":
            pytest.fail("Task 5 requires app.workers.inventory_reservation_expiry")
        raise


def _seed_expired_reservation(
    session,
    *,
    tenant_id: str,
    suffix: str,
    status: str = "ACTIVE",
    reserved: str = "5.0000",
    issued: str = "0.0000",
    released: str = "0.0000",
    expires_at: datetime | None = None,
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-EXP-{suffix}",
        name=f"Warehouse expiry {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-EXP-{suffix}",
        name=f"Spare expiry {suffix}",
    )
    session.add_all([warehouse, spare_part])
    session.flush()
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-EXP-{suffix}",
        name=f"Location expiry {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()

    remaining = Decimal(reserved) - Decimal(issued) - Decimal(released)
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_part.id,
        lot_id=None,
        on_hand_quantity=Decimal("10.0000") - Decimal(issued),
        reserved_quantity=remaining,
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()

    reservation = InventoryReservation(
        tenant_id=tenant_id,
        owner_type="MANUAL",
        owner_id=f"owner-exp-{suffix}",
        status=status,
        expires_at=expires_at or datetime(2026, 8, 1, tzinfo=timezone.utc),
        allow_partial=False,
        actor_user_id="worker-seed-user",
        actor_roles_json=["contributor"],
        request_id=f"request-exp-{suffix}",
        version=1,
    )
    session.add(reservation)
    session.flush()
    line = InventoryReservationLine(
        tenant_id=tenant_id,
        reservation_id=reservation.id,
        spare_part_id=spare_part.id,
        balance_id=balance.id,
        lot_id=None,
        serial_item_id=None,
        requested_quantity=Decimal(reserved),
        reserved_quantity=Decimal(reserved),
        issued_quantity=Decimal(issued),
        released_quantity=Decimal(released),
        expected_balance_version=balance.version,
        fefo_rank=1,
        fefo_override_reason=None,
        recommended_selection_json={
            "balance_id": balance.id,
            "quantity": format(Decimal(reserved), ".4f"),
            "rank": 1,
        },
        actual_selection_json={
            "balance_id": balance.id,
            "quantity": format(Decimal(reserved), ".4f"),
            "rank": 1,
        },
        version=1,
    )
    session.add(line)
    session.flush()
    return reservation, line, balance


def test_expiry_idempotency_key_is_stable() -> None:
    expiry_api = _expiry_api()

    assert expiry_api.expiry_idempotency_key("tenant-a", 17, 4) == (
        "reservation-expire:tenant-a:17:4"
    )


def test_worker_batches_in_tenant_then_reservation_id_order(session) -> None:
    expiry_api = _expiry_api()
    b_reservation, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-b",
        suffix="ORDER-B",
    )
    a_first, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="ORDER-A1",
    )
    a_second, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="ORDER-A2",
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=datetime(2026, 8, 7, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert [(item.tenant_id, item.reservation_id) for item in result.items] == [
        ("tenant-a", a_first.id),
        ("tenant-a", a_second.id),
        ("tenant-b", b_reservation.id),
    ]
    assert all(item.code == "EXPIRED" for item in result.items)
    assert all(item.transaction_id is not None for item in result.items)
    assert all(item.request_id for item in result.items)


def test_worker_scans_active_and_partially_issued_only(session) -> None:
    expiry_api = _expiry_api()
    active, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="STATE-ACTIVE",
        status="ACTIVE",
    )
    partial, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="STATE-PARTIAL",
        status="PARTIALLY_ISSUED",
        issued="2.0000",
    )
    released, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="STATE-RELEASED",
        status="RELEASED",
        released="5.0000",
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=datetime(2026, 8, 7, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert [item.reservation_id for item in result.items] == [active.id, partial.id]
    with SessionLocal() as verify:
        assert verify.get(InventoryReservation, active.id).status == "EXPIRED"
        assert verify.get(InventoryReservation, partial.id).status == "EXPIRED"
        assert verify.get(InventoryReservation, released.id).status == "RELEASED"


def test_worker_preserves_issued_quantity_and_only_releases_remaining(session) -> None:
    expiry_api = _expiry_api()
    reservation, line, balance = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="PARTIAL-ISSUED",
        status="PARTIALLY_ISSUED",
        reserved="5.0000",
        issued="2.0000",
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=datetime(2026, 8, 7, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert [(item.reservation_id, item.code) for item in result.items] == [
        (reservation.id, "EXPIRED")
    ]
    with SessionLocal() as verify:
        stored_line = verify.get(InventoryReservationLine, line.id)
        stored_balance = verify.get(InventoryBalance, balance.id)
        assert stored_line.issued_quantity == Decimal("2.0000")
        assert stored_line.released_quantity == Decimal("3.0000")
        assert stored_balance.reserved_quantity == Decimal("0.0000")
        assert stored_balance.on_hand_quantity == Decimal("8.0000")


def test_repeated_worker_batch_is_idempotent(session) -> None:
    expiry_api = _expiry_api()
    reservation, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="REPEAT",
    )
    session.commit()
    as_of = datetime(2026, 8, 7, tzinfo=timezone.utc)

    first = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=as_of,
        batch_size=10,
    )
    second = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=as_of,
        batch_size=10,
    )

    assert [(item.reservation_id, item.code) for item in first.items] == [
        (reservation.id, "EXPIRED")
    ]
    assert second.items == ()
    with SessionLocal() as verify:
        assert verify.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.operation_type == "UNRESERVE"
            )
        ) == 1


def test_one_expiry_failure_does_not_stop_later_items(
    session,
    monkeypatch,
) -> None:
    expiry_api = _expiry_api()
    broken, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="FAIL-FIRST",
    )
    healthy, _, _ = _seed_expired_reservation(
        session,
        tenant_id="tenant-a",
        suffix="FAIL-SECOND",
    )
    original_expire = InventoryReservationService.expire

    def fail_first_expire(
        self,
        service_session,
        actor,
        reservation_id,
        *,
        command,
        idempotency_key,
    ):
        if reservation_id == broken.id:
            raise NotFoundError(
                "inventory_balance",
                999999,
            )
        return original_expire(
            self,
            service_session,
            actor,
            reservation_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr(
        InventoryReservationService,
        "expire",
        fail_first_expire,
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=datetime(2026, 8, 7, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert [(item.reservation_id, item.code) for item in result.items] == [
        (broken.id, "RESOURCE_NOT_FOUND"),
        (healthy.id, "EXPIRED"),
    ]
    with SessionLocal() as verify:
        assert verify.get(InventoryReservation, broken.id).status == "ACTIVE"
        assert verify.get(InventoryReservation, healthy.id).status == "EXPIRED"


def test_manual_release_before_worker_does_not_double_unreserve(
    session,
    actor_contributor,
) -> None:
    expiry_api = _expiry_api()
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    reservation, _, _ = _seed_expired_reservation(
        session,
        tenant_id=actor_contributor.tenant_id,
        suffix="MANUAL-WINS",
        expires_at=expires_at,
    )
    service = InventoryReservationService()
    service.release(
        session,
        actor_contributor,
        reservation.id,
        command=ReleaseCommand(expected_version=reservation.version, lines=()),
        idempotency_key="manual-release-before-expiry-worker",
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=expires_at + timedelta(days=1),
        batch_size=10,
    )

    assert all(item.reservation_id != reservation.id for item in result.items)
    with SessionLocal() as verify:
        assert verify.get(InventoryReservation, reservation.id).status == "RELEASED"
        assert verify.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.operation_type == "UNRESERVE"
            )
        ) == 1


def test_worker_wins_before_request_does_not_double_unreserve(
    session,
    actor_contributor,
) -> None:
    expiry_api = _expiry_api()
    reservation, _, _ = _seed_expired_reservation(
        session,
        tenant_id=actor_contributor.tenant_id,
        suffix="WORKER-WINS",
    )
    session.commit()

    result = expiry_api.expire_inventory_reservations(
        SessionLocal,
        as_of=datetime(2026, 8, 7, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert [(item.reservation_id, item.code) for item in result.items] == [
        (reservation.id, "EXPIRED")
    ]
    with SessionLocal() as request_session:
        stored = request_session.get(InventoryReservation, reservation.id)
        with pytest.raises(AppException) as raised:
            InventoryReservationService().release(
                request_session,
                actor_contributor,
                stored.id,
                command=ReleaseCommand(
                    expected_version=stored.version,
                    lines=(),
                ),
                idempotency_key="release-after-worker-expiry",
            )
        assert raised.value.code == "RESERVATION_EXPIRED"

    with SessionLocal() as verify:
        assert verify.get(InventoryReservation, reservation.id).status == "EXPIRED"
        assert verify.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.operation_type == "UNRESERVE"
            )
        ) == 1
