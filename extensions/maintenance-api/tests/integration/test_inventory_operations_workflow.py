from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_reservation import (
    IssueCommand,
    ReleaseCommand,
    ReservationQuantityLine,
    ReserveCommand,
    ReturnCommand,
    ReturnLine,
)
from app.security.actor import ActorContext
from app.services.inventory_reservation_service import (
    InventoryReservationService,
)
from app.services.inventory_stocktake_service import (
    InventoryStocktakeService,
)
from app.services.inventory_transfer_service import (
    InventoryTransferService,
)
from app.workers.inventory_reservation_expiry import (
    expire_inventory_reservations,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _seed_balance(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
    on_hand: str,
) -> tuple[
    Warehouse,
    WarehouseLocation,
    SparePart,
    InventoryBalance,
]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-GATE-{suffix}",
        name=f"Gate Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-GATE-{suffix}",
        name=f"Gate Spare {suffix}",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-GATE-{suffix}",
        name=f"Gate Location {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_part.id,
        lot_id=None,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()
    return warehouse, location, spare_part, balance


def _transaction_count(
    session: Session,
    operation_type: str,
) -> int:
    return int(
        session.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.operation_type
                == operation_type
            )
        )
        or 0
    )


def _ledger_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count(InventoryLedgerEntry.id))
        )
        or 0
    )


