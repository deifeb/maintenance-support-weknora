from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    InventoryBalance,
    InventoryTransfer,
    InventoryTransferLine,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from sqlalchemy import func, select


def _service_class():
    try:
        module = importlib.import_module(
            "app.services.inventory_transfer_service"
        )
    except ModuleNotFoundError as exc:
        if exc.name == "app.services.inventory_transfer_service":
            pytest.fail(
                "InventoryTransferService is not implemented",
                pytrace=False,
            )
        raise

    service_class = getattr(
        module,
        "InventoryTransferService",
        None,
    )
    if service_class is None:
        pytest.fail(
            "InventoryTransferService is not implemented",
            pytrace=False,
        )
    return service_class


def _seed_locations_and_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    on_hand: str = "10",
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-TR-SVC-{suffix}",
        name=f"Transfer Service Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-TR-SVC-{suffix}",
        name=f"Transfer Service Part {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    source_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"SRC-SVC-{suffix}",
        name=f"Source Service {suffix}",
        location_type="SHELF",
    )
    target_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"DST-SVC-{suffix}",
        name=f"Target Service {suffix}",
        location_type="SHELF",
    )
    session.add_all(
        [source_location, target_location]
    )
    session.flush()

    source_balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=source_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal("0"),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("0"),
    )
    session.add(source_balance)
    session.flush()

    return {
        "warehouse": warehouse,
        "part": part,
        "source_location": source_location,
        "target_location": target_location,
        "source_balance": source_balance,
    }


def _create_command(facts) -> dict[str, object]:
    source = facts["source_balance"]

    return {
        "source_warehouse_id": facts["warehouse"].id,
        "source_location_id": facts["source_location"].id,
        "target_warehouse_id": facts["warehouse"].id,
        "target_location_id": facts["target_location"].id,
        "reference_type": "work_order",
        "reference_id": "WO-TRANSFER-1",
        "reason": "move stock to destination",
        "lines": [
            {
                "spare_part_id": facts["part"].id,
                "source_balance_id": source.id,
                "lot_id": source.lot_id,
                "serial_item_id": None,
                "quantity": "2.0000",
                "expected_source_version": source.version,
            }
        ],
    }


def _count_transfers(session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(
                InventoryTransfer
            )
        )
        or 0
    )


def _target_balances(session, facts):
    return list(
        session.scalars(
            select(InventoryBalance)
            .where(
                InventoryBalance.tenant_id
                == facts["source_balance"].tenant_id,
                InventoryBalance.warehouse_id
                == facts["warehouse"].id,
                InventoryBalance.location_id
                == facts["target_location"].id,
                InventoryBalance.spare_part_id
                == facts["part"].id,
                InventoryBalance.lot_id.is_(None),
            )
            .order_by(InventoryBalance.id)
        )
    )


def test_create_persists_draft_transfer_and_line_versions(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="CREATE",
    )

    service = _service_class()()

    result = service.create(
        session,
        actor_admin,
        command=_create_command(facts),
        idempotency_key="transfer-create-1",
    )

    assert result.tenant_id == actor_admin.tenant_id
    assert result.status == "DRAFT"
    assert result.version == 1
    assert len(result.lines) == 1

    line = result.lines[0]

    assert (
        line.source_balance_id
        == facts["source_balance"].id
    )
    assert line.target_balance_id > 0
    assert (
        line.expected_source_version
        == facts["source_balance"].version
    )
    assert line.expected_target_version == 1
    assert (
        line.requested_quantity
        == Decimal("2.0000")
    )
    assert (
        line.dispatched_quantity
        == Decimal("0.0000")
    )
    assert (
        line.received_quantity
        == Decimal("0.0000")
    )


def test_create_resolves_missing_target_to_zero_balance(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="TARGETZERO",
    )

    assert _target_balances(session, facts) == []

    service = _service_class()()

    result = service.create(
        session,
        actor_admin,
        command=_create_command(facts),
        idempotency_key="transfer-target-zero",
    )

    targets = _target_balances(
        session,
        facts,
    )

    assert len(targets) == 1

    target = targets[0]

    assert result.lines[0].target_balance_id == target.id
    assert target.on_hand_quantity == Decimal("0.0000")
    assert target.reserved_quantity == Decimal("0.0000")
    assert target.damaged_quantity == Decimal("0.0000")
    assert (
        target.quarantined_quantity
        == Decimal("0.0000")
    )
    assert (
        target.in_transit_quantity
        == Decimal("0.0000")
    )


def test_create_reuses_single_target_identity_winner(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="WINNER",
    )

    service = _service_class()()

    first = service.create(
        session,
        actor_admin,
        command=_create_command(facts),
        idempotency_key="transfer-winner-1",
    )
    second = service.create(
        session,
        actor_admin,
        command={
            **_create_command(facts),
            "reference_id": "WO-TRANSFER-2",
        },
        idempotency_key="transfer-winner-2",
    )

    targets = _target_balances(
        session,
        facts,
    )

    assert len(targets) == 1
    assert (
        first.lines[0].target_balance_id
        == second.lines[0].target_balance_id
        == targets[0].id
    )


def test_create_same_key_same_command_replays_without_duplicate(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="REPLAY",
    )
    command = _create_command(facts)
    service = _service_class()()

    first = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key="transfer-create-replay",
    )

    transfer_count = _count_transfers(session)

    replay = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key="transfer-create-replay",
    )

    assert replay == first
    assert _count_transfers(session) == transfer_count
    assert len(_target_balances(session, facts)) == 1


def test_create_same_key_changed_command_is_rejected(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="IDEMPOTENCY",
    )
    service = _service_class()()

    service.create(
        session,
        actor_admin,
        command=_create_command(facts),
        idempotency_key="transfer-create-conflict",
    )

    changed = {
        **_create_command(facts),
        "reason": "different command",
    }

    with pytest.raises(ConflictError) as exc_info:
        service.create(
            session,
            actor_admin,
            command=changed,
            idempotency_key="transfer-create-conflict",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_create_rejects_same_source_and_target_location(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="SAMELOC",
    )
    service = _service_class()()

    command = _create_command(facts)
    command["target_location_id"] = (
        facts["source_location"].id
    )

    with pytest.raises(
        BusinessValidationError
    ) as exc_info:
        service.create(
            session,
            actor_admin,
            command=command,
            idempotency_key="transfer-same-location",
        )

    assert (
        exc_info.value.code
        == "TRANSFER_STATE_CONFLICT"
    )


def test_create_hides_cross_tenant_source_balance(
    session,
    actor_admin,
) -> None:
    local = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="LOCAL",
    )
    foreign = _seed_locations_and_balance(
        session,
        tenant_id="tenant-b",
        suffix="FOREIGN",
    )

    service = _service_class()()

    command = _create_command(local)
    command["lines"][0]["source_balance_id"] = (
        foreign["source_balance"].id
    )
    command["lines"][0]["spare_part_id"] = (
        foreign["part"].id
    )

    with pytest.raises(NotFoundError):
        service.create(
            session,
            actor_admin,
            command=command,
            idempotency_key="transfer-cross-tenant",
        )

    assert _count_transfers(session) == 0


