from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType

import pytest
from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryReservation,
    InventoryReservationLine,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from sqlalchemy.dialects import postgresql, sqlite


def _reservation_repository_api() -> ModuleType:
    try:
        return importlib.import_module(
            "app.repositories.inventory_reservation_repository"
        )
    except ModuleNotFoundError as exc:
        if exc.name == "app.repositories.inventory_reservation_repository":
            pytest.fail(
                "Task 4 requires app.repositories.inventory_reservation_repository"
            )
        raise


def _seed_reservation(
    session,
    *,
    tenant_id: str,
    suffix: str,
    owner_id: str | None = None,
    status: str = "ACTIVE",
    expires_at: datetime | None = None,
    line_count: int = 2,
) -> tuple[InventoryReservation, list[InventoryReservationLine]]:
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

    reservation = InventoryReservation(
        tenant_id=tenant_id,
        owner_type="MANUAL",
        owner_id=owner_id or f"owner-{suffix}",
        status=status,
        expires_at=expires_at,
        allow_partial=False,
        actor_user_id="user-a",
        actor_roles_json=["contributor"],
        request_id=f"request-{suffix}",
    )
    session.add(reservation)
    session.flush()

    lines: list[InventoryReservationLine] = []
    for index in range(line_count):
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
        )
        session.add_all([location, lot])
        session.flush()
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare_part.id,
            lot_id=lot.id,
            on_hand_quantity=Decimal("5.0000"),
            reserved_quantity=Decimal("2.0000"),
            damaged_quantity=Decimal("0.0000"),
            quarantined_quantity=Decimal("0.0000"),
            in_transit_quantity=Decimal("0.0000"),
        )
        session.add(balance)
        session.flush()
        line = InventoryReservationLine(
            tenant_id=tenant_id,
            reservation_id=reservation.id,
            spare_part_id=spare_part.id,
            balance_id=balance.id,
            lot_id=lot.id,
            serial_item_id=None,
            requested_quantity=Decimal("2.0000"),
            reserved_quantity=Decimal("2.0000"),
            issued_quantity=Decimal("0.0000"),
            released_quantity=Decimal("0.0000"),
            expected_balance_version=balance.version,
            fefo_rank=index + 1,
        )
        session.add(line)
        session.flush()
        lines.append(line)
    return reservation, lines


def test_get_and_list_are_tenant_and_owner_scoped(session) -> None:
    api = _reservation_repository_api()
    repository = api.InventoryReservationRepository()
    visible, _ = _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="VISIBLE",
        owner_id="job-100",
    )
    hidden, _ = _seed_reservation(
        session,
        tenant_id="tenant-b",
        suffix="HIDDEN",
        owner_id="job-100",
    )

    assert repository.get(session, "tenant-a", visible.id).id == visible.id
    assert repository.get(session, "tenant-a", hidden.id) is None
    rows = repository.list(
        session,
        "tenant-a",
        owner_type="MANUAL",
        owner_id="job-100",
    )
    assert [row.id for row in rows] == [visible.id]


def test_lock_aggregate_locks_parent_and_orders_lines(session) -> None:
    api = _reservation_repository_api()
    repository = api.InventoryReservationRepository()
    reservation, lines = _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="LOCK",
        line_count=3,
    )

    statement = repository.lock_statement("tenant-a", reservation.id)
    sqlite_sql = str(statement.compile(dialect=sqlite.dialect()))
    postgres_sql = str(statement.compile(dialect=postgresql.dialect()))
    locked = repository.lock_aggregate(session, "tenant-a", reservation.id)

    assert "inventory_reservations" in sqlite_sql
    assert "FOR UPDATE" in postgres_sql
    assert locked is not None
    locked_reservation, locked_lines = locked
    assert locked_reservation.id == reservation.id
    assert [line.id for line in locked_lines] == sorted(line.id for line in lines)


def test_expiry_scan_is_tenant_scoped_active_only_and_stable(session) -> None:
    api = _reservation_repository_api()
    repository = api.InventoryReservationRepository()
    now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    first, _ = _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="EXP-1",
        expires_at=now - timedelta(hours=2),
    )
    second, _ = _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="EXP-2",
        expires_at=now - timedelta(hours=1),
    )
    _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="FUTURE",
        expires_at=now + timedelta(hours=1),
    )
    _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="DONE",
        status="FULFILLED",
        expires_at=now - timedelta(hours=3),
    )
    _seed_reservation(
        session,
        tenant_id="tenant-b",
        suffix="OTHER",
        expires_at=now - timedelta(hours=3),
    )

    rows = repository.list_expired_candidates(
        session,
        "tenant-a",
        as_of=now,
        limit=10,
    )

    assert [row.id for row in rows] == [first.id, second.id]


def test_missing_and_cross_tenant_aggregate_are_invisible(session) -> None:
    api = _reservation_repository_api()
    repository = api.InventoryReservationRepository()
    reservation, _ = _seed_reservation(
        session,
        tenant_id="tenant-b",
        suffix="CROSS",
    )

    assert repository.lock_aggregate(session, "tenant-a", reservation.id) is None
    assert repository.lock_aggregate(session, "tenant-a", 999999) is None


def test_repository_queries_do_not_commit(session) -> None:
    api = _reservation_repository_api()
    repository = api.InventoryReservationRepository()
    reservation, _ = _seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="ROLLBACK",
    )

    repository.get(session, "tenant-a", reservation.id)
    repository.list(session, "tenant-a")
    repository.lock_aggregate(session, "tenant-a", reservation.id)
    assert session.in_transaction()
    session.rollback()

    assert repository.get(session, "tenant-a", reservation.id) is None
