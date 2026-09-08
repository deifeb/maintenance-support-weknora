from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
)
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    InventoryTransfer,
    InventoryTransferLine,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.services.inventory_operation_service import (
    InventoryOperationService,
)
from app.services.inventory_transaction_service import (
    InventoryTransactionService,
)
from sqlalchemy import func, select


def _seed_balance(
    session,
    *,
    suffix: str,
    on_hand: str = "10",
    reserved: str = "0",
) -> InventoryBalance:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-REV-{suffix}",
        name=f"Reverse Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code=f"SP-REV-{suffix}",
        name=f"Reverse Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code=f"LOC-REV-{suffix}",
        name=f"Reverse Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()

    balance = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("0"),
    )
    session.add(balance)
    session.flush()

    return balance


def _adjust(
    session,
    actor_admin,
    balance: InventoryBalance,
    *,
    on_hand: str = "0",
    reserved: str = "0",
    key: str,
    reason: str,
):
    return InventoryTransactionService().adjust(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(
            on_hand=Decimal(on_hand),
            reserved=Decimal(reserved),
        ),
        reason=reason,
        idempotency_key=key,
    )


def _create_original_adjustment(
    session,
    actor_admin,
    balance: InventoryBalance,
    *,
    delta: str = "5",
    key: str,
):
    return _adjust(
        session,
        actor_admin,
        balance,
        on_hand=delta,
        key=key,
        reason="original correction to reverse",
    )


def _reverse_preview_command(
    original,
) -> dict[str, object]:
    return {
        "expected_transaction_version": original.version,
        "reason": "reverse erroneous inventory correction",
    }


def _reverse_preview_command_for_row(
    original: InventoryTransaction,
) -> dict[str, object]:
    return {
        "expected_transaction_version": original.version,
        "reason": "reverse erroneous inventory correction",
    }


def _execute_command(
    preview,
) -> dict[str, object]:
    return {
        "confirmation_token": preview.confirmation_token,
        "expected_transaction_version": (
            preview.transaction_version
        ),
    }


def _transaction_business_snapshot(
    transaction: InventoryTransaction,
) -> dict[str, object]:
    # Reversal linkage may legitimately update:
    #
    # - reversed_transaction_id
    # - response_snapshot_json
    # - version, if linkage metadata is versioned
    #
    # Those fields are therefore excluded. Existing business facts
    # must otherwise remain unchanged.
    return {
        "id": transaction.id,
        "tenant_id": transaction.tenant_id,
        "operation_type": transaction.operation_type,
        "status": transaction.status,
        "idempotency_key": transaction.idempotency_key,
        "request_hash": transaction.request_hash,
        "reference_type": transaction.reference_type,
        "reference_id": transaction.reference_id,
        "reason": transaction.reason,
        "actor_user_id": transaction.actor_user_id,
        "actor_roles_json": deepcopy(
            transaction.actor_roles_json
        ),
        "request_id": transaction.request_id,
        "completed_at": transaction.completed_at,
        "failed_at": transaction.failed_at,
    }


def _entry_snapshot(
    entry: InventoryLedgerEntry,
) -> dict[str, object]:
    return {
        "id": entry.id,
        "tenant_id": entry.tenant_id,
        "transaction_id": entry.transaction_id,
        "balance_id": entry.balance_id,
        "spare_part_id": entry.spare_part_id,
        "warehouse_id": entry.warehouse_id,
        "location_id": entry.location_id,
        "lot_id": entry.lot_id,
        "serial_item_id": entry.serial_item_id,
        "on_hand_delta": entry.on_hand_delta,
        "reserved_delta": entry.reserved_delta,
        "damaged_delta": entry.damaged_delta,
        "quarantined_delta": entry.quarantined_delta,
        "in_transit_delta": entry.in_transit_delta,
        "state_before_json": deepcopy(
            entry.state_before_json
        ),
        "state_after_json": deepcopy(
            entry.state_after_json
        ),
        "before_balance_version": (
            entry.before_balance_version
        ),
        "resulting_balance_version": (
            entry.resulting_balance_version
        ),
    }


def _ledger_count(
    session,
) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )


def _transaction_count(
    session,
) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(
                InventoryTransaction
            )
        )
        or 0
    )


def _completed_reverse_count(
    session,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(InventoryTransaction)
            .where(
                InventoryTransaction.operation_type
                == "REVERSE",
                InventoryTransaction.status
                == "COMPLETED",
            )
        )
        or 0
    )