def test_serial_transfer_contract_requires_audited_relocation(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="SERIAL",
        on_hand="1",
    )

    serial_item = SerializedItem(
        tenant_id=actor_admin.tenant_id,
        spare_part_id=facts["part"].id,
        serial_number="SERIAL-TRANSFER-001",
        warehouse_id=facts["warehouse"].id,
        location_id=facts["source_location"].id,
        status="IN_STOCK",
    )
    session.add(serial_item)
    session.flush()

    command = _create_command(facts)
    command["lines"][0]["quantity"] = "1.0000"
    command["lines"][0]["serial_item_id"] = serial_item.id

    service = _service_class()()

    transfer = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key="serial-transfer-create",
    )

    dispatch_preview = service.preview_dispatch(
        session,
        actor_admin,
        transfer.id,
        command={
            "expected_version": transfer.version,
        },
        idempotency_key="serial-dispatch-preview",
    )

    dispatched = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command={
                        "transaction_id": dispatch_preview.transaction_id,
"confirmation_token": (
                dispatch_preview.confirmation_token
            ),
            "expected_transaction_version": (
                dispatch_preview.transaction_version
            ),
        },
        idempotency_key="serial-dispatch-execute",
    )

    receive_preview = service.preview_receive(
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
                    "quantity": "1.0000",
                }
            ],
        },
        idempotency_key="serial-receive-preview",
    )

    completed = service.execute_receive(
        session,
        actor_admin,
        dispatched.id,
        command={
            "transaction_id": receive_preview.transaction_id,
            "confirmation_token": (
                receive_preview.confirmation_token
            ),
            "expected_transaction_version": (
                receive_preview.transaction_version
            ),
        },
        idempotency_key="serial-receive-execute",
    )

    session.refresh(serial_item)

    assert completed.status == "COMPLETED"
    assert (
        serial_item.warehouse_id
        == facts["warehouse"].id
    )
    assert (
        serial_item.location_id
        == facts["target_location"].id
    )
    assert serial_item.status == "IN_STOCK"

    target = session.get(
        InventoryBalance,
        completed.lines[0].target_balance_id,
    )
    assert target is not None
    assert target.on_hand_quantity == Decimal("1.0000")


def test_create_does_not_mutate_inventory_quantities(
    session,
    actor_admin,
) -> None:
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="NOSIDEEFFECT",
    )

    source = facts["source_balance"]
    source_quantity = source.on_hand_quantity
    source_version = source.version

    service = _service_class()()

    result = service.create(
        session,
        actor_admin,
        command=_create_command(facts),
        idempotency_key="transfer-create-no-side-effect",
    )

    session.refresh(source)

    target = session.get(
        InventoryBalance,
        result.lines[0].target_balance_id,
    )
    assert target is not None

    assert source.on_hand_quantity == source_quantity
    assert source.version == source_version
    assert target.on_hand_quantity == Decimal("0.0000")
    assert target.in_transit_quantity == Decimal("0.0000")

    persisted_line = session.scalar(
        select(InventoryTransferLine).where(
            InventoryTransferLine.transfer_id
            == result.id
        )
    )
    assert persisted_line is not None

# TASK 7 RED SLICE 2 DISPATCH CONTRACTS


def _dispatch_fixture(
    session,
    actor_admin,
    *,
    suffix: str,
    quantity: str = "2.0000",
    on_hand: str = "10",
):
    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix=f"DISPATCH-{suffix}",
        on_hand=on_hand,
    )

    command = _create_command(facts)
    command["lines"][0]["quantity"] = quantity
    command["reference_id"] = f"WO-DISPATCH-{suffix}"

    service = _service_class()()

    transfer = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key=f"dispatch-create-{suffix}",
    )

    source = session.get(
        InventoryBalance,
        transfer.lines[0].source_balance_id,
    )
    target = session.get(
        InventoryBalance,
        transfer.lines[0].target_balance_id,
    )

    assert source is not None
    assert target is not None

    return service, transfer, facts, source, target


def _dispatch_preview(
    service,
    session,
    actor,
    transfer,
    *,
    key: str,
):
    return service.preview_dispatch(
        session,
        actor,
        transfer.id,
        command={
            "expected_version": transfer.version,
        },
        idempotency_key=key,
    )


def _dispatch_execute_command(
    preview,
    *,
    token: str | None = None,
    transaction_version: int | None = None,
):
    return {
        "transaction_id": preview.transaction_id,
        "confirmation_token": (
            preview.confirmation_token
            if token is None
            else token
        ),
        "expected_transaction_version": (
            preview.transaction_version
            if transaction_version is None
            else transaction_version
        ),
    }


def _inventory_quantities(balance):
    return (
        balance.on_hand_quantity,
        balance.reserved_quantity,
        balance.damaged_quantity,
        balance.quarantined_quantity,
        balance.in_transit_quantity,
        balance.version,
    )


def _ledger_count(session) -> int:
    from app.models import InventoryLedgerEntry

    return int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )


def _manual_dispatch_preview_transaction(
    session,
    actor,
    transfer,
    *,
    token: str = "manual-dispatch-confirmation-token",
    expired: bool = False,
):
    import hashlib
    from datetime import timedelta

    from app.models.mixins import utc_now
    from app.repositories.inventory_transaction_repository import (
        InventoryTransactionRepository,
    )
    from app.services.snapshot_service import snapshot_service

    lines = list(transfer.lines)

    if not lines:
        from app.models import InventoryTransferLine

        lines = list(
            session.scalars(
                select(InventoryTransferLine)
                .where(
                    InventoryTransferLine.tenant_id
                    == actor.tenant_id,
                    InventoryTransferLine.transfer_id
                    == transfer.id,
                )
                .order_by(InventoryTransferLine.id)
            )
        )

    preview_command = {
        "expected_version": transfer.version,
        "lines": [
            {
                "transfer_line_id": line.id,
                "quantity": format(
                    line.requested_quantity,
                    ".4f",
                ),
                "expected_source_version": (
                    line.expected_source_version
                ),
                "expected_target_version": (
                    line.expected_target_version
                ),
                "serial_item_id": line.serial_item_id,
            }
            for line in lines
        ],
    }

    repository = InventoryTransactionRepository()

    transaction = repository.create_transaction(
        session,
        actor=actor,
        operation_type="TRANSFER_DISPATCH",
        idempotency_key=(
            f"manual-dispatch-preview-{transfer.id}"
        ),
        request_hash=snapshot_service.canonical_hash(
            preview_command
        ),
        reason="dispatch inventory transfer",
        status="PREVIEWED",
        reference_type="INVENTORY_TRANSFER",
        reference_id=str(transfer.id),
    )

    transaction.confirmation_token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    if expired:
        transaction.confirmation_expires_at = (
            utc_now() - timedelta(minutes=1)
        )
    else:
        transaction.confirmation_expires_at = (
            utc_now() + timedelta(minutes=15)
        )

    transaction.response_snapshot_json = {
        "transaction_id": transaction.id,
        "operation_type": "TRANSFER_DISPATCH",
        "status": "PREVIEWED",
        "transaction_version": transaction.version,
        "confirmation_token": None,
        "confirmation_expires_at": (
            transaction.confirmation_expires_at.isoformat()
        ),
        "_extensions": {
            "preview_command": preview_command,
        },
    }

    session.flush()

    return transaction, token


