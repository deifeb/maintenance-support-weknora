from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository
from app.services.inventory_fefo_service import select_fefo
from app.services.inventory_operation_service import InventoryOperationService
from sqlalchemy import func, select


def _seed_lot_balance(
    session,
    *,
    suffix: str,
) -> tuple[InventoryBalance, InventoryLot]:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-FREEZE-{suffix}",
        name=f"Freeze Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code=f"SP-FREEZE-{suffix}",
        name=f"Freeze Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code=f"LOC-FREEZE-{suffix}",
        name=f"Freeze Location {suffix}",
        location_type="SHELF",
    )
    lot = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=part.id,
        lot_code=f"LOT-FREEZE-{suffix}",
        quality_status="AVAILABLE",
        is_frozen=False,
    )
    session.add_all([location, lot])
    session.flush()

    balance = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=part.id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("5.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()

    return balance, lot


def _freeze_preview_command(
    balance: InventoryBalance,
    lot: InventoryLot,
) -> dict[str, object]:
    return {
        "operation_type": "FREEZE",
        "balance_id": balance.id,
        "expected_balance_version": balance.version,
        "lot_id": lot.id,
        "expected_lot_version": lot.version,
        "reason": "quality hold",
    }


def _execute_command(preview) -> dict[str, object]:
    token = preview.confirmation_token
    assert token is not None

    return {
        "confirmation_token": token,
        "expected_transaction_version": preview.transaction_version,
    }


def _quantity_state(balance: InventoryBalance) -> tuple[Decimal, ...]:
    return (
        balance.on_hand_quantity,
        balance.reserved_quantity,
        balance.damaged_quantity,
        balance.quarantined_quantity,
        balance.in_transit_quantity,
    )


def test_freeze_execute_applies_state_without_quantity_change(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="SUCCESS",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    balance_version_before = balance.version
    lot_version_before = lot.version

    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-success",
    )
    token = preview.confirmation_token
    assert token is not None

    result = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=_execute_command(preview),
        idempotency_key="freeze-execute-success",
    )

    assert result.id == preview.transaction_id
    assert result.operation_type == "FREEZE"
    assert result.status == "COMPLETED"
    assert len(result.entries) == 1

    entry = result.entries[0]
    assert (
        entry.on_hand_delta,
        entry.reserved_delta,
        entry.damaged_delta,
        entry.quarantined_delta,
        entry.in_transit_delta,
    ) == (
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
    )

    assert entry.state_before_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": False,
            "freeze_reason": None,
        }
    ]
    assert entry.state_after_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": True,
            "freeze_reason": "quality hold",
        }
    ]

    session.refresh(balance)
    session.refresh(lot)

    assert _quantity_state(balance) == quantities_before
    assert balance.version == balance_version_before + 1

    assert lot.is_frozen is True
    assert lot.freeze_reason == "quality hold"
    assert lot.version == lot_version_before + 1

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )
    assert transaction is not None
    assert transaction.status == "COMPLETED"
    assert transaction.completed_at is not None

    assert token not in str(transaction.response_snapshot_json)
    assert token not in str(result.model_dump(mode="json"))

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 1


def test_freeze_execute_replay_does_not_apply_state_twice(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="REPLAY",
    )
    service = InventoryOperationService()

    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-replay",
    )
    execute_command = _execute_command(preview)

    first = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command,
        idempotency_key="freeze-execute-replay",
    )

    session.refresh(balance)
    session.refresh(lot)

    balance_version_after_first = balance.version
    lot_version_after_first = lot.version
    transaction_count_after_first = session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    )
    ledger_count_after_first = session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    )

    replay = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command,
        idempotency_key="freeze-execute-replay",
    )

    session.refresh(balance)
    session.refresh(lot)

    assert replay == first
    assert replay.id == preview.transaction_id

    assert balance.version == balance_version_after_first
    assert lot.version == lot_version_after_first
    assert lot.is_frozen is True
    assert lot.freeze_reason == "quality hold"

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_count_after_first == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == ledger_count_after_first == 1

def _unfreeze_preview_command(
    balance: InventoryBalance,
    lot: InventoryLot,
) -> dict[str, object]:
    return {
        "operation_type": "UNFREEZE",
        "balance_id": balance.id,
        "expected_balance_version": balance.version,
        "lot_id": lot.id,
        "expected_lot_version": lot.version,
        "reason": "quality hold cleared",
    }


def _fefo_selection(
    session,
    balance: InventoryBalance,
):
    repository = InventoryLedgerRepository()
    candidates = repository.list_fefo_candidates(
        session,
        "tenant-a",
        spare_part_id=balance.spare_part_id,
        warehouse_id=balance.warehouse_id,
    )
    return select_fefo(
        candidates,
        Decimal("1.0000"),
        as_of=date(2026, 8, 14),
    )


def _assert_zero_quantity_entry(entry) -> None:
    assert (
        entry.on_hand_delta,
        entry.reserved_delta,
        entry.damaged_delta,
        entry.quarantined_delta,
        entry.in_transit_delta,
    ) == (
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
    )


def test_freeze_execute_excludes_balance_from_fefo(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="FEFO-FROZEN",
    )
    service = InventoryOperationService()

    before = _fefo_selection(session, balance)
    assert [line.balance_id for line in before.lines] == [
        balance.id
    ]
    assert before.excluded == ()

    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-fefo",
    )
    service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=_execute_command(preview),
        idempotency_key="freeze-execute-fefo",
    )

    session.refresh(balance)
    session.refresh(lot)

    assert lot.is_frozen is True

    frozen = _fefo_selection(session, balance)

    assert frozen.lines == ()
    assert {
        item.balance_id: item.reason_codes
        for item in frozen.excluded
    } == {
        balance.id: ("LOT_FROZEN",),
    }


