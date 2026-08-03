from __future__ import annotations

from decimal import Decimal
from typing import Literal

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
from app.models import InventoryBalance, InventoryTransaction
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
from app.security.actor import ActorContext, MaintenanceRole
from app.services.snapshot_service import snapshot_service

OperationType = Literal["OPENING", "ADJUST"]


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
        )

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
    ) -> InventoryTransactionRead:
        clean_reason = self._normalize_reason(reason)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        if all(value == 0 for value in self._delta_values(deltas)):
            raise BusinessValidationError(
                "quantity operation requires a nonzero delta",
                code="INVENTORY_ZERO_DELTA",
            )
        request_hash = snapshot_service.canonical_hash(
            {
                "operation_type": operation_type,
                "balance_id": balance_id,
                "expected_version": expected_version,
                "deltas": deltas.model_dump(),
                "reason": clean_reason,
            }
        )

        self._ensure_savepoint_parent_transaction(session)
        try:
            with session.begin_nested():
                existing = self.transaction_repository.get_idempotent(
                    session,
                    actor.tenant_id,
                    operation_type,
                    clean_key,
                )
                if existing is not None:
                    return self._replay(actor, existing, request_hash)

                locked = self.ledger_repository.lock_balances(
                    session,
                    actor.tenant_id,
                    [balance_id],
                )
                if not locked:
                    raise NotFoundError("inventory_balance", balance_id)
                balance = locked[0]
                existing = self.transaction_repository.get_idempotent(
                    session,
                    actor.tenant_id,
                    operation_type,
                    clean_key,
                )
                if existing is not None:
                    return self._replay(actor, existing, request_hash)
                self._require_version(
                    actor,
                    balance,
                    expected_version=expected_version,
                )
                before_version = balance.version
                before_values = self._balance_values(balance)
                after_values = tuple(
                    current + delta
                    for current, delta in zip(
                        before_values,
                        self._delta_values(deltas),
                        strict=True,
                    )
                )
                self._validate_result(after_values)
                state_before = decimal_state_from_values(before_values)
                state_after = decimal_state_from_values(after_values)

                self._write_balance(balance, after_values)
                balance.version = before_version + 1
                transaction = self.transaction_repository.create_transaction(
                    session,
                    actor=actor,
                    operation_type=operation_type,
                    idempotency_key=clean_key,
                    request_hash=request_hash,
                    reason=clean_reason,
                )
                entry = self.transaction_repository.append_entry(
                    session,
                    transaction=transaction,
                    balance=balance,
                    deltas=deltas,
                    state_before=state_before,
                    state_after=state_after,
                    before_balance_version=before_version,
                    resulting_balance_version=balance.version,
                )
                completed_at = utc_now()
                transaction.completed_at = completed_at
                response = self._read_transaction(transaction, [entry])
                snapshot = response.model_dump(mode="json")
                self.transaction_repository.complete(
                    session,
                    transaction,
                    completed_at=completed_at,
                    response_snapshot=snapshot,
                )
                return response
        except IntegrityError as exc:
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