def test_dispatch_preview_has_no_inventory_or_ledger_side_effect(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-NO-SIDE-EFFECT",
    )

    source_before = _inventory_quantities(source)
    target_before = _inventory_quantities(target)
    ledger_before = _ledger_count(session)

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-no-side-effect",
    )

    session.refresh(source)
    session.refresh(target)

    assert preview.operation_type == "TRANSFER_DISPATCH"
    assert _inventory_quantities(source) == source_before
    assert _inventory_quantities(target) == target_before
    assert _ledger_count(session) == ledger_before


def test_dispatch_preview_persists_previewed_transaction_and_token(
    session,
    actor_admin,
) -> None:
    from app.models import InventoryTransaction

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-TX",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-tx",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )

    assert transaction is not None
    assert transaction.tenant_id == actor_admin.tenant_id
    assert transaction.operation_type == "TRANSFER_DISPATCH"
    assert transaction.status == "PREVIEWED"
    assert transaction.reference_type == "INVENTORY_TRANSFER"
    assert transaction.reference_id == str(transfer.id)

    assert preview.confirmation_token
    assert transaction.confirmation_token_hash
    assert (
        transaction.confirmation_token_hash
        != preview.confirmation_token
    )


def test_dispatch_preview_replay_returns_token_only_once(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-REPLAY",
    )

    first = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-replay",
    )

    replay = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-replay",
    )

    assert replay.transaction_id == first.transaction_id
    assert first.confirmation_token
    assert replay.confirmation_token is None


def test_dispatch_preview_rejects_transfer_version_conflict(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="TRANSFER-VERSION",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.preview_dispatch(
            session,
            actor_admin,
            transfer.id,
            command={
                "expected_version": transfer.version + 1,
            },
            idempotency_key=(
                "dispatch-preview-transfer-version"
            ),
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_dispatch_execute_rejects_wrong_confirmation_token(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="WRONG-TOKEN",
    )

    transaction, _ = _manual_dispatch_preview_transaction(
        session,
        actor_admin,
        transfer,
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": "wrong-token",
                "expected_transaction_version": (
                    transaction.version
                ),
            },
            idempotency_key="dispatch-execute-wrong-token",
        )

    assert (
        exc_info.value.code
        == "INVENTORY_CONFIRMATION_TOKEN_INVALID"
    )


def test_dispatch_execute_rejects_expired_confirmation(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="EXPIRED-TOKEN",
    )

    transaction, token = (
        _manual_dispatch_preview_transaction(
            session,
            actor_admin,
            transfer,
            expired=True,
        )
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": token,
                "expected_transaction_version": (
                    transaction.version
                ),
            },
            idempotency_key=(
                "dispatch-execute-expired-token"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_CONFIRMATION_EXPIRED"
    )


def test_dispatch_execute_rejects_transaction_version_conflict(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="TX-VERSION",
    )

    transaction, token = (
        _manual_dispatch_preview_transaction(
            session,
            actor_admin,
            transfer,
        )
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": token,
                "expected_transaction_version": (
                    transaction.version + 1
                ),
            },
            idempotency_key=(
                "dispatch-execute-tx-version"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_TRANSACTION_VERSION_CONFLICT"
    )


def test_dispatch_execute_revalidates_transfer_state(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="STATE-REVALIDATE",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-state-revalidate",
    )

    from app.models import InventoryTransfer

    persisted_transfer = session.get(
        InventoryTransfer,
        transfer.id,
    )
    assert persisted_transfer is not None

    persisted_transfer.status = "CANCELLED"
    persisted_transfer.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            persisted_transfer.id,
            command=_dispatch_execute_command(preview),
            idempotency_key=(
                "dispatch-execute-state-revalidate"
            ),
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_dispatch_execute_revalidates_source_balance_version(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="SOURCE-VERSION",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-source-version",
    )

    source.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command=_dispatch_execute_command(preview),
            idempotency_key=(
                "dispatch-execute-source-version"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_VERSION_CONFLICT"
    )


def test_dispatch_execute_revalidates_target_balance_version(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="TARGET-VERSION",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-target-version",
    )

    target.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command=_dispatch_execute_command(preview),
            idempotency_key=(
                "dispatch-execute-target-version"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_VERSION_CONFLICT"
    )


def test_dispatch_execute_atomically_moves_source_to_target_transit(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="ATOMIC",
        quantity="2.0000",
        on_hand="10",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-atomic",
    )

    result = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=_dispatch_execute_command(preview),
        idempotency_key="dispatch-execute-atomic",
    )

    session.refresh(source)
    session.refresh(target)

    assert source.on_hand_quantity == Decimal("8.0000")
    assert target.in_transit_quantity == Decimal("2.0000")

    assert result.status == "DISPATCHED"
    assert (
        result.lines[0].dispatched_quantity
        == Decimal("2.0000")
    )
    assert (
        result.lines[0].received_quantity
        == Decimal("0.0000")
    )


def test_dispatch_execute_writes_both_ledger_entries_in_one_transaction(
    session,
    actor_admin,
) -> None:
    from app.models import (
        InventoryLedgerEntry,
        InventoryTransaction,
    )

    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="LEDGER",
        quantity="2.0000",
        on_hand="10",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-ledger",
    )

    service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=_dispatch_execute_command(preview),
        idempotency_key="dispatch-execute-ledger",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )

    assert transaction is not None
    assert transaction.status == "COMPLETED"

    entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.transaction_id
                == transaction.id
            )
            .order_by(InventoryLedgerEntry.balance_id)
        )
    )

    assert len(entries) == 2
    assert {
        entry.transaction_id
        for entry in entries
    } == {transaction.id}

    by_balance = {
        entry.balance_id: entry
        for entry in entries
    }

    assert (
        by_balance[source.id].on_hand_delta
        == Decimal("-2.0000")
    )
    assert (
        by_balance[source.id].in_transit_delta
        == Decimal("0.0000")
    )

    assert (
        by_balance[target.id].on_hand_delta
        == Decimal("0.0000")
    )
    assert (
        by_balance[target.id].in_transit_delta
        == Decimal("2.0000")
    )