def test_unfreeze_execute_restores_fefo_eligibility_without_quantity_change(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="UNFREEZE",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)

    freeze_preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-before-unfreeze",
    )
    service.execute(
        session,
        actor_admin,
        freeze_preview.transaction_id,
        command=_execute_command(freeze_preview),
        idempotency_key="freeze-execute-before-unfreeze",
    )

    session.refresh(balance)
    session.refresh(lot)

    assert lot.is_frozen is True
    assert lot.freeze_reason == "quality hold"

    frozen_selection = _fefo_selection(
        session,
        balance,
    )
    assert frozen_selection.lines == ()
    assert {
        item.balance_id: item.reason_codes
        for item in frozen_selection.excluded
    } == {
        balance.id: ("LOT_FROZEN",),
    }

    balance_version_before_unfreeze = balance.version
    lot_version_before_unfreeze = lot.version

    unfreeze_preview = service.preview(
        session,
        actor_admin,
        command=_unfreeze_preview_command(balance, lot),
        idempotency_key="unfreeze-preview-success",
    )

    result = service.execute(
        session,
        actor_admin,
        unfreeze_preview.transaction_id,
        command=_execute_command(unfreeze_preview),
        idempotency_key="unfreeze-execute-success",
    )

    assert result.id == unfreeze_preview.transaction_id
    assert result.operation_type == "UNFREEZE"
    assert result.status == "COMPLETED"
    assert len(result.entries) == 1

    entry = result.entries[0]
    _assert_zero_quantity_entry(entry)

    assert entry.state_before_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": True,
            "freeze_reason": "quality hold",
        }
    ]
    assert entry.state_after_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": False,
            "freeze_reason": None,
        }
    ]

    session.refresh(balance)
    session.refresh(lot)

    assert _quantity_state(balance) == quantities_before
    assert balance.version == balance_version_before_unfreeze + 1

    assert lot.is_frozen is False
    assert lot.freeze_reason is None
    assert lot.version == lot_version_before_unfreeze + 1

    restored = _fefo_selection(
        session,
        balance,
    )

    assert [line.balance_id for line in restored.lines] == [
        balance.id
    ]
    assert all(
        item.balance_id != balance.id
        for item in restored.excluded
    )

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 2
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 2


def test_unfreeze_execute_replay_does_not_apply_state_twice(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="UNFREEZE-REPLAY",
    )
    service = InventoryOperationService()

    freeze_preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-unfreeze-replay",
    )
    service.execute(
        session,
        actor_admin,
        freeze_preview.transaction_id,
        command=_execute_command(freeze_preview),
        idempotency_key="freeze-execute-unfreeze-replay",
    )

    session.refresh(balance)
    session.refresh(lot)

    unfreeze_preview = service.preview(
        session,
        actor_admin,
        command=_unfreeze_preview_command(balance, lot),
        idempotency_key="unfreeze-preview-replay",
    )
    execute_command = _execute_command(
        unfreeze_preview
    )

    first = service.execute(
        session,
        actor_admin,
        unfreeze_preview.transaction_id,
        command=execute_command,
        idempotency_key="unfreeze-execute-replay",
    )

    session.refresh(balance)
    session.refresh(lot)

    balance_version_after_first = balance.version
    lot_version_after_first = lot.version
    transaction_count_after_first = session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    )
    ledger_count_after_first = session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    )

    replay = service.execute(
        session,
        actor_admin,
        unfreeze_preview.transaction_id,
        command=execute_command,
        idempotency_key="unfreeze-execute-replay",
    )

    session.refresh(balance)
    session.refresh(lot)

    assert replay == first
    assert replay.id == unfreeze_preview.transaction_id

    assert balance.version == balance_version_after_first
    assert lot.version == lot_version_after_first
    assert lot.is_frozen is False
    assert lot.freeze_reason is None

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_count_after_first == 2
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == ledger_count_after_first == 2

    restored = _fefo_selection(
        session,
        balance,
    )
    assert [line.balance_id for line in restored.lines] == [
        balance.id
    ]

def test_freeze_execute_rejects_lot_version_change_after_preview(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="LOT-VERSION-CONFLICT",
    )
    service = InventoryOperationService()

    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-lot-version-conflict",
    )

    expected_lot_version = lot.version
    lot.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="freeze-execute-lot-version-conflict",
        )

    assert exc_info.value.code == "INVENTORY_VERSION_CONFLICT"
    assert exc_info.value.details == {
        "lot_id": lot.id,
        "expected_version": expected_lot_version,
        "actual_version": expected_lot_version + 1,
        "conflict_object": "inventory_lot",
        "retryable": True,
    }

    assert lot.is_frozen is False
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_unfreeze_execute_rejects_already_unfrozen_lot(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(
        session,
        suffix="UNFREEZE-STATE-CONFLICT",
    )
    service = InventoryOperationService()

    preview = service.preview(
        session,
        actor_admin,
        command=_unfreeze_preview_command(balance, lot),
        idempotency_key="unfreeze-preview-state-conflict",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="unfreeze-execute-state-conflict",
        )

    assert (
        exc_info.value.code
        == "INVENTORY_OPERATION_STATE_CONFLICT"
    )
    assert lot.is_frozen is False
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0