def _original_entry(
    session,
    transaction_id: int,
) -> InventoryLedgerEntry:
    entry = session.scalar(
        select(InventoryLedgerEntry)
        .where(
            InventoryLedgerEntry.transaction_id
            == transaction_id
        )
        .order_by(InventoryLedgerEntry.id)
    )

    assert entry is not None

    return entry


def _add_reservation_dependency(
    session,
    actor_admin,
    balance: InventoryBalance,
) -> tuple[str, int]:
    reservation = InventoryReservation(
        tenant_id=actor_admin.tenant_id,
        owner_type="work_order",
        owner_id="WO-REV-DEPENDENCY",
        status="ACTIVE",
        allow_partial=False,
        actor_user_id=actor_admin.user_id,
        actor_roles_json=[
            actor_admin.role.value
        ],
        request_id=actor_admin.request_id,
    )
    session.add(reservation)
    session.flush()

    line = InventoryReservationLine(
        tenant_id=actor_admin.tenant_id,
        reservation_id=reservation.id,
        spare_part_id=balance.spare_part_id,
        balance_id=balance.id,
        requested_quantity=Decimal("1.0000"),
        reserved_quantity=Decimal("1.0000"),
        issued_quantity=Decimal("0.0000"),
        released_quantity=Decimal("0.0000"),
        expected_balance_version=balance.version,
        fefo_rank=1,
    )
    session.add(line)
    session.flush()

    return (
        "inventory_reservation",
        reservation.id,
    )


def _add_transfer_dependency(
    session,
    actor_admin,
    balance: InventoryBalance,
) -> tuple[str, int]:
    target_location = WarehouseLocation(
        tenant_id=actor_admin.tenant_id,
        warehouse_id=balance.warehouse_id,
        code=f"REV-TARGET-{balance.id}",
        name=f"Reverse Target {balance.id}",
        location_type="SHELF",
    )
    session.add(target_location)
    session.flush()

    target_balance = InventoryBalance(
        tenant_id=actor_admin.tenant_id,
        warehouse_id=balance.warehouse_id,
        location_id=target_location.id,
        spare_part_id=balance.spare_part_id,
        on_hand_quantity=Decimal("0"),
        reserved_quantity=Decimal("0"),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("0"),
    )
    session.add(target_balance)
    session.flush()

    transfer = InventoryTransfer(
        tenant_id=actor_admin.tenant_id,
        status="DRAFT",
        source_warehouse_id=balance.warehouse_id,
        source_location_id=balance.location_id,
        target_warehouse_id=balance.warehouse_id,
        target_location_id=target_location.id,
        reason="downstream transfer dependency",
        actor_user_id=actor_admin.user_id,
        actor_roles_json=[
            actor_admin.role.value
        ],
        request_id=actor_admin.request_id,
    )
    session.add(transfer)
    session.flush()

    line = InventoryTransferLine(
        tenant_id=actor_admin.tenant_id,
        transfer_id=transfer.id,
        spare_part_id=balance.spare_part_id,
        source_balance_id=balance.id,
        target_balance_id=target_balance.id,
        requested_quantity=Decimal("1.0000"),
        dispatched_quantity=Decimal("0.0000"),
        received_quantity=Decimal("0.0000"),
        expected_source_version=balance.version,
        expected_target_version=target_balance.version,
    )
    session.add(line)
    session.flush()

    return (
        "inventory_transfer",
        transfer.id,
    )


def test_reverse_preview_has_no_balance_or_ledger_side_effects(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="PREVIEW",
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        key="reverse-original-preview",
    )
    service = InventoryOperationService()

    session.refresh(balance)

    quantity_before = balance.on_hand_quantity
    version_before = balance.version
    ledger_before = _ledger_count(session)
    transaction_before = _transaction_count(
        session
    )

    original_row = session.get(
        InventoryTransaction,
        original.id,
    )

    assert original_row is not None
    assert (
        original_row.reversed_transaction_id
        is None
    )

    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-no-side-effects"
        ),
    )

    session.refresh(balance)
    session.refresh(original_row)

    assert preview.operation_type == "REVERSE"
    assert preview.status == "PREVIEWED"

    assert (
        balance.on_hand_quantity
        == quantity_before
    )
    assert balance.version == version_before

    assert (
        _ledger_count(session)
        == ledger_before
    )
    assert (
        _transaction_count(session)
        == transaction_before + 1
    )

    assert (
        original_row.reversed_transaction_id
        is None
    )