def test_dispatch_insufficient_source_leaves_no_one_sided_target_effect(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="INSUFFICIENT",
        quantity="12.0000",
        on_hand="10",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-insufficient",
    )

    source_before = _inventory_quantities(source)
    target_before = _inventory_quantities(target)
    ledger_before = _ledger_count(session)

    with pytest.raises(
        BusinessValidationError
    ) as exc_info:
        service.execute_dispatch(
            session,
            actor_admin,
            transfer.id,
            command=_dispatch_execute_command(preview),
            idempotency_key=(
                "dispatch-execute-insufficient"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_NEGATIVE_BALANCE"
    )

    session.refresh(source)
    session.refresh(target)

    assert _inventory_quantities(source) == source_before
    assert _inventory_quantities(target) == target_before
    assert _ledger_count(session) == ledger_before


def test_dispatch_execute_replay_does_not_double_move_inventory(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="EXECUTE-REPLAY",
        quantity="2.0000",
        on_hand="10",
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-preview-execute-replay",
    )

    execute_command = _dispatch_execute_command(
        preview
    )

    first = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=execute_command,
        idempotency_key=(
            "dispatch-execute-replay"
        ),
    )

    session.refresh(source)
    session.refresh(target)

    source_after_first = _inventory_quantities(
        source
    )
    target_after_first = _inventory_quantities(
        target
    )
    ledger_after_first = _ledger_count(session)

    replay = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=execute_command,
        idempotency_key=(
            "dispatch-execute-replay"
        ),
    )

    session.refresh(source)
    session.refresh(target)

    assert replay == first
    assert (
        _inventory_quantities(source)
        == source_after_first
    )
    assert (
        _inventory_quantities(target)
        == target_after_first
    )
    assert _ledger_count(session) == ledger_after_first


def test_dispatch_preview_hides_cross_tenant_transfer(
    session,
    actor_admin,
) -> None:
    from app.security.actor import (
        ActorContext,
        MaintenanceRole,
    )

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="TENANT-HIDDEN",
    )

    foreign_actor = ActorContext(
        user_id="foreign-user",
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
        request_id="foreign-request",
        token_id="foreign-token",
    )

    with pytest.raises(NotFoundError):
        service.preview_dispatch(
            session,
            foreign_actor,
            transfer.id,
            command={
                "expected_version": transfer.version,
            },
            idempotency_key=(
                "dispatch-preview-foreign-tenant"
            ),
        )


def test_dispatch_preview_rejects_non_draft_transfer(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="NON-DRAFT",
    )

    from app.models import InventoryTransfer

    persisted_transfer = session.get(
        InventoryTransfer,
        transfer.id,
    )
    assert persisted_transfer is not None

    persisted_transfer.status = "CANCELLED"
    persisted_transfer.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.preview_dispatch(
            session,
            actor_admin,
            persisted_transfer.id,
            command={
                "expected_version": persisted_transfer.version,
            },
            idempotency_key=(
                "dispatch-preview-non-draft"
            ),
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_dispatch_serial_preview_preserves_serial_identity_in_audit_command(
    session,
    actor_admin,
) -> None:
    from app.models import InventoryTransaction

    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix="DISPATCH-SERIAL-AUDIT",
        on_hand="1",
    )

    serial_item = SerializedItem(
        tenant_id=actor_admin.tenant_id,
        spare_part_id=facts["part"].id,
        serial_number="SERIAL-DISPATCH-AUDIT-001",
        warehouse_id=facts["warehouse"].id,
        location_id=facts["source_location"].id,
        status="IN_STOCK",
    )
    session.add(serial_item)
    session.flush()

    command = _create_command(facts)
    command["reference_id"] = "WO-DISPATCH-SERIAL"
    command["lines"][0]["quantity"] = "1.0000"
    command["lines"][0]["serial_item_id"] = (
        serial_item.id
    )

    service = _service_class()()

    transfer = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key=(
            "dispatch-serial-create"
        ),
    )

    preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key="dispatch-serial-preview",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )

    assert transaction is not None
    assert isinstance(
        transaction.response_snapshot_json,
        dict,
    )

    extensions = transaction.response_snapshot_json[
        "_extensions"
    ]
    preview_command = extensions["preview_command"]

    assert (
        preview_command["lines"][0][
            "serial_item_id"
        ]
        == serial_item.id
    )

# TASK 7 RED SLICE 3 RECEIVE CONTRACTS


def _receive_fixture(
    session,
    actor_admin,
    *,
    suffix: str,
    quantity: str = "4.0000",
    on_hand: str = "10",
):
    (
        service,
        transfer,
        facts,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix=f"RECEIVE-{suffix}",
        quantity=quantity,
        on_hand=on_hand,
    )

    dispatch_preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key=f"receive-dispatch-preview-{suffix}",
    )

    dispatched = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=_dispatch_execute_command(
            dispatch_preview
        ),
        idempotency_key=(
            f"receive-dispatch-execute-{suffix}"
        ),
    )

    session.refresh(source)
    session.refresh(target)

    return (
        service,
        dispatched,
        facts,
        source,
        target,
    )


def _receive_preview(
    service,
    session,
    actor,
    transfer,
    *,
    quantity: str,
    key: str,
):
    return service.preview_receive(
        session,
        actor,
        transfer.id,
        command={
            "expected_version": transfer.version,
            "lines": [
                {
                    "transfer_line_id": (
                        transfer.lines[0].id
                    ),
                    "quantity": quantity,
                }
            ],
        },
        idempotency_key=key,
    )


def _receive_execute_command(
    preview,
    *,
    token: str | None = None,
    transaction_version: int | None = None,
):
    return {
        "transaction_id": preview.transaction_id,
        "confirmation_token": (
            preview.confirmation_token
            if token is None
            else token
        ),
        "expected_transaction_version": (
            preview.transaction_version
            if transaction_version is None
            else transaction_version
        ),
    }


def _manual_receive_preview_transaction(
    session,
    actor,
    transfer,
    *,
    quantity: str,
    key: str,
    token: str = "manual-receive-confirmation-token",
    expired: bool = False,
):
    import hashlib
    from datetime import timedelta

    from app.models.mixins import utc_now
    from app.repositories.inventory_transaction_repository import (
        InventoryTransactionRepository,
    )
    from app.services.snapshot_service import (
        snapshot_service,
    )

    line = transfer.lines[0]

    target = session.get(
        InventoryBalance,
        line.target_balance_id,
    )
    assert target is not None

    session.refresh(target)

    private_command = {
        "operation_type": "TRANSFER_RECEIVE",
        "transfer_id": transfer.id,
        "expected_transfer_version": (
            transfer.version
        ),
        "reason": "receive inventory transfer",
        "lines": [
            {
                "transfer_line_id": line.id,
                "quantity": quantity,
                "target_balance_id": target.id,
                "expected_target_version": (
                    target.version
                ),
                "serial_item_id": (
                    line.serial_item_id
                ),
            }
        ],
    }

    repository = InventoryTransactionRepository()

    transaction = repository.create_transaction(
        session,
        actor=actor,
        operation_type="TRANSFER_RECEIVE",
        idempotency_key=(
            f"manual-receive-preview-{key}"
        ),
        request_hash=(
            snapshot_service.canonical_hash(
                private_command
            )
        ),
        reason="receive inventory transfer",
        status="PREVIEWED",
        reference_type="INVENTORY_TRANSFER",
        reference_id=str(transfer.id),
    )

    transaction.confirmation_token_hash = (
        hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()
    )

    if expired:
        transaction.confirmation_expires_at = (
            utc_now() - timedelta(minutes=1)
        )

    if not expired:
        transaction.confirmation_expires_at = (
            utc_now() + timedelta(minutes=15)
        )

    transaction.response_snapshot_json = {
        "transaction_id": transaction.id,
        "operation_type": "TRANSFER_RECEIVE",
        "status": "PREVIEWED",
        "transaction_version": transaction.version,
        "confirmation_token": None,
        "confirmation_expires_at": (
            transaction
            .confirmation_expires_at
            .isoformat()
        ),
        "_extensions": {
            "preview_command": private_command,
        },
    }

    session.flush()

    return transaction, token


