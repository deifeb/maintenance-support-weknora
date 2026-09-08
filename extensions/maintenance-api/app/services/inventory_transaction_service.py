from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from decimal import Decimal
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import false, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryTransaction,
    SerializedItem,
)
from app.models.mixins import utc_now
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
    decimal_state,
)
from app.schemas.inventory_ledger import (
    MAX_INVENTORY_QUANTITY,
    InventoryLedgerEntryRead,
    InventoryQuantityDelta,
    InventoryTransactionRead,
)
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
    InventoryStateMutation,
    InventoryTerminalStatus,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.snapshot_service import snapshot_service

OperationType = Literal["OPENING", "ADJUST"]
NewCommandValidator = Callable[[InventoryBalance], None]
StateTargetsValidator = Callable[
    [dict[int, InventoryLot], dict[int, SerializedItem]],
    None,
]
_IDEMPOTENCY_CONSTRAINT = "uq_inventory_tx_tenant_operation_idempotency"
_SQLITE_IDEMPOTENCY_UNIQUE_ERROR = (
    "UNIQUE constraint failed: inventory_transactions.tenant_id, "
    "inventory_transactions.operation_type, inventory_transactions.idempotency_key"
)
_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_LOT_STATE_FIELDS = frozenset({"is_frozen", "freeze_reason", "quality_status"})
_SERIAL_STATE_FIELDS = frozenset({"status", "warehouse_id", "location_id"})
_SERIAL_LOCATION_FIELDS = frozenset({"warehouse_id", "location_id"})