def test_reverse_execute_creates_compensating_ledger_and_preserves_original(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="SUCCESS",
        on_hand="10",
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        delta="5",
        key="reverse-original-success",
    )
    service = InventoryOperationService()

    original_row = session.get(
        InventoryTransaction,
        original.id,
    )

    assert original_row is not None

    original_entry = _original_entry(
        session,
        original.id,
    )

    original_tx_before = (
        _transaction_business_snapshot(
            original_row
        )
    )
    original_entry_before = (
        _entry_snapshot(
            original_entry
        )
    )

    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-success"
        ),
    )

    result = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=_execute_command(
            preview
        ),
        idempotency_key=(
            "reverse-execute-success"
        ),
    )

    session.refresh(balance)
    session.refresh(original_row)
    session.refresh(original_entry)

    assert result.id == preview.transaction_id
    assert result.id != original.id
    assert result.operation_type == "REVERSE"
    assert result.status == "COMPLETED"

    assert len(result.entries) == 1

    compensation = result.entries[0]

    assert (
        compensation.balance_id
        == balance.id
    )

    assert (
        compensation.on_hand_delta
        == Decimal("-5.0000")
    )
    assert (
        compensation.reserved_delta
        == Decimal("0.0000")
    )
    assert (
        compensation.damaged_delta
        == Decimal("0.0000")
    )
    assert (
        compensation.quarantined_delta
        == Decimal("0.0000")
    )
    assert (
        compensation.in_transit_delta
        == Decimal("0.0000")
    )

    assert (
        compensation.state_before_json[
            "on_hand"
        ]
        == "15.0000"
    )
    assert (
        compensation.state_after_json[
            "on_hand"
        ]
        == "10.0000"
    )

    assert (
        balance.on_hand_quantity
        == Decimal("10.0000")
    )

    # Original business facts and immutable original ledger
    # must remain unchanged.
    assert (
        _transaction_business_snapshot(
            original_row
        )
        == original_tx_before
    )

    assert (
        _entry_snapshot(
            original_entry
        )
        == original_entry_before
    )

    # Correlation metadata is allowed to link original -> reverse.
    assert (
        original_row.reversed_transaction_id
        == result.id
    )

    assert (
        _completed_reverse_count(session)
        == 1
    )
    assert _ledger_count(session) == 2


def test_reverse_execute_replay_does_not_append_compensation_twice(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="REPLAY",
        on_hand="10",
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        delta="5",
        key="reverse-original-replay",
    )
    service = InventoryOperationService()

    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-replay"
        ),
    )

    execute_command = _execute_command(
        preview
    )

    first = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command,
        idempotency_key=(
            "reverse-execute-replay"
        ),
    )

    session.refresh(balance)

    quantity_after_first = (
        balance.on_hand_quantity
    )
    version_after_first = balance.version
    ledger_after_first = _ledger_count(
        session
    )
    reverse_count_after_first = (
        _completed_reverse_count(
            session
        )
    )

    replay = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command,
        idempotency_key=(
            "reverse-execute-replay"
        ),
    )

    session.refresh(balance)

    assert replay == first

    assert (
        balance.on_hand_quantity
        == quantity_after_first
    )
    assert (
        balance.version
        == version_after_first
    )

    assert (
        _ledger_count(session)
        == ledger_after_first
    )
    assert (
        _completed_reverse_count(session)
        == reverse_count_after_first
        == 1
    )