def _serial_cross_warehouse_receive_fixture(
    session,
    actor_admin,
    *,
    suffix: str,
):
    from app.models import (
        Warehouse,
        WarehouseLocation,
    )

    facts = _seed_locations_and_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix=f"SERIAL-RECEIVE-{suffix}",
        on_hand="1",
    )

    target_warehouse = Warehouse(
        tenant_id=actor_admin.tenant_id,
        code=f"WH-SERIAL-TARGET-{suffix}",
        name=f"Serial Target Warehouse {suffix}",
    )
    session.add(target_warehouse)
    session.flush()

    target_location = WarehouseLocation(
        tenant_id=actor_admin.tenant_id,
        warehouse_id=target_warehouse.id,
        code=f"LOC-SERIAL-TARGET-{suffix}",
        name=f"Serial Target Location {suffix}",
        location_type="SHELF",
    )
    session.add(target_location)
    session.flush()

    serial_item = SerializedItem(
        tenant_id=actor_admin.tenant_id,
        spare_part_id=facts["part"].id,
        serial_number=(
            f"SERIAL-RECEIVE-{suffix}"
        ),
        warehouse_id=facts["warehouse"].id,
        location_id=(
            facts["source_location"].id
        ),
        status="IN_STOCK",
    )
    session.add(serial_item)
    session.flush()

    command = _create_command(facts)

    command["target_warehouse_id"] = (
        target_warehouse.id
    )
    command["target_location_id"] = (
        target_location.id
    )
    command["reference_id"] = (
        f"WO-SERIAL-RECEIVE-{suffix}"
    )
    command["lines"][0]["quantity"] = "1.0000"
    command["lines"][0]["serial_item_id"] = (
        serial_item.id
    )

    service = _service_class()()

    transfer = service.create(
        session,
        actor_admin,
        command=command,
        idempotency_key=(
            f"serial-receive-create-{suffix}"
        ),
    )

    dispatch_preview = _dispatch_preview(
        service,
        session,
        actor_admin,
        transfer,
        key=(
            f"serial-receive-dispatch-preview-{suffix}"
        ),
    )

    dispatched = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=_dispatch_execute_command(
            dispatch_preview
        ),
        idempotency_key=(
            f"serial-receive-dispatch-execute-{suffix}"
        ),
    )

    session.refresh(serial_item)

    target_balance = session.get(
        InventoryBalance,
        dispatched.lines[0].target_balance_id,
    )
    assert target_balance is not None

    return (
        service,
        dispatched,
        facts,
        serial_item,
        target_warehouse,
        target_location,
        target_balance,
    )


def test_receive_preview_has_no_inventory_or_ledger_side_effect(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-NO-SIDE-EFFECT",
    )

    source_before = _inventory_quantities(
        source
    )
    target_before = _inventory_quantities(
        target
    )
    ledger_before = _ledger_count(
        session
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-no-side-effect",
    )

    session.refresh(source)
    session.refresh(target)

    assert preview.operation_type == "TRANSFER_RECEIVE"
    assert (
        _inventory_quantities(source)
        == source_before
    )
    assert (
        _inventory_quantities(target)
        == target_before
    )
    assert _ledger_count(session) == ledger_before


def test_receive_preview_persists_previewed_transaction_and_token(
    session,
    actor_admin,
) -> None:
    from app.models import InventoryTransaction

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-TX",
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-tx",
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )

    assert transaction is not None
    assert transaction.tenant_id == actor_admin.tenant_id
    assert transaction.operation_type == "TRANSFER_RECEIVE"
    assert transaction.status == "PREVIEWED"
    assert transaction.reference_type == "INVENTORY_TRANSFER"
    assert transaction.reference_id == str(transfer.id)

    assert preview.confirmation_token
    assert transaction.confirmation_token_hash
    assert (
        transaction.confirmation_token_hash
        != preview.confirmation_token
    )


def test_receive_preview_replay_returns_token_only_once(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="PREVIEW-REPLAY",
    )

    first = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-replay",
    )

    replay = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-replay",
    )

    assert replay.transaction_id == first.transaction_id
    assert first.confirmation_token
    assert replay.confirmation_token is None


