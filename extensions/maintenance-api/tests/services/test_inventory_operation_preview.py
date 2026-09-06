from __future__ import annotations

import hashlib
import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType

import pytest
from app.core.exceptions import AppException, ConflictError
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_ledger import InventoryTransactionRead
from sqlalchemy import func, select


def _operation_service_module() -> ModuleType:
    try:
        return importlib.import_module(
            "app.services.inventory_operation_service"
        )
    except ModuleNotFoundError as exc:
        if exc.name == "app.services.inventory_operation_service":
            pytest.fail(
                "Task 6 requires app.services.inventory_operation_service",
                pytrace=False,
            )
        raise


def _operation_service():
    module = _operation_service_module()
    assert hasattr(
        module,
        "InventoryOperationService",
    ), "Task 6 requires InventoryOperationService"
    return module.InventoryOperationService()


def _seed_lot_balance(
    session,
    *,
    suffix: str,
) -> tuple[InventoryBalance, InventoryLot]:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-PREVIEW-{suffix}",
        name=f"Preview Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code=f"SP-PREVIEW-{suffix}",
        name=f"Preview Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code=f"LOC-PREVIEW-{suffix}",
        name=f"Preview Location {suffix}",
        location_type="SHELF",
    )
    lot = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=part.id,
        lot_code=f"LOT-PREVIEW-{suffix}",
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


def test_inventory_operation_service_exposes_high_risk_contract() -> None:
    module = _operation_service_module()

    assert hasattr(
        module,
        "InventoryOperationService",
    ), "Task 6 requires InventoryOperationService"

    service_type = module.InventoryOperationService

    required_methods = (
        "preview",
        "execute",
        "preview_reverse",
    )
    missing = [
        name
        for name in required_methods
        if not callable(getattr(service_type, name, None))
    ]

    assert not missing, (
        "InventoryOperationService missing Task 6 methods: "
        f"{missing}"
    )


def test_preview_has_no_inventory_side_effects_and_persists_only_token_hash(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="CORE")
    service = _operation_service()
    command = _freeze_preview_command(balance, lot)

    balance_version_before = balance.version
    lot_version_before = lot.version
    on_hand_before = balance.on_hand_quantity

    preview = service.preview(
        session,
        actor_admin,
        command=command,
        idempotency_key="freeze-preview-core",
    )

    assert balance.on_hand_quantity == on_hand_before
    assert balance.version == balance_version_before
    assert lot.is_frozen is False
    assert lot.version == lot_version_before

    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )
    assert transaction is not None
    assert transaction.status == "PREVIEWED"
    assert transaction.operation_type == "FREEZE"
    assert transaction.completed_at is None

    token = preview.confirmation_token
    assert isinstance(token, str)
    assert token

    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert transaction.confirmation_token_hash == expected_hash
    assert transaction.confirmation_token_hash != token
    assert transaction.confirmation_expires_at is not None

    snapshot = transaction.response_snapshot_json
    assert isinstance(snapshot, dict)
    assert token not in str(snapshot)

    extensions = snapshot.get("_extensions")
    assert isinstance(extensions, dict)
    assert extensions.get("preview_command") == command

    public_preview = preview.model_dump(mode="json")
    assert "_extensions" not in public_preview

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1


def test_preview_idempotent_replay_does_not_return_plaintext_token_twice(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="REPLAY")
    service = _operation_service()
    command = _freeze_preview_command(balance, lot)

    first = service.preview(
        session,
        actor_admin,
        command=command,
        idempotency_key="freeze-preview-replay",
    )
    replay = service.preview(
        session,
        actor_admin,
        command=command,
        idempotency_key="freeze-preview-replay",
    )

    assert replay.transaction_id == first.transaction_id
    assert first.confirmation_token
    assert replay.confirmation_token is None

    transaction = session.get(
        InventoryTransaction,
        first.transaction_id,
    )
    assert transaction is not None

    expected_hash = hashlib.sha256(
        first.confirmation_token.encode("utf-8")
    ).hexdigest()
    assert transaction.confirmation_token_hash == expected_hash

    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_public_transaction_read_schema_excludes_private_preview_storage() -> None:
    private_fields = {
        "confirmation_token_hash",
        "confirmation_expires_at",
        "response_snapshot_json",
    }

    assert private_fields.isdisjoint(
        InventoryTransactionRead.model_fields
    )

def _execute_command(
    preview,
    *,
    confirmation_token: str | None = None,
    expected_transaction_version: int | None = None,
) -> dict[str, object]:
    token = (
        preview.confirmation_token
        if confirmation_token is None
        else confirmation_token
    )
    assert token is not None

    return {
        "confirmation_token": token,
        "expected_transaction_version": (
            preview.transaction_version
            if expected_transaction_version is None
            else expected_transaction_version
        ),
    }


def _assert_execute_has_no_inventory_side_effects(
    session,
    *,
    balance: InventoryBalance,
    lot: InventoryLot,
) -> None:
    assert balance.on_hand_quantity == Decimal("5.0000")
    assert balance.reserved_quantity == Decimal("0.0000")
    assert balance.damaged_quantity == Decimal("0.0000")
    assert balance.quarantined_quantity == Decimal("0.0000")
    assert balance.in_transit_quantity == Decimal("0.0000")
    assert lot.is_frozen is False
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_execute_rejects_wrong_confirmation_token_before_inventory_mutation(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="WRONG-TOKEN")
    service = _operation_service()
    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-wrong-token",
    )

    with pytest.raises(AppException):
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(
                preview,
                confirmation_token="definitely-wrong-token",
            ),
            idempotency_key="freeze-execute-wrong-token",
        )

    _assert_execute_has_no_inventory_side_effects(
        session,
        balance=balance,
        lot=lot,
    )


def test_execute_rejects_expired_confirmation_before_inventory_mutation(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="EXPIRED")
    service = _operation_service()
    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-expired",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )
    assert transaction is not None
    transaction.confirmation_expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    session.flush()

    with pytest.raises(AppException):
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="freeze-execute-expired",
        )

    _assert_execute_has_no_inventory_side_effects(
        session,
        balance=balance,
        lot=lot,
    )


def test_execute_rejects_transaction_version_change_before_inventory_mutation(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="TX-VERSION")
    service = _operation_service()
    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-tx-version",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )
    assert transaction is not None
    transaction.version += 1
    session.flush()

    with pytest.raises(ConflictError):
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(
                preview,
                expected_transaction_version=preview.transaction_version,
            ),
            idempotency_key="freeze-execute-tx-version",
        )

    _assert_execute_has_no_inventory_side_effects(
        session,
        balance=balance,
        lot=lot,
    )


def test_execute_rejects_balance_version_change_after_preview(
    session,
    actor_admin,
) -> None:
    balance, lot = _seed_lot_balance(session, suffix="BALANCE-VERSION")
    service = _operation_service()
    preview = service.preview(
        session,
        actor_admin,
        command=_freeze_preview_command(balance, lot),
        idempotency_key="freeze-preview-balance-version",
    )

    balance.version += 1
    session.flush()

    with pytest.raises(ConflictError):
        service.execute(
            session,
            actor_admin,
            preview.transaction_id,
            command=_execute_command(preview),
            idempotency_key="freeze-execute-balance-version",
        )

    _assert_execute_has_no_inventory_side_effects(
        session,
        balance=balance,
        lot=lot,
    )