def test_reverse_rejects_second_full_reversal(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="REPEAT",
        on_hand="10",
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        delta="5",
        key="reverse-original-repeat",
    )
    service = InventoryOperationService()

    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-first"
        ),
    )

    first = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=_execute_command(
            preview
        ),
        idempotency_key=(
            "reverse-execute-first"
        ),
    )

    assert first.operation_type == "REVERSE"

    session.refresh(balance)

    original_row = session.get(
        InventoryTransaction,
        original.id,
    )

    assert original_row is not None

    session.refresh(original_row)

    quantity_after_first = (
        balance.on_hand_quantity
    )
    version_after_first = balance.version
    ledger_after_first = _ledger_count(
        session
    )

    assert (
        _completed_reverse_count(session)
        == 1
    )

    with pytest.raises(
        ConflictError
    ) as exc_info:
        service.preview_reverse(
            session,
            actor_admin,
            original.id,
            command=(
                _reverse_preview_command_for_row(
                    original_row
                )
            ),
            idempotency_key=(
                "reverse-preview-second"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_OPERATION_STATE_CONFLICT"
    )

    assert (
        exc_info.value.details[
            "conflict_object"
        ]
        == "inventory_transaction"
    )
    assert (
        exc_info.value.details["object_id"]
        == original.id
    )
    assert (
        exc_info.value.details["retryable"]
        is False
    )

    session.refresh(balance)

    assert (
        balance.on_hand_quantity
        == quantity_after_first
    )
    assert (
        balance.version
        == version_after_first
    )
    assert (
        _ledger_count(session)
        == ledger_after_first
    )
    assert (
        _completed_reverse_count(session)
        == 1
    )


def test_reverse_execute_revalidates_negative_compensation_after_preview(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="NEGATIVE",
        on_hand="0",
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        delta="5",
        key="reverse-original-negative",
    )
    service = InventoryOperationService()

    # At preview time reversal is valid: 5 - 5 == 0.
    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-negative"
        ),
    )

    # A later legitimate mutation consumes four units.
    # Execute must not reuse stale preview facts.
    _adjust(
        session,
        actor_admin,
        balance,
        on_hand="-4",
        key="reverse-later-consumption",
        reason=(
            "later inventory consumption fixture"
        ),
    )

    session.refresh(balance)

    assert (
        balance.on_hand_quantity
        == Decimal("1.0000")
    )

    ledger_before_execute = _ledger_count(
        session
    )
    version_before_execute = (
        balance.version
    )

    original_row = session.get(
        InventoryTransaction,
        original.id,
    )

    assert original_row is not None

    with pytest.raises(
        BusinessValidationError
    ) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(
                preview
            ),
            idempotency_key=(
                "reverse-execute-negative"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_NEGATIVE_BALANCE"
    )

    session.refresh(balance)
    session.refresh(original_row)

    assert (
        balance.on_hand_quantity
        == Decimal("1.0000")
    )
    assert (
        balance.version
        == version_before_execute
    )

    # No compensating entry may be written.
    assert (
        _ledger_count(session)
        == ledger_before_execute
    )

    assert (
        original_row.reversed_transaction_id
        is None
    )
    assert (
        _completed_reverse_count(session)
        == 0
    )


@pytest.mark.parametrize(
    (
        "dependency_builder",
        "expected_conflict_object",
        "initial_reserved",
    ),
    [
        (
            _add_reservation_dependency,
            "inventory_reservation",
            "1",
        ),
        (
            _add_transfer_dependency,
            "inventory_transfer",
            "0",
        ),
    ],
)
def test_reverse_execute_rejects_dependency_added_after_preview(
    session,
    actor_admin,
    dependency_builder,
    expected_conflict_object,
    initial_reserved,
) -> None:
    balance = _seed_balance(
        session,
        suffix=(
            expected_conflict_object.upper()
        ),
        on_hand="10",
        reserved=initial_reserved,
    )
    original = _create_original_adjustment(
        session,
        actor_admin,
        balance,
        delta="5",
        key=(
            "reverse-original-"
            + expected_conflict_object
        ),
    )
    service = InventoryOperationService()

    # Preview is valid before downstream business state appears.
    preview = service.preview_reverse(
        session,
        actor_admin,
        original.id,
        command=_reverse_preview_command(
            original
        ),
        idempotency_key=(
            "reverse-preview-dependency-"
            + expected_conflict_object
        ),
    )

    conflict_object, object_id = (
        dependency_builder(
            session,
            actor_admin,
            balance,
        )
    )

    assert (
        conflict_object
        == expected_conflict_object
    )

    session.refresh(balance)

    quantity_before_execute = (
        balance.on_hand_quantity
    )
    version_before_execute = (
        balance.version
    )
    ledger_before_execute = (
        _ledger_count(session)
    )

    original_row = session.get(
        InventoryTransaction,
        original.id,
    )

    assert original_row is not None

    with pytest.raises(
        ConflictError
    ) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(
                preview
            ),
            idempotency_key=(
                "reverse-execute-dependency-"
                + expected_conflict_object
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_OPERATION_STATE_CONFLICT"
    )

    assert (
        exc_info.value.details[
            "conflict_object"
        ]
        == expected_conflict_object
    )

    assert (
        exc_info.value.details["object_id"]
        == object_id
    )

    assert (
        exc_info.value.details["retryable"]
        is False
    )

    session.refresh(balance)
    session.refresh(original_row)

    assert (
        balance.on_hand_quantity
        == quantity_before_execute
    )
    assert (
        balance.version
        == version_before_execute
    )
    assert (
        _ledger_count(session)
        == ledger_before_execute
    )

    assert (
        original_row.reversed_transaction_id
        is None
    )
    assert (
        _completed_reverse_count(session)
        == 0
    )
