from __future__ import annotations

import importlib
from decimal import Decimal
from types import ModuleType

import pytest
from app.schemas.inventory_ledger import InventoryQuantityDelta
from pydantic import ValidationError


def _operation_schema_module() -> ModuleType:
    try:
        return importlib.import_module("app.schemas.inventory_operation")
    except ModuleNotFoundError:
        pytest.fail(
            "Task 2 requires app.schemas.inventory_operation",
            pytrace=False,
        )


def _operation_schema_api():
    module = _operation_schema_module()
    required_names = (
        "InventoryStateMutation",
        "InventoryBalanceMutation",
        "InventoryMutationPlan",
    )
    missing = [name for name in required_names if not hasattr(module, name)]
    assert not missing, f"missing Task 2 schema types: {missing}"
    return tuple(getattr(module, name) for name in required_names)


def test_plan_normalizes_balance_lock_order() -> None:
    _, InventoryBalanceMutation, InventoryMutationPlan = _operation_schema_api()

    plan = InventoryMutationPlan(
        operation_type="TRANSFER_DISPATCH",
        reason="dispatch transfer",
        mutations=(
            InventoryBalanceMutation(
                balance_id=20,
                expected_version=3,
                deltas=InventoryQuantityDelta(in_transit="2"),
            ),
            InventoryBalanceMutation(
                balance_id=10,
                expected_version=4,
                deltas=InventoryQuantityDelta(on_hand="-2"),
            ),
        ),
    )

    assert [item.balance_id for item in plan.mutations] == [10, 20]


def test_plan_rejects_duplicate_balance_mutations() -> None:
    _, InventoryBalanceMutation, InventoryMutationPlan = _operation_schema_api()

    with pytest.raises(ValidationError):
        InventoryMutationPlan(
            operation_type="ADJUST",
            reason="duplicate balance",
            mutations=(
                InventoryBalanceMutation(
                    balance_id=10,
                    expected_version=1,
                    deltas=InventoryQuantityDelta(on_hand="1"),
                ),
                InventoryBalanceMutation(
                    balance_id=10,
                    expected_version=1,
                    deltas=InventoryQuantityDelta(reserved="1"),
                ),
            ),
        )


def test_plan_rejects_zero_delta_without_state_mutation() -> None:
    _, InventoryBalanceMutation, InventoryMutationPlan = _operation_schema_api()

    with pytest.raises(ValidationError):
        InventoryMutationPlan(
            operation_type="ADJUST",
            reason="no change",
            mutations=(
                InventoryBalanceMutation(
                    balance_id=10,
                    expected_version=1,
                    deltas=InventoryQuantityDelta(),
                ),
            ),
        )


def test_freeze_accepts_zero_delta_with_state_mutation() -> None:
    (
        InventoryStateMutation,
        InventoryBalanceMutation,
        InventoryMutationPlan,
    ) = _operation_schema_api()

    plan = InventoryMutationPlan(
        operation_type="FREEZE",
        reason="quality hold",
        mutations=(
            InventoryBalanceMutation(
                balance_id=10,
                expected_version=1,
                deltas=InventoryQuantityDelta(),
                state_mutations=(
                    InventoryStateMutation(
                        lot_id=30,
                        state_before={"is_frozen": False, "freeze_reason": None},
                        state_after={
                            "is_frozen": True,
                            "freeze_reason": "quality hold",
                        },
                    ),
                ),
            ),
        ),
    )

    assert plan.mutations[0].deltas.on_hand == Decimal("0.0000")
    assert plan.mutations[0].state_mutations[0].lot_id == 30


def test_plan_rejects_unknown_operation_type() -> None:
    _, InventoryBalanceMutation, InventoryMutationPlan = _operation_schema_api()

    with pytest.raises(ValidationError):
        InventoryMutationPlan(
            operation_type="UNKNOWN",
            reason="invalid operation",
            mutations=(
                InventoryBalanceMutation(
                    balance_id=10,
                    expected_version=1,
                    deltas=InventoryQuantityDelta(on_hand="1"),
                ),
            ),
        )