def test_gate_reservation_issue_return_release_workflow(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    warehouse, _, spare_part, balance = _seed_balance(
        session,
        tenant_id=actor_contributor.tenant_id,
        suffix="RESERVATION",
        on_hand="5.0000",
    )
    service = InventoryReservationService()
    command = ReserveCommand(
        owner_type="MANUAL",
        owner_id="GATE-RESERVATION",
        spare_part_id=spare_part.id,
        warehouse_id=warehouse.id,
        requested_quantity="5.0000",
        allow_partial=False,
        expected_balance_versions={
            balance.id: balance.version,
        },
        as_of=date(2026, 8, 15),
    )

    reserved = service.reserve(
        session,
        actor_contributor,
        command=command,
        idempotency_key="gate-reserve",
    )
    replay = service.reserve(
        session,
        actor_contributor,
        command=command,
        idempotency_key="gate-reserve",
    )
    assert replay == reserved
    assert reserved.status == "ACTIVE"
    assert reserved.reserved_quantity == Decimal("5.0000")
    assert _transaction_count(session, "RESERVE") == 1

    line = reserved.lines[0]
    issued = service.issue(
        session,
        actor_contributor,
        reserved.id,
        command=IssueCommand(
            expected_version=reserved.version,
            lines=(
                ReservationQuantityLine(
                    reservation_line_id=line.id,
                    quantity="2.0000",
                ),
            ),
        ),
        idempotency_key="gate-issue",
    )
    issue_transaction = session.scalar(
        select(InventoryTransaction)
        .where(
            InventoryTransaction.operation_type == "ISSUE",
            InventoryTransaction.reference_id
            == str(reserved.id),
        )
        .order_by(InventoryTransaction.id.desc())
    )
    assert issue_transaction is not None
    assert issued.status == "PARTIALLY_ISSUED"

    returned = service.return_items(
        session,
        actor_contributor,
        reserved.id,
        command=ReturnCommand(
            expected_version=issued.version,
            lines=(
                ReturnLine(
                    reservation_line_id=line.id,
                    issue_transaction_id=issue_transaction.id,
                    quantity="1.0000",
                ),
            ),
        ),
        idempotency_key="gate-return",
    )
    assert returned.status == "PARTIALLY_ISSUED"

    released = service.release(
        session,
        actor_contributor,
        reserved.id,
        command=ReleaseCommand(
            expected_version=returned.version,
            lines=(),
        ),
        idempotency_key="gate-release",
    )
    assert released.status == "RELEASED"

    session.expire_all()
    persisted_balance = session.get(
        InventoryBalance,
        balance.id,
    )
    assert persisted_balance is not None
    assert persisted_balance.on_hand_quantity == Decimal(
        "4.0000"
    )
    assert persisted_balance.reserved_quantity == Decimal(
        "0.0000"
    )
    assert _transaction_count(session, "RESERVE") == 1
    assert _transaction_count(session, "ISSUE") == 1
    assert _transaction_count(session, "RETURN") == 1
    assert _transaction_count(session, "UNRESERVE") == 1
    assert _ledger_count(session) == 4


def test_gate_transfer_dispatch_partial_receive_final_receive(
    session: Session,
    actor_admin: ActorContext,
) -> None:
    warehouse, source_location, spare_part, source = (
        _seed_balance(
            session,
            tenant_id=actor_admin.tenant_id,
            suffix="TRANSFER-SOURCE",
            on_hand="10.0000",
        )
    )
    target_location = WarehouseLocation(
        tenant_id=actor_admin.tenant_id,
        warehouse_id=warehouse.id,
        code="LOC-GATE-TRANSFER-TARGET",
        name="Gate Transfer Target",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(target_location)
    session.flush()

    service = InventoryTransferService()
    transfer = service.create(
        session,
        actor_admin,
        command={
            "source_warehouse_id": warehouse.id,
            "source_location_id": source_location.id,
            "target_warehouse_id": warehouse.id,
            "target_location_id": target_location.id,
            "reference_type": "work_order",
            "reference_id": "GATE-TRANSFER",
            "reason": "gate transfer workflow",
            "lines": [
                {
                    "spare_part_id": spare_part.id,
                    "source_balance_id": source.id,
                    "lot_id": None,
                    "serial_item_id": None,
                    "quantity": "2.0000",
                    "expected_source_version": source.version,
                }
            ],
        },
        idempotency_key="gate-transfer-create",
    )

    dispatch_preview = service.preview_dispatch(
        session,
        actor_admin,
        transfer.id,
        command={
            "expected_version": transfer.version,
        },
        idempotency_key="gate-dispatch-preview",
    )
    dispatched = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command={
            "transaction_id": (
                dispatch_preview.transaction_id
            ),
            "confirmation_token": (
                dispatch_preview.confirmation_token
            ),
            "expected_transaction_version": (
                dispatch_preview.transaction_version
            ),
        },
        idempotency_key="gate-dispatch-execute",
    )
    assert dispatched.status == "DISPATCHED"

    first_preview = service.preview_receive(
        session,
        actor_admin,
        dispatched.id,
        command={
            "expected_version": dispatched.version,
            "lines": [
                {
                    "transfer_line_id": (
                        dispatched.lines[0].id
                    ),
                    "quantity": "1.5000",
                }
            ],
        },
        idempotency_key="gate-receive-preview-1",
    )
    partial = service.execute_receive(
        session,
        actor_admin,
        dispatched.id,
        command={
            "transaction_id": first_preview.transaction_id,
            "confirmation_token": (
                first_preview.confirmation_token
            ),
            "expected_transaction_version": (
                first_preview.transaction_version
            ),
        },
        idempotency_key="gate-receive-execute-1",
    )
    assert partial.status == "PARTIALLY_RECEIVED"

    second_preview = service.preview_receive(
        session,
        actor_admin,
        partial.id,
        command={
            "expected_version": partial.version,
            "lines": [
                {
                    "transfer_line_id": (
                        partial.lines[0].id
                    ),
                    "quantity": "0.5000",
                }
            ],
        },
        idempotency_key="gate-receive-preview-2",
    )
    completed = service.execute_receive(
        session,
        actor_admin,
        partial.id,
        command={
            "transaction_id": second_preview.transaction_id,
            "confirmation_token": (
                second_preview.confirmation_token
            ),
            "expected_transaction_version": (
                second_preview.transaction_version
            ),
        },
        idempotency_key="gate-receive-execute-2",
    )
    assert completed.status == "COMPLETED"

    session.expire_all()
    source_after = session.get(
        InventoryBalance,
        source.id,
    )
    target_after = session.get(
        InventoryBalance,
        completed.lines[0].target_balance_id,
    )
    assert source_after is not None
    assert target_after is not None
    assert source_after.on_hand_quantity == Decimal(
        "8.0000"
    )
    assert target_after.on_hand_quantity == Decimal(
        "2.0000"
    )
    assert target_after.in_transit_quantity == Decimal(
        "0.0000"
    )
    assert _transaction_count(
        session,
        "TRANSFER_DISPATCH",
    ) == 1
    assert _transaction_count(
        session,
        "TRANSFER_RECEIVE",
    ) == 2


def test_gate_stocktake_partial_confirm_rebase_then_final_confirm(
    session: Session,
    actor_contributor: ActorContext,
    actor_admin: ActorContext,
) -> None:
    warehouse = Warehouse(
        tenant_id=actor_contributor.tenant_id,
        code="WH-GATE-STOCKTAKE",
        name="Gate Stocktake Warehouse",
    )
    session.add(warehouse)
    session.flush()
    location = WarehouseLocation(
        tenant_id=actor_contributor.tenant_id,
        warehouse_id=warehouse.id,
        code="LOC-GATE-STOCKTAKE",
        name="Gate Stocktake Location",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    balances: list[InventoryBalance] = []
    for index, quantity in enumerate(
        ("10.0000", "4.0000"),
        start=1,
    ):
        part = SparePart(
            tenant_id=actor_contributor.tenant_id,
            code=f"SP-GATE-STOCKTAKE-{index}",
            name=f"Gate Stocktake Spare {index}",
            unit="EA",
            is_serialized=False,
        )
        session.add(part)
        session.flush()
        balance = InventoryBalance(
            tenant_id=actor_contributor.tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=part.id,
            lot_id=None,
            on_hand_quantity=Decimal(quantity),
            reserved_quantity=Decimal("0.0000"),
            damaged_quantity=Decimal("0.0000"),
            quarantined_quantity=Decimal("0.0000"),
            in_transit_quantity=Decimal("0.0000"),
        )
        session.add(balance)
        session.flush()
        balances.append(balance)

    service = InventoryStocktakeService()
    created = service.create(
        session,
        actor_contributor,
        command={
            "warehouse_id": warehouse.id,
            "location_id": location.id,
        },
        idempotency_key="gate-stocktake-create",
    )
    counting = service.start(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="gate-stocktake-start",
    )

    current = counting
    for index, line in enumerate(
        counting.lines,
        start=1,
    ):
        current_line = next(
            item
            for item in current.lines
            if item.id == line.id
        )
        current = service.record_count(
            session,
            actor_contributor,
            current.id,
            current_line.id,
            command={
                "expected_version": current.version,
                "expected_line_version": (
                    current_line.version
                ),
                "counted_quantity": (
                    current_line.system_quantity
                    - Decimal("1.0000")
                ),
            },
            idempotency_key=(
                f"gate-stocktake-count-{index}"
            ),
        )

    reviewing = service.review(
        session,
        actor_contributor,
        current.id,
        expected_version=current.version,
        idempotency_key="gate-stocktake-review",
    )
    first_preview = service.preview_confirm(
        session,
        actor_admin,
        reviewing.id,
        command={
            "expected_version": reviewing.version,
        },
        idempotency_key="gate-stocktake-preview-1",
    )

    conflict_balance = session.get(
        InventoryBalance,
        balances[1].id,
    )
    assert conflict_balance is not None
    conflict_balance.version += 1
    session.flush()

    partial = service.execute_confirm(
        session,
        actor_admin,
        reviewing.id,
        command={
            "transaction_id": (
                first_preview.transaction_id
            ),
            "expected_transaction_version": (
                first_preview.transaction_version
            ),
            "confirmation_token": (
                first_preview.confirmation_token
            ),
        },
        idempotency_key="gate-stocktake-execute-1",
    )
    assert partial.status == "CONFLICTED"

    adjusted_line = next(
        line
        for line in partial.lines
        if line.resolution == "ADJUSTED"
    )
    conflicted_line = next(
        line
        for line in partial.lines
        if line.resolution == "CONFLICTED"
    )
    adjusted_balance = session.get(
        InventoryBalance,
        adjusted_line.balance_id,
    )
    assert adjusted_balance is not None
    adjusted_quantity = adjusted_balance.on_hand_quantity
    adjusted_version = adjusted_balance.version

    rebased = service.rebase_lines(
        session,
        actor_contributor,
        partial.id,
        command={
            "expected_version": partial.version,
            "lines": [
                {
                    "line_id": conflicted_line.id,
                    "action": "RECOUNT",
                }
            ],
        },
        idempotency_key="gate-stocktake-rebase",
    )
    recount_line = next(
        line
        for line in rebased.lines
        if line.id == conflicted_line.id
    )
    current_conflict_balance = session.get(
        InventoryBalance,
        recount_line.balance_id,
    )
    assert current_conflict_balance is not None

    recounted = service.record_count(
        session,
        actor_contributor,
        rebased.id,
        recount_line.id,
        command={
            "expected_version": rebased.version,
            "expected_line_version": recount_line.version,
            "counted_quantity": (
                current_conflict_balance.on_hand_quantity
            ),
        },
        idempotency_key="gate-stocktake-recount",
    )
    reviewing_again = service.review(
        session,
        actor_contributor,
        recounted.id,
        expected_version=recounted.version,
        idempotency_key="gate-stocktake-review-2",
    )
    second_preview = service.preview_confirm(
        session,
        actor_admin,
        reviewing_again.id,
        command={
            "expected_version": reviewing_again.version,
        },
        idempotency_key="gate-stocktake-preview-2",
    )
    completed = service.execute_confirm(
        session,
        actor_admin,
        reviewing_again.id,
        command={
            "transaction_id": (
                second_preview.transaction_id
            ),
            "expected_transaction_version": (
                second_preview.transaction_version
            ),
            "confirmation_token": (
                second_preview.confirmation_token
            ),
        },
        idempotency_key="gate-stocktake-execute-2",
    )
    assert completed.status == "CONFIRMED"

    adjusted_after = session.get(
        InventoryBalance,
        adjusted_line.balance_id,
    )
    assert adjusted_after is not None
    assert adjusted_after.on_hand_quantity == adjusted_quantity
    assert adjusted_after.version == adjusted_version

    first_transaction = session.get(
        InventoryTransaction,
        first_preview.transaction_id,
    )
    second_transaction = session.get(
        InventoryTransaction,
        second_preview.transaction_id,
    )
    assert first_transaction is not None
    assert second_transaction is not None
    assert first_transaction.status == "PARTIALLY_COMPLETED"
    assert second_transaction.status == "COMPLETED"


def test_gate_expiry_worker_then_request_releases_once(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    warehouse, _, spare_part, balance = _seed_balance(
        session,
        tenant_id=actor_contributor.tenant_id,
        suffix="EXPIRY",
        on_hand="5.0000",
    )
    service = InventoryReservationService()
    reservation = service.reserve(
        session,
        actor_contributor,
        command=ReserveCommand(
            owner_type="MANUAL",
            owner_id="GATE-EXPIRY",
            spare_part_id=spare_part.id,
            warehouse_id=warehouse.id,
            requested_quantity="3.0000",
            allow_partial=False,
            expected_balance_versions={
                balance.id: balance.version,
            },
            as_of=date(2026, 8, 15),
            expires_at=(
                datetime.now(timezone.utc)
                - timedelta(minutes=1)
            ),
        ),
        idempotency_key="gate-expiry-reserve",
    )
    session.commit()

    result = expire_inventory_reservations(
        SessionLocal,
        as_of=(
            datetime.now(timezone.utc)
            + timedelta(minutes=1)
        ),
        batch_size=10,
    )
    assert [
        (item.tenant_id, item.reservation_id, item.code)
        for item in result.items
    ] == [
        (
            actor_contributor.tenant_id,
            reservation.id,
            "EXPIRED",
        )
    ]

    with SessionLocal() as request_session:
        stored = request_session.get(
            InventoryReservation,
            reservation.id,
        )
        assert stored is not None
        with pytest.raises(AppException) as raised:
            InventoryReservationService().release(
                request_session,
                actor_contributor,
                stored.id,
                command=ReleaseCommand(
                    expected_version=stored.version,
                    lines=(),
                ),
                idempotency_key=(
                    "gate-expiry-request-release"
                ),
            )
        assert raised.value.code == "RESERVATION_EXPIRED"

    with SessionLocal() as verify:
        persisted_balance = verify.get(
            InventoryBalance,
            balance.id,
        )
        assert persisted_balance is not None
        assert persisted_balance.reserved_quantity == Decimal(
            "0.0000"
        )
        assert _transaction_count(
            verify,
            "UNRESERVE",
        ) == 1