def test_receive_preview_rejects_draft_transfer(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="RECEIVE-DRAFT",
        quantity="2.0000",
        on_hand="10",
    )

    with pytest.raises(ConflictError) as exc_info:
        _receive_preview(
            service,
            session,
            actor_admin,
            transfer,
            quantity="1.0000",
            key="receive-preview-draft",
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_receive_preview_rejects_completed_transfer(
    session,
    actor_admin,
) -> None:
    from app.models import InventoryTransfer

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="COMPLETED",
    )

    persisted = session.get(
        InventoryTransfer,
        transfer.id,
    )
    assert persisted is not None

    persisted.status = "COMPLETED"
    persisted.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.preview_receive(
            session,
            actor_admin,
            persisted.id,
            command={
                "expected_version": persisted.version,
                "lines": [
                    {
                        "transfer_line_id": (
                            transfer.lines[0].id
                        ),
                        "quantity": "1.0000",
                    }
                ],
            },
            idempotency_key=(
                "receive-preview-completed"
            ),
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_receive_preview_rejects_transfer_version_conflict(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="TRANSFER-VERSION",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.preview_receive(
            session,
            actor_admin,
            transfer.id,
            command={
                "expected_version": (
                    transfer.version + 1
                ),
                "lines": [
                    {
                        "transfer_line_id": (
                            transfer.lines[0].id
                        ),
                        "quantity": "1.0000",
                    }
                ],
            },
            idempotency_key=(
                "receive-preview-transfer-version"
            ),
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"


def test_receive_preview_rejects_over_receive(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="OVER-RECEIVE",
        quantity="2.0000",
    )

    with pytest.raises(ConflictError) as exc_info:
        _receive_preview(
            service,
            session,
            actor_admin,
            transfer,
            quantity="3.0000",
            key="receive-preview-over",
        )

    assert (
        exc_info.value.code
        == "TRANSFER_RECEIPT_EXCEEDS_DISPATCH"
    )


def test_receive_preview_hides_cross_tenant_transfer(
    session,
    actor_admin,
) -> None:
    from app.security.actor import (
        ActorContext,
        MaintenanceRole,
    )

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="TENANT-HIDDEN",
    )

    foreign_actor = ActorContext(
        user_id="foreign-user",
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
        request_id="foreign-request",
        token_id="foreign-token",
    )

    with pytest.raises(NotFoundError):
        _receive_preview(
            service,
            session,
            foreign_actor,
            transfer,
            quantity="1.0000",
            key="receive-preview-foreign",
        )


def test_receive_execute_rejects_wrong_confirmation_token(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="WRONG-TOKEN",
    )

    transaction, _ = (
        _manual_receive_preview_transaction(
            session,
            actor_admin,
            transfer,
            quantity="1.0000",
            key="wrong-token",
        )
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_receive(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": "wrong-token",
                "expected_transaction_version": (
                    transaction.version
                ),
            },
            idempotency_key=(
                "receive-execute-wrong-token"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_CONFIRMATION_TOKEN_INVALID"
    )


def test_receive_execute_rejects_expired_confirmation(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="EXPIRED",
    )

    transaction, token = (
        _manual_receive_preview_transaction(
            session,
            actor_admin,
            transfer,
            quantity="1.0000",
            key="expired",
            expired=True,
        )
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_receive(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": token,
                "expected_transaction_version": (
                    transaction.version
                ),
            },
            idempotency_key=(
                "receive-execute-expired"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_CONFIRMATION_EXPIRED"
    )


def test_receive_execute_rejects_transaction_version_conflict(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="TX-VERSION",
    )

    transaction, token = (
        _manual_receive_preview_transaction(
            session,
            actor_admin,
            transfer,
            quantity="1.0000",
            key="tx-version",
        )
    )

    with pytest.raises(ConflictError) as exc_info:
        service.execute_receive(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": token,
                "expected_transaction_version": (
                    transaction.version + 1
                ),
            },
            idempotency_key=(
                "receive-execute-tx-version"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_TRANSACTION_VERSION_CONFLICT"
    )


def test_receive_execute_revalidates_target_balance_version(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="TARGET-VERSION",
    )

    transaction, token = (
        _manual_receive_preview_transaction(
            session,
            actor_admin,
            transfer,
            quantity="1.0000",
            key="target-version",
        )
    )

    target.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_receive(
            session,
            actor_admin,
            transfer.id,
            command={
                "transaction_id": transaction.id,
                "confirmation_token": token,
                "expected_transaction_version": (
                    transaction.version
                ),
            },
            idempotency_key=(
                "receive-execute-target-version"
            ),
        )

    assert (
        exc_info.value.code
        == "INVENTORY_VERSION_CONFLICT"
    )


def test_receive_partial_moves_transit_to_on_hand_and_updates_status(
    session,
    actor_admin,
) -> None:
    from app.models import (
        InventoryLedgerEntry,
        InventoryTransaction,
    )
    from sqlalchemy import select

    (
        service,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="PARTIAL",
        quantity="4.0000",
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.5000",
        key="receive-preview-partial",
    )

    result = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=_receive_execute_command(
            preview
        ),
        idempotency_key="receive-execute-partial",
    )

    session.refresh(target)

    assert (
        target.in_transit_quantity
        == Decimal("2.5000")
    )
    assert (
        target.on_hand_quantity
        == Decimal("1.5000")
    )

    assert result.status == "PARTIALLY_RECEIVED"
    assert (
        result.lines[0].received_quantity
        == Decimal("1.5000")
    )
    assert (
        result.lines[0].dispatched_quantity
        == Decimal("4.0000")
    )

    transaction = session.get(
        InventoryTransaction,
        preview.transaction_id,
    )
    assert transaction is not None
    assert transaction.status == "COMPLETED"

    entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.transaction_id
                == transaction.id
            )
        )
    )

    assert len(entries) == 1
    entry = entries[0]

    assert entry.balance_id == target.id
    assert (
        entry.in_transit_delta
        == Decimal("-1.5000")
    )
    assert (
        entry.on_hand_delta
        == Decimal("1.5000")
    )


def test_receive_final_quantity_completes_transfer(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="COMPLETE",
        quantity="4.0000",
    )

    first_preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.5000",
        key="receive-preview-complete-1",
    )

    partial = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=_receive_execute_command(
            first_preview
        ),
        idempotency_key=(
            "receive-execute-complete-1"
        ),
    )

    assert partial.status == "PARTIALLY_RECEIVED"

    second_preview = _receive_preview(
        service,
        session,
        actor_admin,
        partial,
        quantity="2.5000",
        key="receive-preview-complete-2",
    )

    completed = service.execute_receive(
        session,
        actor_admin,
        partial.id,
        command=_receive_execute_command(
            second_preview
        ),
        idempotency_key=(
            "receive-execute-complete-2"
        ),
    )

    session.refresh(target)

    assert completed.status == "COMPLETED"
    assert (
        completed.lines[0].received_quantity
        == Decimal("4.0000")
    )
    assert (
        target.in_transit_quantity
        == Decimal("0.0000")
    )
    assert (
        target.on_hand_quantity
        == Decimal("4.0000")
    )


def test_repeated_receive_uses_distinct_transactions(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="REPEATED",
        quantity="4.0000",
    )

    first_preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-repeat-1",
    )

    first = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=_receive_execute_command(
            first_preview
        ),
        idempotency_key="receive-execute-repeat-1",
    )

    second_preview = _receive_preview(
        service,
        session,
        actor_admin,
        first,
        quantity="1.0000",
        key="receive-preview-repeat-2",
    )

    second = service.execute_receive(
        session,
        actor_admin,
        first.id,
        command=_receive_execute_command(
            second_preview
        ),
        idempotency_key="receive-execute-repeat-2",
    )

    assert (
        first_preview.transaction_id
        != second_preview.transaction_id
    )
    assert first.status == "PARTIALLY_RECEIVED"
    assert second.status == "PARTIALLY_RECEIVED"
    assert (
        second.lines[0].received_quantity
        == Decimal("2.0000")
    )


def test_receive_execute_replay_does_not_double_receive(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="EXECUTE-REPLAY",
        quantity="4.0000",
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="receive-preview-replay-execute",
    )

    execute_command = _receive_execute_command(
        preview
    )

    first = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=execute_command,
        idempotency_key=(
            "receive-execute-replay"
        ),
    )

    session.refresh(target)

    target_after_first = (
        _inventory_quantities(target)
    )
    ledger_after_first = _ledger_count(
        session
    )

    replay = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=execute_command,
        idempotency_key=(
            "receive-execute-replay"
        ),
    )

    session.refresh(target)

    assert replay == first
    assert (
        _inventory_quantities(target)
        == target_after_first
    )
    assert (
        _ledger_count(session)
        == ledger_after_first
    )


