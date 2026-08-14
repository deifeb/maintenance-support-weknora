from __future__ import annotations

import hashlib
import hmac
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    InventoryLedgerEntry,
    InventoryLot,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    InventoryTransfer,
    InventoryTransferLine,
)
from app.models.mixins import utc_now
from app.repositories.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
)
from app.schemas.inventory_ledger import (
    InventoryQuantityDelta,
    InventoryTransactionRead,
)
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
    InventoryOperationPreviewRead,
    InventoryStateMutation,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_transaction_service import (
    InventoryTransactionService,
)
from app.services.snapshot_service import snapshot_service

_DEFAULT_PREVIEW_TTL = timedelta(minutes=15)


class InventoryOperationService:
    def __init__(
        self,
        *,
        transaction_repository: InventoryTransactionRepository | None = None,
        ledger_repository: InventoryLedgerRepository | None = None,
        transaction_service: InventoryTransactionService | None = None,
        preview_ttl: timedelta = _DEFAULT_PREVIEW_TTL,
    ) -> None:
        self.transaction_repository = (
            transaction_repository or InventoryTransactionRepository()
        )
        self.ledger_repository = (
            ledger_repository or InventoryLedgerRepository()
        )
        self.transaction_service = (
            transaction_service
            or InventoryTransactionService(
                transaction_repository=self.transaction_repository,
                ledger_repository=self.ledger_repository,
            )
        )
        self.preview_ttl = preview_ttl

    def preview(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command: Any,
        idempotency_key: str,
    ) -> InventoryOperationPreviewRead:
        payload = self._command_payload(command)
        operation_type = self._operation_type(payload)
        self._require_adjust_admin(
            actor,
            operation_type=operation_type,
        )
        reason = self._reason(payload)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = snapshot_service.canonical_hash(payload)

        existing = self.transaction_repository.get_idempotent(
            session,
            actor.tenant_id,
            operation_type,
            clean_key,
        )
        if existing is not None:
            return self._replay_preview(
                actor,
                existing,
                request_hash=request_hash,
            )

        confirmation_token = secrets.token_urlsafe(32)
        confirmation_token_hash = hashlib.sha256(
            confirmation_token.encode("utf-8")
        ).hexdigest()
        confirmation_expires_at = utc_now() + self.preview_ttl

        transaction = self.transaction_repository.create_transaction(
            session,
            actor=actor,
            operation_type=operation_type,
            idempotency_key=clean_key,
            request_hash=request_hash,
            reason=reason,
            status="PREVIEWED",
        )
        transaction.confirmation_token_hash = confirmation_token_hash
        transaction.confirmation_expires_at = confirmation_expires_at

        stored_preview = InventoryOperationPreviewRead(
            transaction_id=transaction.id,
            operation_type=operation_type,
            transaction_version=transaction.version,
            confirmation_token=None,
            confirmation_expires_at=confirmation_expires_at,
        )

        snapshot = stored_preview.model_dump(mode="json")
        snapshot["_extensions"] = {
            "preview_command": deepcopy(payload),
        }
        transaction.response_snapshot_json = snapshot
        session.flush()

        return stored_preview.model_copy(
            update={"confirmation_token": confirmation_token}
        )

    def execute(
        self,
        session: Session,
        actor: ActorContext,
        transaction_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> InventoryTransactionRead:
        payload = self._command_payload(command)
        clean_key = self._normalize_idempotency_key(
            idempotency_key
        )
        execute_request_hash = snapshot_service.canonical_hash(
            payload
        )

        transaction = self.transaction_repository.lock_transaction(
            session,
            actor.tenant_id,
            transaction_id,
        )
        if transaction is None:
            error = NotFoundError(
                "inventory_transaction",
                transaction_id,
            )
            error.request_id = actor.request_id
            raise error

        self._require_adjust_admin(
            actor,
            operation_type=transaction.operation_type,
        )
        self._require_reverse_admin(
            actor,
            operation_type=transaction.operation_type,
        )

        if transaction.status != "PREVIEWED":
            return self._replay_execute(
                actor,
                transaction,
                idempotency_key=clean_key,
                request_hash=execute_request_hash,
            )

        expected_transaction_version = (
            self._required_positive_int(
                payload,
                "expected_transaction_version",
            )
        )
        self._require_transaction_version(
            actor,
            transaction,
            expected_version=expected_transaction_version,
        )

        confirmation_token = self._confirmation_token(
            payload
        )
        self._require_confirmation_token(
            transaction,
            confirmation_token,
        )
        self._require_confirmation_not_expired(
            transaction
        )

        preview_command = self._preview_command(
            actor,
            transaction,
        )
        operation_type = self._operation_type(
            preview_command
        )

        if operation_type == "REVERSE":
            result = self._execute_reverse(
                session,
                actor,
                transaction,
                preview_command=preview_command,
            )
        else:
            balance_id = self._required_positive_int(
                preview_command,
                "balance_id",
            )
            expected_balance_version = (
                self._required_positive_int(
                    preview_command,
                    "expected_balance_version",
                )
            )

            balance = self.ledger_repository.get_balance(
                session,
                actor.tenant_id,
                balance_id,
            )
            if balance is None:
                error = NotFoundError(
                    "inventory_balance",
                    balance_id,
                )
                error.request_id = actor.request_id
                raise error

            session.refresh(balance)

            if balance.version != expected_balance_version:
                conflict = ConflictError(
                    "inventory balance version conflict",
                    code="INVENTORY_VERSION_CONFLICT",
                    details={
                        "balance_id": balance.id,
                        "expected_version": expected_balance_version,
                        "actual_version": balance.version,
                        "conflict_object": "inventory_balance",
                        "retryable": True,
                    },
                )
                conflict.request_id = actor.request_id
                raise conflict

            operation_type = self._operation_type(
                preview_command
            )

            if operation_type == "ADJUST":
                plan = self._adjust_plan(
                    preview_command
                )

                try:
                    result = (
                        self.transaction_service.apply_plan_to_transaction(
                            session,
                            actor,
                            transaction=transaction,
                            plan=plan,
                            required_role=MaintenanceRole.ADMIN,
                        )
                    )
                except BusinessValidationError as exc:
                    if exc.code != "INVENTORY_NEGATIVE_QUANTITY":
                        raise

                    error = BusinessValidationError(
                        "inventory balance cannot become negative",
                        code="INVENTORY_NEGATIVE_BALANCE",
                        details=exc.details,
                    )
                    error.request_id = actor.request_id
                    raise error from exc

            else:
                if operation_type not in {
                    "FREEZE",
                    "UNFREEZE",
                }:
                    raise NotImplementedError(
                        "Task 6 successful execute is implemented "
                        "only for ADJUST, FREEZE and UNFREEZE"
                    )

                lot_id = self._required_positive_int(
                    preview_command,
                    "lot_id",
                )
                expected_lot_version = self._required_positive_int(
                    preview_command,
                    "expected_lot_version",
                )

                lot = session.scalar(
                    select(InventoryLot)
                    .where(
                        InventoryLot.tenant_id
                        == actor.tenant_id,
                        InventoryLot.id == lot_id,
                    )
                    .execution_options(
                        populate_existing=True
                    )
                )
                if lot is None:
                    error = NotFoundError(
                        "inventory_lot",
                        lot_id,
                    )
                    error.request_id = actor.request_id
                    raise error

                session.refresh(lot)

                self._require_lot_version(
                    actor,
                    lot,
                    expected_version=expected_lot_version,
                )
                self._require_lot_operation_state(
                    actor,
                    lot,
                    operation_type=operation_type,
                )

                plan = self._lot_freeze_state_plan(
                    preview_command,
                    lot,
                )

                def validate_state_targets(
                    lots_by_id: dict[int, InventoryLot],
                    serial_items_by_id: dict[int, Any],
                ) -> None:
                    del serial_items_by_id

                    locked_lot = lots_by_id[lot_id]

                    # lock_lots() has already acquired the row lock.
                    session.refresh(locked_lot)

                    self._require_lot_version(
                        actor,
                        locked_lot,
                        expected_version=expected_lot_version,
                    )
                    self._require_lot_operation_state(
                        actor,
                        locked_lot,
                        operation_type=operation_type,
                    )

                result = (
                    self.transaction_service.apply_plan_to_transaction(
                        session,
                        actor,
                        transaction=transaction,
                        plan=plan,
                        required_role=MaintenanceRole.ADMIN,
                        validate_state_targets=validate_state_targets,
                    )
                )

        self.transaction_service.store_response_extension(
            session,
            actor,
            transaction_id=transaction.id,
            name="execute",
            value={
                "idempotency_key": clean_key,
                "request_hash": execute_request_hash,
            },
        )

        return result
    def preview_reverse(
        self,
        session: Session,
        actor: ActorContext,
        transaction_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> InventoryOperationPreviewRead:
        payload = self._command_payload(command)

        self._require_reverse_admin(
            actor,
            operation_type="REVERSE",
        )

        expected_original_version = (
            self._required_positive_int(
                payload,
                "expected_transaction_version",
            )
        )

        original = self._reverse_original(
            session,
            actor,
            transaction_id,
        )

        self._require_transaction_version(
            actor,
            original,
            expected_version=expected_original_version,
        )
        self._require_reverse_available(
            actor,
            original,
        )

        entries = self._reverse_entries(
            session,
            actor,
            original.id,
        )
        reason = self._reason(payload)

        # Preview validates current business facts but does not
        # retain executable deltas. Execute rebuilds this plan.
        self._reverse_plan(
            session,
            actor,
            original,
            entries,
            reason=reason,
        )

        preview_command = {
            "operation_type": "REVERSE",
            "original_transaction_id": original.id,
            "expected_original_transaction_version": (
                original.version
            ),
            "reason": reason,
        }

        return self.preview(
            session,
            actor,
            command=preview_command,
            idempotency_key=idempotency_key,
        )


    @staticmethod
    def _require_reverse_admin(
        actor: ActorContext,
        *,
        operation_type: str,
    ) -> None:
        if operation_type != "REVERSE":
            return

        if actor.role is MaintenanceRole.ADMIN:
            return

        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.ADMIN.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )

    def _reverse_original(
        self,
        session: Session,
        actor: ActorContext,
        transaction_id: int,
    ) -> InventoryTransaction:
        original = (
            self.transaction_repository.get_transaction(
                session,
                actor.tenant_id,
                transaction_id,
            )
        )

        if original is None:
            error = NotFoundError(
                "inventory_transaction",
                transaction_id,
            )
            error.request_id = actor.request_id
            raise error

        return original

    @staticmethod
    def _reverse_state_conflict(
        actor: ActorContext,
        *,
        conflict_object: str,
        object_id: int,
        suggested_action: str,
    ) -> None:
        error = ConflictError(
            "inventory operation state conflict",
            code="INVENTORY_OPERATION_STATE_CONFLICT",
            details={
                "conflict_object": conflict_object,
                "object_id": object_id,
                "expected_version": None,
                "actual_version": None,
                "affected_lines": [],
                "retryable": False,
                "suggested_action": suggested_action,
            },
        )
        error.request_id = actor.request_id
        raise error

    def _require_reverse_available(
        self,
        actor: ActorContext,
        original: InventoryTransaction,
    ) -> None:
        if original.operation_type == "REVERSE":
            self._reverse_state_conflict(
                actor,
                conflict_object="inventory_transaction",
                object_id=original.id,
                suggested_action=(
                    "select the original non-REVERSE transaction"
                ),
            )

        if original.status not in {
            "COMPLETED",
            "PARTIALLY_COMPLETED",
        }:
            self._reverse_state_conflict(
                actor,
                conflict_object="inventory_transaction",
                object_id=original.id,
                suggested_action=(
                    "reverse only a completed inventory transaction"
                ),
            )

        if original.reversed_transaction_id is not None:
            self._reverse_state_conflict(
                actor,
                conflict_object="inventory_transaction",
                object_id=original.id,
                suggested_action=(
                    "use the existing reversal transaction"
                ),
            )

    @staticmethod
    def _reverse_entries(
        session: Session,
        actor: ActorContext,
        transaction_id: int,
    ) -> list[InventoryLedgerEntry]:
        entries = list(
            session.scalars(
                select(InventoryLedgerEntry)
                .where(
                    InventoryLedgerEntry.tenant_id
                    == actor.tenant_id,
                    InventoryLedgerEntry.transaction_id
                    == transaction_id,
                )
                .order_by(InventoryLedgerEntry.id)
            )
        )

        if not entries:
            error = ConflictError(
                "inventory transaction has no reversible ledger entries",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction_id,
                    "expected_version": None,
                    "actual_version": None,
                    "affected_lines": [],
                    "retryable": False,
                    "suggested_action": (
                        "select a transaction with ledger entries"
                    ),
                },
            )
            error.request_id = actor.request_id
            raise error

        return entries

    def _require_reverse_dependencies(
        self,
        session: Session,
        actor: ActorContext,
        *,
        balance_ids: tuple[int, ...],
    ) -> None:
        reservation_id = session.scalar(
            select(InventoryReservation.id)
            .join(
                InventoryReservationLine,
                InventoryReservationLine.reservation_id
                == InventoryReservation.id,
            )
            .where(
                InventoryReservation.tenant_id
                == actor.tenant_id,
                InventoryReservationLine.tenant_id
                == actor.tenant_id,
                InventoryReservationLine.balance_id.in_(
                    balance_ids
                ),
                InventoryReservation.status.in_(
                    (
                        "ACTIVE",
                        "PARTIALLY_ISSUED",
                        "FULFILLED",
                    )
                ),
            )
            .order_by(InventoryReservation.id)
            .limit(1)
        )

        if reservation_id is not None:
            self._reverse_state_conflict(
                actor,
                conflict_object="inventory_reservation",
                object_id=reservation_id,
                suggested_action=(
                    "resolve the dependent reservation first"
                ),
            )

        transfer_id = session.scalar(
            select(InventoryTransfer.id)
            .join(
                InventoryTransferLine,
                InventoryTransferLine.transfer_id
                == InventoryTransfer.id,
            )
            .where(
                InventoryTransfer.tenant_id
                == actor.tenant_id,
                InventoryTransferLine.tenant_id
                == actor.tenant_id,
                InventoryTransferLine.source_balance_id.in_(
                    balance_ids
                ),
                InventoryTransfer.status.in_(
                    (
                        "DRAFT",
                        "DISPATCHED",
                        "PARTIALLY_RECEIVED",
                        "COMPLETED",
                    )
                ),
            )
            .order_by(InventoryTransfer.id)
            .limit(1)
        )

        if transfer_id is None:
            transfer_id = session.scalar(
                select(InventoryTransfer.id)
                .join(
                    InventoryTransferLine,
                    InventoryTransferLine.transfer_id
                    == InventoryTransfer.id,
                )
                .where(
                    InventoryTransfer.tenant_id
                    == actor.tenant_id,
                    InventoryTransferLine.tenant_id
                    == actor.tenant_id,
                    InventoryTransferLine.target_balance_id.in_(
                        balance_ids
                    ),
                    InventoryTransfer.status.in_(
                        (
                            "DRAFT",
                            "DISPATCHED",
                            "PARTIALLY_RECEIVED",
                            "COMPLETED",
                        )
                    ),
                )
                .order_by(InventoryTransfer.id)
                .limit(1)
            )

        if transfer_id is not None:
            self._reverse_state_conflict(
                actor,
                conflict_object="inventory_transfer",
                object_id=transfer_id,
                suggested_action=(
                    "resolve the dependent transfer first"
                ),
            )

    @staticmethod
    def _validate_reverse_projection(
        actor: ActorContext,
        *,
        entries: list[InventoryLedgerEntry],
        balances_by_id: dict[int, Any],
    ) -> None:
        quantity_fields = (
            ("on_hand", "on_hand_quantity", "on_hand_delta"),
            ("reserved", "reserved_quantity", "reserved_delta"),
            ("damaged", "damaged_quantity", "damaged_delta"),
            (
                "quarantined",
                "quarantined_quantity",
                "quarantined_delta",
            ),
            (
                "in_transit",
                "in_transit_quantity",
                "in_transit_delta",
            ),
        )

        for entry in entries:
            balance = balances_by_id[entry.balance_id]

            projected = {}

            for (
                public_name,
                balance_attr,
                delta_attr,
            ) in quantity_fields:
                current = getattr(
                    balance,
                    balance_attr,
                )
                reverse_delta = -getattr(
                    entry,
                    delta_attr,
                )
                value = current + reverse_delta

                projected[public_name] = value

                if value < 0:
                    error = BusinessValidationError(
                        "inventory balance cannot become negative",
                        code="INVENTORY_NEGATIVE_BALANCE",
                        details={
                            "balance_id": balance.id,
                            "field": public_name,
                            "current_quantity": str(current),
                            "reverse_delta": str(reverse_delta),
                            "projected_quantity": str(value),
                            "conflict_object": (
                                "inventory_balance"
                            ),
                            "retryable": False,
                        },
                    )
                    error.request_id = actor.request_id
                    raise error

            allocated = (
                projected["reserved"]
                + projected["damaged"]
                + projected["quarantined"]
            )

            if allocated > projected["on_hand"]:
                error = ConflictError(
                    "reverse would violate inventory allocation state",
                    code="INVENTORY_OPERATION_STATE_CONFLICT",
                    details={
                        "conflict_object": "inventory_balance",
                        "object_id": balance.id,
                        "expected_version": balance.version,
                        "actual_version": balance.version,
                        "affected_lines": [entry.id],
                        "retryable": False,
                        "suggested_action": (
                            "resolve dependent allocation state first"
                        ),
                    },
                )
                error.request_id = actor.request_id
                raise error

    def _execute_reverse(
        self,
        session: Session,
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        preview_command: dict[str, Any],
    ) -> InventoryTransactionRead:
        original_transaction_id = (
            self._required_positive_int(
                preview_command,
                "original_transaction_id",
            )
        )
        expected_original_version = (
            self._required_positive_int(
                preview_command,
                "expected_original_transaction_version",
            )
        )
        reason = self._reason(
            preview_command
        )

        original = (
            self.transaction_repository.lock_transaction(
                session,
                actor.tenant_id,
                original_transaction_id,
            )
        )

        if original is None:
            error = NotFoundError(
                "inventory_transaction",
                original_transaction_id,
            )
            error.request_id = actor.request_id
            raise error

        self._require_transaction_version(
            actor,
            original,
            expected_version=expected_original_version,
        )
        self._require_reverse_available(
            actor,
            original,
        )

        entries = self._reverse_entries(
            session,
            actor,
            original.id,
        )

        plan, balances_by_id = (
            self._reverse_plan(
                session,
                actor,
                original,
                entries,
                reason=reason,
            )
        )

        def validate_reverse_state(
            lots_by_id: dict[int, InventoryLot],
            serial_items_by_id: dict[int, Any],
        ) -> None:
            del lots_by_id
            del serial_items_by_id

            # Original transaction is already locked.
            session.refresh(original)

            self._require_reverse_available(
                actor,
                original,
            )

            self._require_reverse_dependencies(
                session,
                actor,
                balance_ids=tuple(
                    balances_by_id
                ),
            )

            # apply_plan_to_transaction() has already locked all
            # balances in deterministic balance-id order.
            for balance in balances_by_id.values():
                session.refresh(balance)

            self._validate_reverse_projection(
                actor,
                entries=entries,
                balances_by_id=balances_by_id,
            )

        try:
            result = (
                self.transaction_service.apply_plan_to_transaction(
                    session,
                    actor,
                    transaction=transaction,
                    plan=plan,
                    required_role=MaintenanceRole.ADMIN,
                    validate_state_targets=validate_reverse_state,
                )
            )
        except BusinessValidationError as exc:
            if exc.code != "INVENTORY_NEGATIVE_QUANTITY":
                raise

            error = BusinessValidationError(
                "inventory balance cannot become negative",
                code="INVENTORY_NEGATIVE_BALANCE",
                details=exc.details,
            )
            error.request_id = actor.request_id
            raise error from exc

        # Original business transaction and original ledger entries
        # remain unchanged. Only reversal-link metadata is added.
        original.reversed_transaction_id = transaction.id
        original.version += 1

        # Bidirectional transaction association.
        transaction.reversed_transaction_id = original.id

        original_snapshot = deepcopy(
            original.response_snapshot_json
            or {}
        )
        extensions = deepcopy(
            original_snapshot.get(
                "_extensions"
            )
            or {}
        )
        extensions["reversal"] = {
            "transaction_id": transaction.id,
        }
        original_snapshot[
            "_extensions"
        ] = extensions
        original.response_snapshot_json = (
            original_snapshot
        )

        session.flush()

        return result

    def _reverse_plan(
        self,
        session: Session,
        actor: ActorContext,
        original: InventoryTransaction,
        entries: list[InventoryLedgerEntry],
        *,
        reason: str,
    ) -> tuple[InventoryMutationPlan, dict[int, Any]]:
        balance_ids = tuple(
            dict.fromkeys(
                entry.balance_id
                for entry in entries
            )
        )

        self._require_reverse_dependencies(
            session,
            actor,
            balance_ids=balance_ids,
        )

        balances_by_id: dict[int, Any] = {}

        for balance_id in balance_ids:
            balance = self.ledger_repository.get_balance(
                session,
                actor.tenant_id,
                balance_id,
            )

            if balance is None:
                error = NotFoundError(
                    "inventory_balance",
                    balance_id,
                )
                error.request_id = actor.request_id
                raise error

            session.refresh(balance)
            balances_by_id[balance_id] = balance

        self._validate_reverse_projection(
            actor,
            entries=entries,
            balances_by_id=balances_by_id,
        )

        mutations = tuple(
            InventoryBalanceMutation(
                balance_id=entry.balance_id,
                expected_version=(
                    balances_by_id[
                        entry.balance_id
                    ].version
                ),
                deltas=InventoryQuantityDelta(
                    on_hand=-entry.on_hand_delta,
                    reserved=-entry.reserved_delta,
                    damaged=-entry.damaged_delta,
                    quarantined=(
                        -entry.quarantined_delta
                    ),
                    in_transit=(
                        -entry.in_transit_delta
                    ),
                ),
            )
            for entry in entries
        )

        plan = InventoryMutationPlan(
            operation_type="REVERSE",
            reference_type="inventory_transaction",
            reference_id=str(original.id),
            reason=reason,
            mutations=mutations,
            audit_context={
                "original_transaction_id": original.id,
                "original_entry_ids": [
                    entry.id
                    for entry in entries
                ],
            },
        )

        return plan, balances_by_id

    @classmethod
    def _adjust_plan(
        cls,
        preview_command: dict[str, Any],
    ) -> InventoryMutationPlan:
        operation_type = cls._operation_type(
            preview_command
        )
        if operation_type != "ADJUST":
            raise AssertionError(
                "ADJUST planner received another operation"
            )

        balance_id = cls._required_positive_int(
            preview_command,
            "balance_id",
        )
        expected_balance_version = (
            cls._required_positive_int(
                preview_command,
                "expected_balance_version",
            )
        )
        reason = cls._reason(
            preview_command
        )

        raw_deltas = preview_command.get(
            "deltas"
        )
        if not isinstance(raw_deltas, dict):
            raise BusinessValidationError(
                "inventory adjustment deltas are required",
                code="INVENTORY_ADJUSTMENT_INVALID",
            )

        deltas = InventoryQuantityDelta.model_validate(
            raw_deltas
        )

        return InventoryMutationPlan(
            operation_type="ADJUST",
            reason=reason,
            mutations=(
                InventoryBalanceMutation(
                    balance_id=balance_id,
                    expected_version=expected_balance_version,
                    deltas=deltas,
                ),
            ),
            audit_context={
                "high_risk_preview": True,
            },
        )

    @staticmethod
    def _require_adjust_admin(
        actor: ActorContext,
        *,
        operation_type: str,
    ) -> None:
        if operation_type != "ADJUST":
            return

        if actor.role is MaintenanceRole.ADMIN:
            return

        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.ADMIN.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )
    @classmethod
    def _lot_freeze_state_plan(
        cls,
        preview_command: dict[str, Any],
        lot: InventoryLot,
    ) -> InventoryMutationPlan:
        operation_type = cls._operation_type(
            preview_command
        )
        if operation_type not in {
            "FREEZE",
            "UNFREEZE",
        }:
            raise NotImplementedError(
                "Task 6 successful execute is implemented "
                "only for FREEZE and UNFREEZE"
            )

        reason = cls._reason(preview_command)
        balance_id = cls._required_positive_int(
            preview_command,
            "balance_id",
        )
        expected_balance_version = (
            cls._required_positive_int(
                preview_command,
                "expected_balance_version",
            )
        )
        lot_id = cls._required_positive_int(
            preview_command,
            "lot_id",
        )

        state_before = {
            "is_frozen": lot.is_frozen,
            "freeze_reason": lot.freeze_reason,
        }

        if operation_type == "FREEZE":
            state_after = {
                "is_frozen": True,
                "freeze_reason": reason,
            }
        else:
            state_after = {
                "is_frozen": False,
                "freeze_reason": None,
            }

        return InventoryMutationPlan(
            operation_type=operation_type,
            reason=reason,
            mutations=(
                InventoryBalanceMutation(
                    balance_id=balance_id,
                    expected_version=expected_balance_version,
                    deltas=InventoryQuantityDelta(),
                    state_mutations=(
                        InventoryStateMutation(
                            lot_id=lot_id,
                            state_before=state_before,
                            state_after=state_after,
                        ),
                    ),
                ),
            ),
            audit_context={
                "high_risk_preview": True,
            },
        )

    @staticmethod
    def _require_lot_version(
        actor: ActorContext,
        lot: InventoryLot,
        *,
        expected_version: int,
    ) -> None:
        if lot.version == expected_version:
            return

        conflict = ConflictError(
            "inventory lot version conflict",
            code="INVENTORY_VERSION_CONFLICT",
            details={
                "lot_id": lot.id,
                "expected_version": expected_version,
                "actual_version": lot.version,
                "conflict_object": "inventory_lot",
                "retryable": True,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _require_lot_operation_state(
        actor: ActorContext,
        lot: InventoryLot,
        *,
        operation_type: str,
    ) -> None:
        if operation_type == "FREEZE":
            expected_is_frozen = False
        elif operation_type == "UNFREEZE":
            expected_is_frozen = True
        else:
            raise NotImplementedError(
                "Task 6 successful execute is implemented "
                "only for FREEZE and UNFREEZE"
            )

        if lot.is_frozen is expected_is_frozen:
            return

        conflict = ConflictError(
            "inventory operation state conflict",
            code="INVENTORY_OPERATION_STATE_CONFLICT",
            details={
                "lot_id": lot.id,
                "operation_type": operation_type,
                "expected_is_frozen": expected_is_frozen,
                "actual_is_frozen": lot.is_frozen,
                "conflict_object": "inventory_lot",
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict
    @staticmethod
    def _replay_execute(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> InventoryTransactionRead:
        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            conflict = ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        extensions = snapshot.get("_extensions")
        execute_extension = (
            extensions.get("execute")
            if isinstance(extensions, dict)
            else None
        )

        if not isinstance(execute_extension, dict):
            conflict = ConflictError(
                "inventory operation state conflict",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "transaction_id": transaction.id,
                    "status": transaction.status,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        if (
            execute_extension.get("idempotency_key")
            != idempotency_key
            or execute_extension.get("request_hash")
            != request_hash
        ):
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

        public_snapshot = deepcopy(snapshot)
        public_snapshot.pop("_extensions", None)

        try:
            return InventoryTransactionRead.model_validate(
                public_snapshot
            ).model_copy(deep=True)
        except ValidationError as exc:
            conflict = ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict from exc
    @staticmethod
    def _command_payload(command: Any) -> dict[str, Any]:
        if isinstance(command, BaseModel):
            raw = command.model_dump(mode="json")
        elif isinstance(command, dict):
            raw = deepcopy(command)
        else:
            raise BusinessValidationError(
                "inventory operation command must be an object"
            )

        normalized = snapshot_service.normalize(raw)
        if not isinstance(normalized, dict):
            raise BusinessValidationError(
                "inventory operation command must be an object"
            )
        return normalized

    @staticmethod
    def _operation_type(payload: dict[str, Any]) -> str:
        operation_type = payload.get("operation_type")
        if not isinstance(operation_type, str) or not operation_type.strip():
            raise BusinessValidationError(
                "inventory operation type is required"
            )
        return operation_type.strip()

    @staticmethod
    def _reason(payload: dict[str, Any]) -> str:
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise BusinessValidationError(
                "reason must not be blank",
                code="INVENTORY_REASON_REQUIRED",
            )
        clean_reason = reason.strip()
        if len(clean_reason) > 500:
            raise BusinessValidationError(
                "reason is invalid",
                code="INVENTORY_REASON_INVALID",
            )
        return clean_reason

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
    def _required_positive_int(
        payload: dict[str, Any],
        field_name: str,
    ) -> int:
        value = payload.get(field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise BusinessValidationError(
                f"{field_name} must be a positive integer"
            )
        return value

    @staticmethod
    def _confirmation_token(
        payload: dict[str, Any],
    ) -> str:
        token = payload.get("confirmation_token")
        if not isinstance(token, str) or not token:
            raise BusinessValidationError(
                "confirmation token is required"
            )
        return token

    @staticmethod
    def _require_transaction_version(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        expected_version: int,
    ) -> None:
        if transaction.version == expected_version:
            return

        conflict = ConflictError(
            "inventory transaction version conflict",
            details={
                "transaction_id": transaction.id,
                "expected_version": expected_version,
                "actual_version": transaction.version,
                "conflict_object": "inventory_transaction",
                "retryable": True,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _require_confirmation_token(
        transaction: InventoryTransaction,
        token: str,
    ) -> None:
        stored_hash = transaction.confirmation_token_hash
        presented_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        if (
            not isinstance(stored_hash, str)
            or not hmac.compare_digest(
                stored_hash,
                presented_hash,
            )
        ):
            raise BusinessValidationError(
                "confirmation token is invalid"
            )

    @classmethod
    def _require_confirmation_not_expired(
        cls,
        transaction: InventoryTransaction,
    ) -> None:
        expires_at = transaction.confirmation_expires_at
        if expires_at is None:
            raise ConflictError(
                "confirmation expiry is unavailable",
                details={
                    "transaction_id": transaction.id,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )

        if cls._as_utc(expires_at) <= utc_now():
            raise BusinessValidationError(
                "confirmation token has expired"
            )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _preview_command(
        actor: ActorContext,
        transaction: InventoryTransaction,
    ) -> dict[str, Any]:
        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            conflict = ConflictError(
                "preview command is unavailable",
                details={
                    "transaction_id": transaction.id,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        extensions = snapshot.get("_extensions")
        preview_command = (
            extensions.get("preview_command")
            if isinstance(extensions, dict)
            else None
        )
        if not isinstance(preview_command, dict):
            conflict = ConflictError(
                "preview command is unavailable",
                details={
                    "transaction_id": transaction.id,
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        return deepcopy(preview_command)

    @staticmethod
    def _replay_preview(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        request_hash: str,
    ) -> InventoryOperationPreviewRead:
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

        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            conflict = ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        public_snapshot = deepcopy(snapshot)
        public_snapshot.pop("_extensions", None)

        try:
            preview = InventoryOperationPreviewRead.model_validate(
                public_snapshot
            )
        except ValidationError as exc:
            conflict = ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict from exc

        return preview.model_copy(
            update={"confirmation_token": None}
        )