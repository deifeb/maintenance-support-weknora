from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
)
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.services.inventory_operation_service import InventoryOperationService
from sqlalchemy import func, select


def _seed_balance(
    session,
    *,
    suffix: str,
    on_hand: str = "10",
    reserved: str = "0",
    damaged: str = "0",
    quarantined: str = "0",
    in_transit: str = "0",
) -> InventoryBalance:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-ADJ-{suffix}",
        name=f"Adjust Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code=f"SP-ADJ-{suffix}",
        name=f"Adjust Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code=f"LOC-ADJ-{suffix}",
        name=f"Adjust Location {suffix}",
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
        damaged_quantity=Decimal(damaged),
        quarantined_quantity=Decimal(quarantined),
        in_transit_quantity=Decimal(in_transit),
    )
    session.add(balance)
    session.flush()
    return balance


def _adjust_preview_command(
    balance: InventoryBalance,
    *,
    on_hand_delta: str,
    reason: str = "cycle correction",
) -> dict[str, object]:
    return {
        "operation_type": "ADJUST",
        "balance_id": balance.id,
        "expected_balance_version": balance.version,
        "deltas": {
            "on_hand": on_hand_delta,
            "reserved": "0.0000",
            "damaged": "0.0000",
            "quarantined": "0.0000",
            "in_transit": "0.0000",
        },
        "reason": reason,
    }


def _execute_command(preview) -> dict[str, object]:
    return {
        "confirmation_token": preview.confirmation_token,
        "expected_transaction_version": preview.transaction_version,
    }


def _quantity_state(
    balance: InventoryBalance,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    return (
        balance.on_hand_quantity,
        balance.reserved_quantity,
        balance.damaged_quantity,
        balance.quarantined_quantity,
        balance.in_transit_quantity,
    )


def test_adjust_preview_has_no_inventory_or_ledger_side_effects(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="PREVIEW",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    version_before = balance.version

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta="3.0000",
        ),
        idempotency_key="adjust-preview-no-side-effects",
    )

    session.refresh(balance)

    assert preview.operation_type == "ADJUST"
    assert preview.status == "PREVIEWED"
    assert _quantity_state(balance) == quantities_before
    assert balance.version == version_before

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_adjust_preview_requires_admin(
    session,
    actor_contributor,
) -> None:
    balance = _seed_balance(
        session,
        suffix="PREVIEW-RBAC",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    version_before = balance.version

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as exc_info:
        service.preview(
            session,
            actor_contributor,
            command=_adjust_preview_command(
                balance,
                on_hand_delta="1.0000",
            ),
            idempotency_key="adjust-preview-contributor",
        )

    assert exc_info.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"

    session.refresh(balance)

    assert _quantity_state(balance) == quantities_before
    assert balance.version == version_before
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_adjust_execute_requires_admin(
    session,
    actor_admin,
    actor_contributor,
) -> None:
    balance = _seed_balance(
        session,
        suffix="EXECUTE-RBAC",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    version_before = balance.version

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta="1.0000",
        ),
        idempotency_key="adjust-preview-execute-rbac",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as exc_info:
        service.execute(
            session,
            actor_contributor,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="adjust-execute-contributor",
        )

    assert exc_info.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"

    session.refresh(balance)

    assert _quantity_state(balance) == quantities_before
    assert balance.version == version_before
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


@pytest.mark.parametrize(
    ("delta", "expected_on_hand", "suffix"),
    [
        ("3.0000", Decimal("13.0000"), "POSITIVE"),
        ("-3.0000", Decimal("7.0000"), "NEGATIVE"),
    ],
)
def test_adjust_execute_applies_positive_and_negative_delta(
    session,
    actor_admin,
    delta,
    expected_on_hand,
    suffix,
) -> None:
    balance = _seed_balance(
        session,
        suffix=suffix,
        on_hand="10",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    version_before = balance.version

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta=delta,
        ),
        idempotency_key=f"adjust-preview-{suffix.lower()}",
    )

    assert _quantity_state(balance) == quantities_before
    assert balance.version == version_before

    result = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=_execute_command(preview),
        idempotency_key=f"adjust-execute-{suffix.lower()}",
    )

    assert result.id == preview.transaction_id
    assert result.operation_type == "ADJUST"
    assert result.status == "COMPLETED"
    assert len(result.entries) == 1

    entry = result.entries[0]

    assert entry.balance_id == balance.id
    assert entry.on_hand_delta == Decimal(delta)
    assert entry.reserved_delta == Decimal("0.0000")
    assert entry.damaged_delta == Decimal("0.0000")
    assert entry.quarantined_delta == Decimal("0.0000")
    assert entry.in_transit_delta == Decimal("0.0000")
    assert entry.before_balance_version == version_before
    assert entry.resulting_balance_version == version_before + 1

    session.refresh(balance)

    assert balance.on_hand_quantity == expected_on_hand
    assert balance.version == version_before + 1

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 1


def test_adjust_execute_rejects_negative_result_without_mutation(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="NEGATIVE-RESULT",
        on_hand="2",
    )
    service = InventoryOperationService()

    quantities_before = _quantity_state(balance)
    version_before = balance.version

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta="-3.0000",
            reason="invalid negative correction",
        ),
        idempotency_key="adjust-preview-negative-result",
    )

    with pytest.raises(
        BusinessValidationError
    ) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="adjust-execute-negative-result",
        )

    assert exc_info.value.code == "INVENTORY_NEGATIVE_BALANCE"

    session.refresh(balance)

    assert _quantity_state(balance) == quantities_before
    assert balance.version == version_before
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_adjust_execute_rejects_balance_version_change_after_preview(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="VERSION-CONFLICT",
    )
    service = InventoryOperationService()

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta="2.0000",
        ),
        idempotency_key="adjust-preview-version-conflict",
    )

    expected_version = balance.version
    balance.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="adjust-execute-version-conflict",
        )

    assert exc_info.value.code == "INVENTORY_VERSION_CONFLICT"
    assert exc_info.value.details == {
        "balance_id": balance.id,
        "expected_version": expected_version,
        "actual_version": expected_version + 1,
        "conflict_object": "inventory_balance",
        "retryable": True,
    }

    assert balance.on_hand_quantity == Decimal("10.0000")
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_adjust_execute_replay_does_not_apply_delta_twice(
    session,
    actor_admin,
) -> None:
    balance = _seed_balance(
        session,
        suffix="REPLAY",
    )
    service = InventoryOperationService()

    preview = service.preview(
        session,
        actor_admin,
        command=_adjust_preview_command(
            balance,
            on_hand_delta="3.0000",
        ),
        idempotency_key="adjust-preview-replay",
    )
    execute_command = _execute_command(preview)

    first = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command,
        idempotency_key="adjust-execute-replay",
    )

    session.refresh(balance)

    version_after_first = balance.version
    quantity_after_first = balance.on_hand_quantity

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
        idempotency_key="adjust-execute-replay",
    )

    session.refresh(balance)

    assert replay == first
    assert replay.id == preview.transaction_id
    assert balance.on_hand_quantity == quantity_after_first
    assert balance.version == version_after_first

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_count_after_first == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == ledger_count_after_first == 1