def test_serial_receive_relocates_item_to_target_warehouse_and_location(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        facts,
        serial_item,
        target_warehouse,
        target_location,
        _,
    ) = _serial_cross_warehouse_receive_fixture(
        session,
        actor_admin,
        suffix="RELOCATE",
    )

    assert (
        serial_item.warehouse_id
        == facts["warehouse"].id
    )
    assert (
        serial_item.location_id
        == facts["source_location"].id
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="serial-receive-preview-relocate",
    )

    completed = service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=_receive_execute_command(
            preview
        ),
        idempotency_key=(
            "serial-receive-execute-relocate"
        ),
    )

    session.refresh(serial_item)

    assert completed.status == "COMPLETED"
    assert (
        serial_item.warehouse_id
        == target_warehouse.id
    )
    assert (
        serial_item.location_id
        == target_location.id
    )
    assert serial_item.status == "IN_STOCK"


def test_serial_receive_ledger_audits_location_before_and_after(
    session,
    actor_admin,
) -> None:
    from app.models import InventoryLedgerEntry
    from sqlalchemy import select

    (
        service,
        transfer,
        facts,
        serial_item,
        target_warehouse,
        target_location,
        _,
    ) = _serial_cross_warehouse_receive_fixture(
        session,
        actor_admin,
        suffix="AUDIT",
    )

    preview = _receive_preview(
        service,
        session,
        actor_admin,
        transfer,
        quantity="1.0000",
        key="serial-receive-preview-audit",
    )

    service.execute_receive(
        session,
        actor_admin,
        transfer.id,
        command=_receive_execute_command(
            preview
        ),
        idempotency_key=(
            "serial-receive-execute-audit"
        ),
    )

    entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.transaction_id
                == preview.transaction_id
            )
            .order_by(InventoryLedgerEntry.id)
        )
    )

    assert len(entries) == 1

    entry = entries[0]

    assert entry.serial_item_id == serial_item.id

    assert (
        entry.state_before_json["state_mutations"]
        == [
            {
                "target_type": "serialized_item",
                "target_id": serial_item.id,
                "warehouse_id": (
                    facts["warehouse"].id
                ),
                "location_id": (
                    facts["source_location"].id
                ),
            }
        ]
    )

    assert (
        entry.state_after_json["state_mutations"]
        == [
            {
                "target_type": "serialized_item",
                "target_id": serial_item.id,
                "warehouse_id": target_warehouse.id,
                "location_id": target_location.id,
            }
        ]
    )
# TASK 7 RED SLICE 4 鈥?CANCEL CONTRACTS


def test_cancel_draft_marks_cancelled_and_has_no_inventory_or_ledger_side_effect(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        source,
        target,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="CANCEL-DRAFT",
        quantity="2.0000",
        on_hand="10",
    )

    source_before = _inventory_quantities(source)
    target_before = _inventory_quantities(target)
    ledger_before = _ledger_count(session)
    original_version = transfer.version

    cancelled = service.cancel(
        session,
        actor_admin,
        transfer.id,
        expected_version=transfer.version,
        idempotency_key="cancel-draft-success",
    )

    assert cancelled.status == "CANCELLED"
    assert cancelled.version == original_version + 1
    assert cancelled.cancelled_at is not None
    assert _inventory_quantities(source) == source_before
    assert _inventory_quantities(target) == target_before
    assert _ledger_count(session) == ledger_before


