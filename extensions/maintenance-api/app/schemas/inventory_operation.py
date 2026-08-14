from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.inventory_ledger import InventoryQuantityDelta

InventoryOperationType = Literal[
    "OPENING",
    "ADJUST",
    "RESERVE",
    "UNRESERVE",
    "ISSUE",
    "RETURN",
    "TRANSFER_DISPATCH",
    "TRANSFER_RECEIVE",
    "FREEZE",
    "UNFREEZE",
    "REVERSE",
    "STOCKTAKE_CONFIRM",
]
InventoryTerminalStatus = Literal["COMPLETED", "PARTIALLY_COMPLETED"]
InventoryStateValue = str | int | bool | None
InventoryAuditValue = str | int | bool | list | dict


class InventoryStateMutation(BaseModel):
    model_config = ConfigDict(frozen=True)

    lot_id: int | None = Field(default=None, gt=0)
    serial_item_id: int | None = Field(default=None, gt=0)
    state_before: dict[str, InventoryStateValue]
    state_after: dict[str, InventoryStateValue]

    @model_validator(mode="after")
    def validate_target_and_change(self) -> InventoryStateMutation:
        target_count = int(self.lot_id is not None) + int(self.serial_item_id is not None)
        if target_count != 1:
            raise ValueError("state mutation requires exactly one lot or serial target")
        if not self.state_before or self.state_before.keys() != self.state_after.keys():
            raise ValueError("state mutation requires matching non-empty state keys")
        if self.state_before == self.state_after:
            raise ValueError("state mutation must change state")
        return self


class InventoryBalanceMutation(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance_id: int = Field(gt=0)
    expected_version: int = Field(gt=0)
    deltas: InventoryQuantityDelta
    state_mutations: tuple[InventoryStateMutation, ...] = ()


class InventoryMutationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_type: InventoryOperationType
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str
    mutations: tuple[InventoryBalanceMutation, ...]
    audit_context: dict[str, InventoryAuditValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_and_validate_mutations(self) -> InventoryMutationPlan:
        if not self.mutations:
            raise ValueError("inventory mutation plan requires at least one mutation")

        ordered = tuple(sorted(self.mutations, key=lambda item: item.balance_id))
        balance_ids = [item.balance_id for item in ordered]
        if len(balance_ids) != len(set(balance_ids)):
            raise ValueError("inventory mutation plan contains duplicate balances")

        state_targets: list[tuple[str, int]] = []
        for mutation in ordered:
            mutation_has_nonzero_delta = any(
                value != 0
                for value in (
                    mutation.deltas.on_hand,
                    mutation.deltas.reserved,
                    mutation.deltas.damaged,
                    mutation.deltas.quarantined,
                    mutation.deltas.in_transit,
                )
            )
            if not mutation_has_nonzero_delta:
                if (
                    self.operation_type not in {"FREEZE", "UNFREEZE"}
                    or not mutation.state_mutations
                ):
                    raise ValueError(
                        "zero-delta mutations require FREEZE or UNFREEZE state changes"
                    )
            for state_mutation in mutation.state_mutations:
                if state_mutation.lot_id is not None:
                    state_targets.append(("lot", state_mutation.lot_id))
                else:
                    assert state_mutation.serial_item_id is not None
                    state_targets.append(("serial", state_mutation.serial_item_id))

        if len(state_targets) != len(set(state_targets)):
            raise ValueError("inventory mutation plan contains duplicate state targets")

        object.__setattr__(self, "mutations", ordered)
        return self


class InventoryOperationPreviewRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: int = Field(gt=0)
    operation_type: InventoryOperationType
    status: Literal["PREVIEWED"] = "PREVIEWED"
    transaction_version: int = Field(gt=0)
    confirmation_token: str | None = None
    confirmation_expires_at: datetime