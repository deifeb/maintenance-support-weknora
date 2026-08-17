from __future__ import annotations

import importlib
from decimal import Decimal
from types import ModuleType

import pytest
from app.core.exceptions import (
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
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
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.security.actor import MaintenanceRole
from sqlalchemy import func, select


def _operation_schema_module() -> ModuleType:
    try:
        return importlib.import_module("app.schemas.inventory_operation")
    except ModuleNotFoundError:
        pytest.fail(
            "Task 2 requires app.schemas.inventory_operation",
            pytrace=False,
        )


def _mutation_api():
    module = _operation_schema_module()
    required_names = (
        "InventoryBalanceMutation",
        "InventoryMutationPlan",
    )
    missing = [name for name in required_names if not hasattr(module, name)]
    assert not missing, f"missing Task 2 schema types: {missing}"

    from app.services.inventory_transaction_service import InventoryTransactionService

    assert hasattr(
        InventoryTransactionService,
        "apply_plan",
    ), "Task 2 requires InventoryTransactionService.apply_plan"
    return (
        module.InventoryBalanceMutation,
        module.InventoryMutationPlan,
        InventoryTransactionService,
    )


def _seed_transfer_balances(session) -> tuple[InventoryBalance, InventoryBalance]:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-MUTATION",
        name="Mutation Warehouse",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code="SP-MUTATION",
        name="Mutation Spare",
    )
    session.add_all([warehouse, part])
    session.flush()

    source_location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code="SOURCE",
        name="Source",
        location_type="SHELF",
    )
    target_location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code="TARGET",
        name="Target",
        location_type="SHELF",
    )
    session.add_all([source_location, target_location])
    session.flush()

    source = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        location_id=source_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal("5.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    target = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        location_id=target_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal("0.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("1.0000"),
    )
    session.add_all([source, target])
    session.flush()
    return source, target


def _dispatch_plan(
    source: InventoryBalance,
    target: InventoryBalance,
    *,
    quantity: str = "2.0000",
    target_expected_version: int | None = None,
):
    InventoryBalanceMutation, InventoryMutationPlan, _ = _mutation_api()
    amount = Decimal(quantity)
    return InventoryMutationPlan(
        operation_type="TRANSFER_DISPATCH",
        reference_type="inventory_transfer",
        reference_id="transfer-1",
        reason="dispatch transfer",
        mutations=(
            InventoryBalanceMutation(
                balance_id=target.id,
                expected_version=(
                    target.version
                    if target_expected_version is None
                    else target_expected_version
                ),
                deltas=InventoryQuantityDelta(in_transit=amount),
            ),
            InventoryBalanceMutation(
                balance_id=source.id,
                expected_version=source.version,
                deltas=InventoryQuantityDelta(on_hand=-amount),
            ),
        ),
        audit_context={"transfer_id": "transfer-1"},
    )