class InventoryTransactionService:
    def __init__(
        self,
        *,
        transaction_repository: InventoryTransactionRepository | None = None,
        ledger_repository: InventoryLedgerRepository | None = None,
    ) -> None:
        self.transaction_repository = (
            transaction_repository or InventoryTransactionRepository()
        )
        self.ledger_repository = ledger_repository or InventoryLedgerRepository()

    def opening(
        self,
        session: Session,
        actor: ActorContext,
        *,
        balance_id: int,
        expected_version: int,
        deltas: InventoryQuantityDelta,
        reason: str,
        idempotency_key: str,
    ) -> InventoryTransactionRead:
        self._require_contributor(actor)
        return self._apply_quantity_operation(
            session,
            actor,
            operation_type="OPENING",
            balance_id=balance_id,
            expected_version=expected_version,
            deltas=deltas,
            reason=reason,
            idempotency_key=idempotency_key,
        )

    def adjust(
        self,
        session: Session,
        actor: ActorContext,
        *,
        balance_id: int,
        expected_version: int,
        deltas: InventoryQuantityDelta,
        reason: str,
        idempotency_key: str,
        validate_new_command: NewCommandValidator | None = None,
    ) -> InventoryTransactionRead:
        self._require_admin(actor)
        return self._apply_quantity_operation(
            session,
            actor,
            operation_type="ADJUST",
            balance_id=balance_id,
            expected_version=expected_version,
            deltas=deltas,
            reason=reason,
            idempotency_key=idempotency_key,
            validate_new_command=validate_new_command,
        )

    def apply_plan(
        self,
        session: Session,
        actor: ActorContext,
        *,
        plan: InventoryMutationPlan,
        idempotency_key: str,
        required_role: MaintenanceRole,
        terminal_status: InventoryTerminalStatus = "COMPLETED",
    ) -> InventoryTransactionRead:
        return self._apply_plan(
            session,
            actor,
            plan=plan,
            idempotency_key=idempotency_key,
            required_role=required_role,
            terminal_status=terminal_status,
        )

    def apply_plan_to_transaction(
        self,
        session: Session,
        actor: ActorContext,
        *,
        transaction: InventoryTransaction,
        plan: InventoryMutationPlan,
        required_role: MaintenanceRole,
        terminal_status: InventoryTerminalStatus = "COMPLETED",
        validate_state_targets: StateTargetsValidator | None = None,
    ) -> InventoryTransactionRead:
        if transaction.tenant_id != actor.tenant_id:
            error = NotFoundError(
                "inventory_transaction",
                transaction.id,
            )
            error.request_id = actor.request_id
            raise error

        if (
            transaction.status != "PREVIEWED"
            or transaction.operation_type != plan.operation_type
        ):
            conflict = ConflictError(
                "inventory operation state conflict",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "transaction_id": transaction.id,
                    "status": transaction.status,
                    "operation_type": transaction.operation_type,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        return self._apply_plan(
            session,
            actor,
            plan=plan,
            idempotency_key=transaction.idempotency_key,
            required_role=required_role,
            terminal_status=terminal_status,
            existing_transaction=transaction,
            validate_state_targets=validate_state_targets,
        )
    def complete_preview_without_mutations(
        self,
        session: Session,
        actor: ActorContext,
        *,
        transaction: InventoryTransaction,
        operation_type: str,
        required_role: MaintenanceRole,
        terminal_status: InventoryTerminalStatus,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> InventoryTransactionRead:
        self._require_role(actor, required_role)
        if transaction.tenant_id != actor.tenant_id:
            error = NotFoundError(
                "inventory_transaction",
                transaction.id,
            )
            error.request_id = actor.request_id
            raise error

        if (
            transaction.status != "PREVIEWED"
            or transaction.operation_type != operation_type
        ):
            conflict = ConflictError(
                "inventory operation state conflict",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "transaction_id": transaction.id,
                    "status": transaction.status,
                    "operation_type": transaction.operation_type,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        existing_entries = self.transaction_repository.list_entries(
            session,
            actor.tenant_id,
            transaction.id,
        )
        if existing_entries:
            conflict = ConflictError(
                "zero-mutation terminalization requires zero ledger entries",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "transaction_id": transaction.id,
                    "entry_count": len(existing_entries),
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        clean_reason = self._normalize_reason(reason)
        previous_snapshot = deepcopy(
            transaction.response_snapshot_json
        )
        previous_extensions = (
            previous_snapshot.get("_extensions")
            if isinstance(previous_snapshot, dict)
            else None
        )

        transaction.status = terminal_status
        transaction.reason = clean_reason
        transaction.reference_type = reference_type
        transaction.reference_id = reference_id
        transaction.version += 1
        transaction.completed_at = utc_now()

        response = self._read_transaction(
            transaction,
            [],
        )
        snapshot = response.model_dump(mode="json")
        if isinstance(previous_extensions, dict):
            snapshot["_extensions"] = deepcopy(
                previous_extensions
            )
        self.transaction_repository.complete(
            session,
            transaction,
            completed_at=transaction.completed_at,
            response_snapshot=snapshot,
        )
        return response

    def _apply_quantity_operation(
        self,
        session: Session,
        actor: ActorContext,
        *,
        operation_type: OperationType,
        balance_id: int,
        expected_version: int,
        deltas: InventoryQuantityDelta,
        reason: str,
        idempotency_key: str,
        validate_new_command: NewCommandValidator | None = None,
    ) -> InventoryTransactionRead:
        clean_reason = self._normalize_reason(reason)
        if all(value == 0 for value in self._delta_values(deltas)):
            raise BusinessValidationError(
                "quantity operation requires a nonzero delta",
                code="INVENTORY_ZERO_DELTA",
            )
        plan = InventoryMutationPlan(
            operation_type=operation_type,
            reason=clean_reason,
            mutations=(
                InventoryBalanceMutation(
                    balance_id=balance_id,
                    expected_version=expected_version,
                    deltas=deltas,
                ),
            ),
        )
        return self._apply_plan(
            session,
            actor,
            plan=plan,
            idempotency_key=idempotency_key,
            required_role=(
                MaintenanceRole.CONTRIBUTOR
                if operation_type == "OPENING"
                else MaintenanceRole.ADMIN
            ),
            terminal_status="COMPLETED",
            request_hash_payload={
                "operation_type": operation_type,
                "balance_id": balance_id,
                "expected_version": expected_version,
                "deltas": deltas.model_dump(),
                "reason": clean_reason,
            },
            validate_new_command=validate_new_command,
        )

    def _apply_plan(
        self,
        session: Session,
        actor: ActorContext,
        *,
        plan: InventoryMutationPlan,
        idempotency_key: str,
        required_role: MaintenanceRole,
        terminal_status: InventoryTerminalStatus,
        request_hash_payload: dict[str, Any] | None = None,
        validate_new_command: NewCommandValidator | None = None,
        existing_transaction: InventoryTransaction | None = None,
        validate_state_targets: StateTargetsValidator | None = None,
    ) -> InventoryTransactionRead:
        self._require_role(actor, required_role)
        clean_reason = self._normalize_reason(plan.reason)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        clean_plan = plan.model_copy(update={"reason": clean_reason})
        request_hash = snapshot_service.canonical_hash(
            request_hash_payload or clean_plan.model_dump()
        )
        operation_type = clean_plan.operation_type

        self._ensure_savepoint_parent_transaction(session)
        try:
            with session.begin_nested():
                if existing_transaction is None:
                    existing = self.transaction_repository.get_idempotent(
                        session,
                        actor.tenant_id,
                        operation_type,
                        clean_key,
                    )
                    if existing is not None:
                        return self._replay(
                            actor,
                            existing,
                            request_hash,
                        )

                balance_ids = [item.balance_id for item in clean_plan.mutations]
                locked = self.ledger_repository.lock_balances(
                    session,
                    actor.tenant_id,
                    balance_ids,
                )
                locked_by_id = {balance.id: balance for balance in locked}

                if existing_transaction is None:
                    existing = self.transaction_repository.get_idempotent(
                        session,
                        actor.tenant_id,
                        operation_type,
                        clean_key,
                    )
                    if existing is not None:
                        return self._replay(
                            actor,
                            existing,
                            request_hash,
                        )

                if validate_new_command is not None:
                    validate_new_command(locked_by_id[clean_plan.mutations[0].balance_id])

                lots_by_id, serial_items_by_id = self._lock_state_targets(
                    session,
                    actor,
                    clean_plan.mutations,
                )
                if validate_state_targets is not None:
                    validate_state_targets(
                        lots_by_id,
                        serial_items_by_id,
                    )
                prepared = self._prepare_mutations(
                    actor,
                    clean_plan.mutations,
                    locked_by_id=locked_by_id,
                    lots_by_id=lots_by_id,
                    serial_items_by_id=serial_items_by_id,
                )
                for item in prepared:
                    self._write_balance(item["balance"], item["after_values"])
                    item["balance"].version = item["before_version"] + 1
                    for target, state_after in item["state_writes"]:
                        for field_name, value in state_after.items():
                            setattr(target, field_name, value)
                        target.version += 1

                if existing_transaction is None:
                    transaction = (
                        self.transaction_repository.create_transaction(
                            session,
                            actor=actor,
                            operation_type=operation_type,
                            idempotency_key=clean_key,
                            request_hash=request_hash,
                            reason=clean_reason,
                            status=terminal_status,
                            reference_type=clean_plan.reference_type,
                            reference_id=clean_plan.reference_id,
                        )
                    )
                else:
                    transaction = existing_transaction
                    transaction.status = terminal_status
                    transaction.reason = clean_reason
                    transaction.reference_type = clean_plan.reference_type
                    transaction.reference_id = clean_plan.reference_id
                    transaction.version += 1
                    session.flush()
                entries = self.transaction_repository.append_entries(
                    session,
                    transaction=transaction,
                    entries=[
                        {
                            "balance": item["balance"],
                            "deltas": item["mutation"].deltas,
                            "state_before": item["state_before"],
                            "state_after": item["state_after"],
                            "before_balance_version": item["before_version"],
                            "resulting_balance_version": item["balance"].version,
                            "serial_item_id": item["serial_item_id"],
                        }
                        for item in prepared
                    ],
                )
                completed_at = utc_now()
                transaction.completed_at = completed_at
                response = self._read_transaction(transaction, entries)
                snapshot = response.model_dump(mode="json")
                extensions: dict[str, Any] = {}
                if existing_transaction is not None:
                    previous_snapshot = (
                        existing_transaction.response_snapshot_json
                    )
                    if isinstance(previous_snapshot, dict):
                        previous_extensions = (
                            previous_snapshot.get("_extensions")
                        )
                        if isinstance(
                            previous_extensions,
                            dict,
                        ):
                            extensions.update(
                                deepcopy(previous_extensions)
                            )
                if clean_plan.audit_context:
                    extensions["audit_context"] = deepcopy(clean_plan.audit_context)
                if clean_plan.reference_type is not None or clean_plan.reference_id is not None:
                    extensions["reference"] = {
                        "type": clean_plan.reference_type,
                        "id": clean_plan.reference_id,
                    }
                if extensions:
                    snapshot["_extensions"] = extensions
                self.transaction_repository.complete(
                    session,
                    transaction,
                    completed_at=completed_at,
                    response_snapshot=snapshot,
                )
                return response
        except IntegrityError as exc:
            if existing_transaction is not None:
                raise
            if not self._is_idempotency_constraint_violation(exc):
                raise
            winner = self.transaction_repository.get_idempotent(
                session,
                actor.tenant_id,
                operation_type,
                clean_key,
            )
            if winner is not None:
                return self._replay(actor, winner, request_hash)
            conflict = ConflictError(
                "inventory transaction conflict",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": True,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict from exc

    def _lock_state_targets(
        self,
        session: Session,
        actor: ActorContext,
        mutations: Sequence[InventoryBalanceMutation],
    ) -> tuple[dict[int, InventoryLot], dict[int, SerializedItem]]:
        lot_ids = [
            state_mutation.lot_id
            for mutation in mutations
            for state_mutation in mutation.state_mutations
            if state_mutation.lot_id is not None
        ]
        serial_item_ids = [
            state_mutation.serial_item_id
            for mutation in mutations
            for state_mutation in mutation.state_mutations
            if state_mutation.serial_item_id is not None
        ]
        lots = self.ledger_repository.lock_lots(session, actor.tenant_id, lot_ids)
        serial_items = self.ledger_repository.lock_serial_items(
            session,
            actor.tenant_id,
            serial_item_ids,
        )
        return (
            {lot.id: lot for lot in lots},
            {item.id: item for item in serial_items},
        )

    def _prepare_mutations(
        self,
        actor: ActorContext,
        mutations: Sequence[InventoryBalanceMutation],
        *,
        locked_by_id: dict[int, InventoryBalance],
        lots_by_id: dict[int, InventoryLot],
        serial_items_by_id: dict[int, SerializedItem],
    ) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for mutation in mutations:
            balance = locked_by_id[mutation.balance_id]
            self._require_version(
                actor,
                balance,
                expected_version=mutation.expected_version,
            )
            before_version = balance.version
            before_values = self._balance_values(balance)
            after_values = tuple(
                current + delta
                for current, delta in zip(
                    before_values,
                    self._delta_values(mutation.deltas),
                    strict=True,
                )
            )
            self._validate_result(after_values)
            state_before: dict[str, Any] = decimal_state_from_values(before_values)
            state_after: dict[str, Any] = decimal_state_from_values(after_values)
            state_writes, state_snapshots, serial_item_id = self._prepare_state_writes(
                actor,
                balance,
                mutation.state_mutations,
                lots_by_id=lots_by_id,
                serial_items_by_id=serial_items_by_id,
            )
            if state_snapshots:
                state_before["state_mutations"] = [
                    snapshot["before"] for snapshot in state_snapshots
                ]
                state_after["state_mutations"] = [
                    snapshot["after"] for snapshot in state_snapshots
                ]
            prepared.append(
                {
                    "mutation": mutation,
                    "balance": balance,
                    "before_version": before_version,
                    "after_values": after_values,
                    "state_before": state_before,
                    "state_after": state_after,
                    "state_writes": state_writes,
                    "serial_item_id": serial_item_id,
                }
            )
        return prepared

    def _prepare_state_writes(
        self,
        actor: ActorContext,
        balance: InventoryBalance,
        state_mutations: Sequence[InventoryStateMutation],
        *,
        lots_by_id: dict[int, InventoryLot],
        serial_items_by_id: dict[int, SerializedItem],
    ) -> tuple[
        list[tuple[InventoryLot | SerializedItem, dict[str, str | int | bool | None]]],
        list[dict[str, dict[str, Any]]],
        int | None,
    ]:
        writes: list[
            tuple[InventoryLot | SerializedItem, dict[str, str | int | bool | None]]
        ] = []
        snapshots: list[dict[str, dict[str, Any]]] = []
        serial_ids: list[int] = []
        for state_mutation in state_mutations:
            if state_mutation.lot_id is not None:
                target: InventoryLot | SerializedItem = lots_by_id[state_mutation.lot_id]
                self._require_lot_matches_balance(actor, balance, target)
                target_type = "inventory_lot"
                target_id = state_mutation.lot_id
                allowed_fields = _LOT_STATE_FIELDS
            else:
                serial_item_id = state_mutation.serial_item_id
                if serial_item_id is None:
                    raise AssertionError("validated state mutation has no target")
                target = serial_items_by_id[serial_item_id]
                requested_fields = set(state_mutation.state_before)
                if requested_fields & _SERIAL_LOCATION_FIELDS:
                    self._require_serial_relocation_matches_balance(
                        actor,
                        balance,
                        target,
                        state_mutation,
                    )
                else:
                    self._require_serial_matches_balance(actor, balance, target)
                target_type = "serialized_item"
                target_id = serial_item_id
                serial_ids.append(serial_item_id)
                allowed_fields = _SERIAL_STATE_FIELDS

            self._require_state_snapshot(
                actor,
                target,
                state_mutation,
                target_type=target_type,
                target_id=target_id,
                allowed_fields=allowed_fields,
            )
            writes.append((target, state_mutation.state_after))
            snapshots.append(
                {
                    "before": {
                        "target_type": target_type,
                        "target_id": target_id,
                        **state_mutation.state_before,
                    },
                    "after": {
                        "target_type": target_type,
                        "target_id": target_id,
                        **state_mutation.state_after,
                    },
                }
            )
        return writes, snapshots, serial_ids[0] if len(serial_ids) == 1 else None

    @staticmethod
    def _require_lot_matches_balance(
        actor: ActorContext,
        balance: InventoryBalance,
        target: InventoryLot | SerializedItem,
    ) -> None:
        if not isinstance(target, InventoryLot) or balance.lot_id != target.id:
            conflict = ConflictError(
                "inventory lot does not match balance",
                code="INVENTORY_STATE_TARGET_MISMATCH",
                details={
                    "balance_id": balance.id,
                    "lot_id": target.id,
                    "conflict_object": "inventory_lot",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

    @staticmethod
    def _require_serial_matches_balance(
        actor: ActorContext,
        balance: InventoryBalance,
        target: InventoryLot | SerializedItem,
    ) -> None:
        matches = isinstance(target, SerializedItem) and (
            target.spare_part_id == balance.spare_part_id
            and target.warehouse_id == balance.warehouse_id
            and target.location_id == balance.location_id
            and target.lot_id == balance.lot_id
        )
        if not matches:
            conflict = ConflictError(
                "serialized item does not match balance",
                code="INVENTORY_STATE_TARGET_MISMATCH",
                details={
                    "balance_id": balance.id,
                    "serial_item_id": target.id,
                    "conflict_object": "serialized_item",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

    @staticmethod
    def _require_serial_relocation_matches_balance(
        actor: ActorContext,
        balance: InventoryBalance,
        target: InventoryLot | SerializedItem,
        state_mutation: InventoryStateMutation,
    ) -> None:
        if not isinstance(target, SerializedItem):
            conflict = ConflictError(
                "serialized item does not match balance",
                code="INVENTORY_STATE_TARGET_MISMATCH",
                details={
                    "balance_id": balance.id,
                    "serial_item_id": getattr(target, "id", None),
                    "conflict_object": "serialized_item",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        requested_fields = set(state_mutation.state_before)
        if not _SERIAL_LOCATION_FIELDS.issubset(requested_fields):
            raise BusinessValidationError(
                "serialized item relocation requires warehouse and location",
                code="INVENTORY_STATE_FIELD_INVALID",
                details={
                    "target_type": "serialized_item",
                    "target_id": target.id,
                    "fields": sorted(requested_fields),
                },
            )

        relocation_changed = any(
            state_mutation.state_before[field_name]
            != state_mutation.state_after[field_name]
            for field_name in _SERIAL_LOCATION_FIELDS
        )
        if not relocation_changed:
            raise BusinessValidationError(
                "serialized item relocation must change warehouse or location",
                code="INVENTORY_STATE_FIELD_INVALID",
                details={
                    "target_type": "serialized_item",
                    "target_id": target.id,
                    "fields": sorted(_SERIAL_LOCATION_FIELDS),
                },
            )

        source_identity_matches = (
            target.warehouse_id
            == state_mutation.state_before["warehouse_id"]
            and target.location_id
            == state_mutation.state_before["location_id"]
        )
        target_balance_identity_matches = (
            target.spare_part_id == balance.spare_part_id
            and target.lot_id == balance.lot_id
        )
        destination_matches_balance = (
            state_mutation.state_after["warehouse_id"]
            == balance.warehouse_id
            and state_mutation.state_after["location_id"]
            == balance.location_id
        )

        if (
            source_identity_matches
            and target_balance_identity_matches
            and destination_matches_balance
        ):
            return

        conflict = ConflictError(
            "serialized item relocation does not match source state or target balance",
            code="INVENTORY_STATE_TARGET_MISMATCH",
            details={
                "balance_id": balance.id,
                "serial_item_id": target.id,
                "expected_target_warehouse_id": balance.warehouse_id,
                "expected_target_location_id": balance.location_id,
                "conflict_object": "serialized_item",
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _require_state_snapshot(
        actor: ActorContext,
        target: InventoryLot | SerializedItem,
        state_mutation: InventoryStateMutation,
        *,
        target_type: str,
        target_id: int,
        allowed_fields: frozenset[str],
    ) -> None:
        requested_fields = set(state_mutation.state_before)
        unsupported_fields = sorted(requested_fields - allowed_fields)
        if unsupported_fields:
            raise BusinessValidationError(
                "inventory state mutation contains unsupported fields",
                code="INVENTORY_STATE_FIELD_INVALID",
                details={
                    "target_type": target_type,
                    "target_id": target_id,
                    "fields": unsupported_fields,
                },
            )
        actual_state = {
            field_name: getattr(target, field_name)
            for field_name in state_mutation.state_before
        }
        if actual_state != state_mutation.state_before:
            conflict = ConflictError(
                "inventory state version conflict",
                code="INVENTORY_STATE_CONFLICT",
                details={
                    "target_type": target_type,
                    "target_id": target_id,
                    "expected_state": state_mutation.state_before,
                    "actual_state": actual_state,
                    "conflict_object": target_type,
                    "retryable": True,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

    @staticmethod
    def _require_role(actor: ActorContext, required_role: MaintenanceRole) -> None:
        if _ROLE_RANK[actor.role] < _ROLE_RANK[required_role]:
            raise InsufficientMaintenanceRoleError(
                required_role=required_role.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    def response_extension(
        self,
        session: Session,
        actor: ActorContext,
        *,
        transaction_id: int,
        name: str,
    ) -> dict | None:
        transaction = self.transaction_repository.get_transaction(
            session,
            actor.tenant_id,
            transaction_id,
        )
        if transaction is None:
            raise NotFoundError(
                "inventory_transaction",
                transaction_id,
            )
        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            return None
        extensions = snapshot.get("_extensions")
        if not isinstance(extensions, dict):
            return None
        value = extensions.get(name)
        return deepcopy(value) if isinstance(value, dict) else None

    def store_response_extension(
        self,
        session: Session,
        actor: ActorContext,
        *,
        transaction_id: int,
        name: str,
        value: dict,
    ) -> None:
        transaction = self.transaction_repository.get_transaction(
            session,
            actor.tenant_id,
            transaction_id,
        )
        if transaction is None:
            raise NotFoundError(
                "inventory_transaction",
                transaction_id,
            )
        snapshot = deepcopy(transaction.response_snapshot_json)
        if not isinstance(snapshot, dict):
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
        extensions = snapshot.get("_extensions")
        if not isinstance(extensions, dict):
            extensions = {}
        extensions[name] = deepcopy(value)
        snapshot["_extensions"] = extensions
        transaction.response_snapshot_json = snapshot
        session.flush()

    @staticmethod
    def _is_idempotency_constraint_violation(exc: IntegrityError) -> bool:
        driver_error = exc.orig
        diagnostic = getattr(driver_error, "diag", None)
        if (
            getattr(diagnostic, "constraint_name", None)
            == _IDEMPOTENCY_CONSTRAINT
        ):
            return True
        return str(driver_error) == _SQLITE_IDEMPOTENCY_UNIQUE_ERROR

    @staticmethod
    def _ensure_savepoint_parent_transaction(session: Session) -> None:
        if session.get_bind().dialect.name == "sqlite":
            session.execute(
                update(InventoryBalance)
                .where(false())
                .values(version=InventoryBalance.version)
            )

    @staticmethod
    def _replay(
        actor: ActorContext,
        transaction: InventoryTransaction,
        request_hash: str,
    ) -> InventoryTransactionRead:
        if transaction.request_hash != request_hash:
            conflict = ConflictError(
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict
        if transaction.response_snapshot_json is None:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
        try:
            return InventoryTransactionRead.model_validate(
                transaction.response_snapshot_json
            ).model_copy(deep=True)
        except ValidationError as exc:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            ) from exc

    @staticmethod
    def _read_transaction(
        transaction: InventoryTransaction,
        entries: list,
    ) -> InventoryTransactionRead:
        return InventoryTransactionRead.model_validate(
            {
                "id": transaction.id,
                "tenant_id": transaction.tenant_id,
                "operation_type": transaction.operation_type,
                "status": transaction.status,
                "idempotency_key": transaction.idempotency_key,
                "request_hash": transaction.request_hash,
                "reason": transaction.reason,
                "actor_user_id": transaction.actor_user_id,
                "actor_roles_json": transaction.actor_roles_json,
                "request_id": transaction.request_id,
                "version": transaction.version,
                "completed_at": transaction.completed_at,
                "entries": [
                    InventoryLedgerEntryRead.model_validate(entry)
                    for entry in entries
                ],
            }
        )

    @staticmethod
    def _balance_values(balance: InventoryBalance) -> tuple[Decimal, ...]:
        return (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
        )

    @staticmethod
    def _delta_values(deltas: InventoryQuantityDelta) -> tuple[Decimal, ...]:
        return (
            deltas.on_hand,
            deltas.reserved,
            deltas.damaged,
            deltas.quarantined,
            deltas.in_transit,
        )

    @staticmethod
    def _write_balance(balance: InventoryBalance, values: tuple[Decimal, ...]) -> None:
        (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
        ) = values

    @staticmethod
    def _validate_result(values: tuple[Decimal, ...]) -> None:
        if any(value < 0 for value in values):
            raise BusinessValidationError(
                "inventory quantities must not be negative",
                code="INVENTORY_NEGATIVE_QUANTITY",
            )
        if any(value > MAX_INVENTORY_QUANTITY for value in values):
            raise BusinessValidationError(
                "inventory quantities must fit Numeric(18,4)",
                code="INVENTORY_QUANTITY_OUT_OF_RANGE",
            )
        on_hand, reserved, damaged, quarantined, _ = values
        if reserved + damaged + quarantined > on_hand:
            raise BusinessValidationError(
                "allocated inventory must not exceed on-hand quantity",
                code="INVENTORY_ALLOCATION_EXCEEDS_ON_HAND",
            )

    @staticmethod
    def _require_version(
        actor: ActorContext,
        balance: InventoryBalance,
        *,
        expected_version: int,
    ) -> None:
        if balance.version != expected_version:
            conflict = ConflictError(
                "inventory balance version conflict",
                code="INVENTORY_VERSION_CONFLICT",
                details={
                    "balance_id": balance.id,
                    "expected_version": expected_version,
                    "actual_version": balance.version,
                    "conflict_object": "inventory_balance",
                    "retryable": True,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        clean_key = idempotency_key.strip()
        if not clean_key:
            raise BusinessValidationError(
                "idempotency key is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
        if len(clean_key) > 128:
            raise BusinessValidationError(
                "idempotency key is invalid",
                code="INVALID_IDEMPOTENCY_KEY",
            )
        return clean_key

    @staticmethod
    def _normalize_reason(reason: str) -> str:
        clean_reason = reason.strip()
        if not clean_reason:
            raise BusinessValidationError(
                "reason must not be blank",
                code="INVENTORY_REASON_REQUIRED",
            )
        if len(clean_reason) > 500:
            raise BusinessValidationError(
                "reason is invalid",
                code="INVENTORY_REASON_INVALID",
            )
        return clean_reason

    @staticmethod
    def _require_contributor(actor: ActorContext) -> None:
        if actor.role not in {MaintenanceRole.CONTRIBUTOR, MaintenanceRole.ADMIN}:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.CONTRIBUTOR.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _require_admin(actor: ActorContext) -> None:
        if actor.role is not MaintenanceRole.ADMIN:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )


def decimal_state_from_values(values: tuple[Decimal, ...]) -> dict[str, str]:
    return decimal_state(
        on_hand=values[0],
        reserved=values[1],
        damaged=values[2],
        quarantined=values[3],
        in_transit=values[4],
    )


inventory_transaction_service = InventoryTransactionService()