def test_cancel_rejects_stale_transfer_version(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="CANCEL-VERSION",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.cancel(
            session,
            actor_admin,
            transfer.id,
            expected_version=transfer.version + 1,
            idempotency_key="cancel-stale-version",
        )

    assert exc_info.value.details["conflict_object"] == "inventory_transfer"
    assert exc_info.value.details["expected_version"] == transfer.version + 1
    assert exc_info.value.details["actual_version"] == transfer.version


def test_cancel_same_key_same_command_replays_without_second_transition(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="CANCEL-REPLAY",
    )

    first = service.cancel(
        session,
        actor_admin,
        transfer.id,
        expected_version=transfer.version,
        idempotency_key="cancel-replay-key",
    )
    replay = service.cancel(
        session,
        actor_admin,
        transfer.id,
        expected_version=transfer.version,
        idempotency_key="cancel-replay-key",
    )

    assert replay == first
    assert replay.status == "CANCELLED"
    assert replay.version == transfer.version + 1


def test_cancel_same_key_changed_payload_is_rejected(
    session,
    actor_admin,
) -> None:
    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="CANCEL-IDEMPOTENCY-REUSE",
    )

    service.cancel(
        session,
        actor_admin,
        transfer.id,
        expected_version=transfer.version,
        idempotency_key="cancel-reused-key",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.cancel(
            session,
            actor_admin,
            transfer.id,
            expected_version=transfer.version + 1,
            idempotency_key="cancel-reused-key",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_cancel_hides_cross_tenant_transfer(
    session,
    actor_admin,
) -> None:
    from app.security.actor import ActorContext, MaintenanceRole

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix="CANCEL-TENANT",
    )

    foreign_actor = ActorContext(
        user_id="foreign-user",
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
        request_id="foreign-request",
        token_id="foreign-token",
    )

    with pytest.raises(NotFoundError):
        service.cancel(
            session,
            foreign_actor,
            transfer.id,
            expected_version=transfer.version,
            idempotency_key="cancel-cross-tenant",
        )


@pytest.mark.parametrize(
    "blocked_status",
    [
        "DISPATCHED",
        "PARTIALLY_RECEIVED",
        "COMPLETED",
    ],
)
def test_cancel_rejects_transfer_after_dispatch_started(
    session,
    actor_admin,
    blocked_status,
) -> None:
    from app.models import InventoryTransfer

    (
        service,
        transfer,
        _,
        _,
        _,
    ) = _dispatch_fixture(
        session,
        actor_admin,
        suffix=f"CANCEL-{blocked_status}",
    )

    persisted = session.get(
        InventoryTransfer,
        transfer.id,
    )
    assert persisted is not None

    persisted.status = blocked_status
    persisted.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.cancel(
            session,
            actor_admin,
            persisted.id,
            expected_version=persisted.version,
            idempotency_key=f"cancel-blocked-{blocked_status.lower()}",
        )

    assert exc_info.value.code == "TRANSFER_STATE_CONFLICT"
    assert exc_info.value.details["conflict_object"] == "inventory_transfer"
    assert exc_info.value.details["retryable"] is False
# TASK 7 RED SLICE 5 鈥?DETERMINISTIC CONCURRENT RECEIVE


def _concurrent_receive_preview(
    session,
    actor,
    *,
    transfer_id: int,
    transfer_line_id: int,
    expected_version: int,
    quantity: str,
    key: str,
):
    service = _service_class()()
    preview = service.preview_receive(
        session,
        actor,
        transfer_id,
        command={
            "expected_version": expected_version,
            "lines": [
                {
                    "transfer_line_id": transfer_line_id,
                    "quantity": quantity,
                }
            ],
        },
        idempotency_key=key,
    )
    session.commit()
    return preview


@pytest.mark.parametrize(
    ("winner_quantity", "expected_status", "expected_remaining"),
    [
        ("4.0000", "COMPLETED", "0.0000"),
        ("3.0000", "PARTIALLY_RECEIVED", "1.0000"),
    ],
)
def test_concurrent_receive_stale_previews_apply_exactly_once(
    session,
    actor_admin,
    winner_quantity,
    expected_status,
    expected_remaining,
) -> None:
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models import (
        InventoryBalance,
        InventoryTransfer,
        InventoryTransferLine,
    )

    (
        _,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix=f"CONCURRENT-{expected_status}",
        quantity="4.0000",
    )

    transfer_id = transfer.id
    transfer_line_id = transfer.lines[0].id
    target_balance_id = target.id
    starting_transfer_version = transfer.version
    starting_line_version = transfer.lines[0].version
    starting_target_on_hand = target.on_hand_quantity
    starting_target_in_transit = target.in_transit_quantity
    session.commit()

    winner_session = SessionLocal()
    loser_session = SessionLocal()
    verification_session = SessionLocal()

    try:
        winner_preview = _concurrent_receive_preview(
            winner_session,
            actor_admin,
            transfer_id=transfer_id,
            transfer_line_id=transfer_line_id,
            expected_version=starting_transfer_version,
            quantity=winner_quantity,
            key=f"concurrent-preview-winner-{expected_status}",
        )
        loser_preview = _concurrent_receive_preview(
            loser_session,
            actor_admin,
            transfer_id=transfer_id,
            transfer_line_id=transfer_line_id,
            expected_version=starting_transfer_version,
            quantity=winner_quantity,
            key=f"concurrent-preview-loser-{expected_status}",
        )

        winner_service = _service_class()()
        winner = winner_service.execute_receive(
            winner_session,
            actor_admin,
            transfer_id,
            command=_receive_execute_command(winner_preview),
            idempotency_key=f"concurrent-execute-winner-{expected_status}",
        )
        winner_session.commit()

        loser_service = _service_class()()
        loser_error = None
        loser_result = None
        try:
            loser_result = loser_service.execute_receive(
                loser_session,
                actor_admin,
                transfer_id,
                command=_receive_execute_command(loser_preview),
                idempotency_key=f"concurrent-execute-loser-{expected_status}",
            )
            loser_session.commit()
        except ConflictError as exc:
            loser_error = exc
            loser_session.rollback()

        assert loser_result is None
        assert loser_error is not None
        assert loser_error.code in {
            "INVENTORY_TRANSACTION_VERSION_CONFLICT",
            "INVENTORY_VERSION_CONFLICT",
            "TRANSFER_STATE_CONFLICT",
        }

        persisted_transfer = verification_session.get(
            InventoryTransfer,
            transfer_id,
        )
        persisted_line = verification_session.get(
            InventoryTransferLine,
            transfer_line_id,
        )
        persisted_target = verification_session.get(
            InventoryBalance,
            target_balance_id,
        )

        assert persisted_transfer is not None
        assert persisted_line is not None
        assert persisted_target is not None

        amount = Decimal(winner_quantity)
        assert winner.status == expected_status
        assert persisted_transfer.status == expected_status
        assert persisted_transfer.version == starting_transfer_version + 1
        assert persisted_line.received_quantity == amount
        assert persisted_line.version == starting_line_version + 1
        assert (
            persisted_target.in_transit_quantity
            == starting_target_in_transit - amount
        )
        assert (
            persisted_target.on_hand_quantity
            == starting_target_on_hand + amount
        )
        assert (
            persisted_target.in_transit_quantity
            == Decimal(expected_remaining)
        )
        assert persisted_line.received_quantity <= persisted_line.dispatched_quantity
    finally:
        verification_session.close()
        loser_session.rollback()
        loser_session.close()
        winner_session.rollback()
        winner_session.close()


def test_concurrent_receive_same_execute_key_replays_without_double_mutation(
    session,
    actor_admin,
) -> None:
    from app.db.session import SessionLocal
    from app.models import (
        InventoryBalance,
        InventoryTransfer,
        InventoryTransferLine,
    )

    (
        _,
        transfer,
        _,
        _,
        target,
    ) = _receive_fixture(
        session,
        actor_admin,
        suffix="CONCURRENT-REPLAY",
        quantity="4.0000",
    )

    transfer_id = transfer.id
    transfer_line_id = transfer.lines[0].id
    target_balance_id = target.id
    starting_transfer_version = transfer.version
    starting_line_version = transfer.lines[0].version
    starting_target_on_hand = target.on_hand_quantity
    starting_target_in_transit = target.in_transit_quantity
    session.commit()

    winner_session = SessionLocal()
    replay_session = SessionLocal()
    verification_session = SessionLocal()

    try:
        preview = _concurrent_receive_preview(
            winner_session,
            actor_admin,
            transfer_id=transfer_id,
            transfer_line_id=transfer_line_id,
            expected_version=starting_transfer_version,
            quantity="1.0000",
            key="concurrent-replay-preview",
        )

        execute_key = "concurrent-replay-execute"
        execute_command = _receive_execute_command(preview)

        winner = _service_class()().execute_receive(
            winner_session,
            actor_admin,
            transfer_id,
            command=execute_command,
            idempotency_key=execute_key,
        )
        winner_session.commit()

        replay = _service_class()().execute_receive(
            replay_session,
            actor_admin,
            transfer_id,
            command=execute_command,
            idempotency_key=execute_key,
        )
        replay_session.commit()

        assert replay == winner

        persisted_transfer = verification_session.get(
            InventoryTransfer,
            transfer_id,
        )
        persisted_line = verification_session.get(
            InventoryTransferLine,
            transfer_line_id,
        )
        persisted_target = verification_session.get(
            InventoryBalance,
            target_balance_id,
        )

        assert persisted_transfer is not None
        assert persisted_line is not None
        assert persisted_target is not None

        assert persisted_transfer.status == "PARTIALLY_RECEIVED"
        assert persisted_transfer.version == starting_transfer_version + 1
        assert persisted_line.received_quantity == Decimal("1.0000")
        assert persisted_line.version == starting_line_version + 1
        assert (
            persisted_target.in_transit_quantity
            == starting_target_in_transit - Decimal("1.0000")
        )
        assert (
            persisted_target.on_hand_quantity
            == starting_target_on_hand + Decimal("1.0000")
        )
    finally:
        verification_session.close()
        replay_session.rollback()
        replay_session.close()
        winner_session.rollback()
        winner_session.close()