def test_apply_plan_updates_two_balances_and_writes_ordered_entries(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    source, target = _seed_transfer_balances(session)
    service = InventoryTransactionService()

    result = service.apply_plan(
        session,
        actor_admin,
        plan=_dispatch_plan(source, target),
        idempotency_key="dispatch-success",
        required_role=MaintenanceRole.ADMIN,
    )

    assert result.operation_type == "TRANSFER_DISPATCH"
    assert result.status == "COMPLETED"
    assert [entry.balance_id for entry in result.entries] == sorted(
        [source.id, target.id]
    )
    assert source.on_hand_quantity == Decimal("3.0000")
    assert target.in_transit_quantity == Decimal("3.0000")
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 2


def test_apply_plan_requests_balance_locks_in_stable_order(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    source, target = _seed_transfer_balances(session)

    class RecordingLedgerRepository(InventoryLedgerRepository):
        def __init__(self) -> None:
            self.requested_balance_ids: list[int] = []

        def lock_balances(self, session, tenant_id, balance_ids):
            self.requested_balance_ids = list(balance_ids)
            return super().lock_balances(session, tenant_id, balance_ids)

    repository = RecordingLedgerRepository()
    service = InventoryTransactionService(ledger_repository=repository)

    service.apply_plan(
        session,
        actor_admin,
        plan=_dispatch_plan(source, target),
        idempotency_key="dispatch-lock-order",
        required_role=MaintenanceRole.ADMIN,
    )

    assert repository.requested_balance_ids == sorted([source.id, target.id])


def test_apply_plan_rolls_back_all_balances_on_second_conflict(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    source, target = _seed_transfer_balances(session)
    source_id = source.id
    target_id = target.id
    service = InventoryTransactionService()

    with pytest.raises(ConflictError) as exc_info:
        service.apply_plan(
            session,
            actor_admin,
            plan=_dispatch_plan(
                source,
                target,
                target_expected_version=target.version + 1,
            ),
            idempotency_key="dispatch-conflict",
            required_role=MaintenanceRole.ADMIN,
        )

    assert exc_info.value.code == "INVENTORY_VERSION_CONFLICT"
    session.expire_all()
    persisted_source = session.get(InventoryBalance, source_id)
    persisted_target = session.get(InventoryBalance, target_id)
    assert persisted_source is not None
    assert persisted_target is not None
    assert persisted_source.on_hand_quantity == Decimal("5.0000")
    assert persisted_target.in_transit_quantity == Decimal("1.0000")
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0


def test_apply_plan_replays_same_request_and_rejects_changed_payload(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    source, target = _seed_transfer_balances(session)
    service = InventoryTransactionService()
    plan = _dispatch_plan(source, target)

    first = service.apply_plan(
        session,
        actor_admin,
        plan=plan,
        idempotency_key="dispatch-replay",
        required_role=MaintenanceRole.ADMIN,
    )
    replay = service.apply_plan(
        session,
        actor_admin,
        plan=plan,
        idempotency_key="dispatch-replay",
        required_role=MaintenanceRole.ADMIN,
    )

    assert replay == first
    with pytest.raises(ConflictError) as exc_info:
        service.apply_plan(
            session,
            actor_admin,
            plan=_dispatch_plan(source, target, quantity="1.0000"),
            idempotency_key="dispatch-replay",
            required_role=MaintenanceRole.ADMIN,
        )
    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 2



def _seed_lot_balance(session) -> tuple[InventoryBalance, InventoryLot]:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-STATE",
        name="State Warehouse",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code="SP-STATE",
        name="State Spare",
    )
    session.add_all([warehouse, part])
    session.flush()
    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code="STATE",
        name="State Location",
        location_type="SHELF",
    )
    lot = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=part.id,
        lot_code="LOT-STATE",
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


def _freeze_plan(balance: InventoryBalance, lot: InventoryLot, *, before=False):
    module = _operation_schema_module()
    return module.InventoryMutationPlan(
        operation_type="FREEZE",
        reason="quality hold",
        mutations=(
            module.InventoryBalanceMutation(
                balance_id=balance.id,
                expected_version=balance.version,
                deltas=InventoryQuantityDelta(),
                state_mutations=(
                    module.InventoryStateMutation(
                        lot_id=lot.id,
                        state_before={
                            "is_frozen": before,
                            "freeze_reason": None,
                        },
                        state_after={
                            "is_frozen": True,
                            "freeze_reason": "quality hold",
                        },
                    ),
                ),
            ),
        ),
        audit_context={"source": "manual-review"},
    )


def test_apply_plan_applies_zero_delta_lot_state_atomically(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    balance, lot = _seed_lot_balance(session)

    result = InventoryTransactionService().apply_plan(
        session,
        actor_admin,
        plan=_freeze_plan(balance, lot),
        idempotency_key="freeze-lot",
        required_role=MaintenanceRole.ADMIN,
    )

    assert result.operation_type == "FREEZE"
    assert lot.is_frozen is True
    assert lot.freeze_reason == "quality hold"
    assert lot.version == 2
    assert balance.version == 2
    assert result.entries[0].state_before_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": False,
            "freeze_reason": None,
        }
    ]
    assert result.entries[0].state_after_json["state_mutations"] == [
        {
            "target_type": "inventory_lot",
            "target_id": lot.id,
            "is_frozen": True,
            "freeze_reason": "quality hold",
        }
    ]


def test_apply_plan_rejects_stale_state_snapshot_without_partial_writes(
    session,
    actor_admin,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    balance, lot = _seed_lot_balance(session)

    with pytest.raises(ConflictError) as exc_info:
        InventoryTransactionService().apply_plan(
            session,
            actor_admin,
            plan=_freeze_plan(balance, lot, before=True),
            idempotency_key="freeze-stale",
            required_role=MaintenanceRole.ADMIN,
        )

    assert exc_info.value.code == "INVENTORY_STATE_CONFLICT"
    assert lot.is_frozen is False
    assert lot.version == 1
    assert balance.version == 1
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0


def test_apply_plan_rejects_missing_balance_before_writing_any_projection(
    session,
    actor_admin,
) -> None:
    InventoryBalanceMutation, InventoryMutationPlan, InventoryTransactionService = (
        _mutation_api()
    )
    source, _ = _seed_transfer_balances(session)
    missing_balance_id = source.id + 1000
    plan = InventoryMutationPlan(
        operation_type="TRANSFER_DISPATCH",
        reason="missing target",
        mutations=(
            InventoryBalanceMutation(
                balance_id=source.id,
                expected_version=source.version,
                deltas=InventoryQuantityDelta(on_hand="-1"),
            ),
            InventoryBalanceMutation(
                balance_id=missing_balance_id,
                expected_version=1,
                deltas=InventoryQuantityDelta(in_transit="1"),
            ),
        ),
    )

    with pytest.raises(NotFoundError) as exc_info:
        InventoryTransactionService().apply_plan(
            session,
            actor_admin,
            plan=plan,
            idempotency_key="missing-target",
            required_role=MaintenanceRole.ADMIN,
        )

    assert exc_info.value.details == {
        "resource": "inventory_balance",
        "identifier": missing_balance_id,
    }
    assert source.on_hand_quantity == Decimal("5.0000")
    assert source.version == 1


def test_apply_plan_enforces_required_role(
    session,
    actor_contributor,
) -> None:
    _, _, InventoryTransactionService = _mutation_api()
    source, target = _seed_transfer_balances(session)

    with pytest.raises(InsufficientMaintenanceRoleError) as exc_info:
        InventoryTransactionService().apply_plan(
            session,
            actor_contributor,
            plan=_dispatch_plan(source, target),
            idempotency_key="dispatch-forbidden",
            required_role=MaintenanceRole.ADMIN,
        )

    assert exc_info.value.details == {
        "required_role": "admin",
        "actual_role": "contributor",
    }
