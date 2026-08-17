from __future__ import annotations

import hashlib
import hmac
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    InventoryStocktake,
    InventoryStocktakeLine,
    InventoryTargetReceipt,
    InventoryTransaction,
)
from app.models.mixins import utc_now
from app.repositories.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from app.repositories.inventory_stocktake_repository import (
    InventoryStocktakeRepository,
)
from app.repositories.inventory_target_receipt_repository import (
    InventoryTargetReceiptRepository,
)
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
    InventoryOperationPreviewRead,
)
from app.schemas.inventory_stocktake import (
    InventoryStocktakeLineRead,
    InventoryStocktakeRead,
    StocktakeCountCommand,
    StocktakeCreateCommand,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_transaction_service import (
    InventoryTransactionService,
)
from app.services.snapshot_service import snapshot_service

_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_CANCELLABLE_STATUSES = frozenset({"DRAFT", "COUNTING", "REVIEWING", "CONFLICTED"})
_DEFAULT_CONFIRM_PREVIEW_TTL = timedelta(minutes=15)


class InventoryStocktakeService:
    def __init__(
        self,
        *,
        stocktake_repository: InventoryStocktakeRepository | None = None,
        receipt_repository: InventoryTargetReceiptRepository | None = None,
        transaction_repository: InventoryTransactionRepository | None = None,
        ledger_repository: InventoryLedgerRepository | None = None,
        transaction_service: InventoryTransactionService | None = None,
        confirm_preview_ttl: timedelta = _DEFAULT_CONFIRM_PREVIEW_TTL,
    ) -> None:
        self.stocktake_repository = (
            stocktake_repository or InventoryStocktakeRepository()
        )
        self.receipt_repository = (
            receipt_repository or InventoryTargetReceiptRepository()
        )
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
        self.confirm_preview_ttl = confirm_preview_ttl

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command: StocktakeCreateCommand | dict[str, Any],
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        parsed = self._create_command(command, actor)
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key("create", clean_key)
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_CREATE",
                "command": parsed.model_dump(mode="json"),
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        if not self.stocktake_repository.scope_exists(
            session,
            actor.tenant_id,
            warehouse_id=parsed.warehouse_id,
            location_id=parsed.location_id,
        ):
            error = NotFoundError(
                "warehouse_location",
                parsed.location_id,
            )
            error.request_id = actor.request_id
            raise error

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            balances = self.stocktake_repository.list_scope_balances(
                session,
                actor.tenant_id,
                warehouse_id=parsed.warehouse_id,
                location_id=parsed.location_id,
            )
            stocktake = self.stocktake_repository.create(
                session,
                actor=actor,
                warehouse_id=parsed.warehouse_id,
                location_id=parsed.location_id,
                snapshot_at=utc_now(),
            )
            lines = self.stocktake_repository.create_lines(
                session,
                stocktake=stocktake,
                balances=balances,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def start(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
            expected_version=expected_version,
        )

        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key("start", clean_key)
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_START",
                "stocktake_id": stocktake_id,
                "expected_version": expected_version,
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=expected_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"DRAFT"},
            )

            stocktake.status = "COUNTING"
            stocktake.version += 1
            session.flush()

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def record_count(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        line_id: int,
        *,
        command: StocktakeCountCommand | dict[str, Any],
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
            line_id=line_id,
        )
        parsed = self._count_command(command, actor)
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key("record-count", clean_key)
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_RECORD_COUNT",
                "stocktake_id": stocktake_id,
                "line_id": line_id,
                "command": parsed.model_dump(mode="json"),
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=parsed.expected_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"COUNTING"},
            )

            line = self.stocktake_repository.lock_line(
                session,
                actor.tenant_id,
                stocktake.id,
                line_id,
            )
            if line is None:
                error = NotFoundError(
                    "inventory_stocktake_line",
                    line_id,
                )
                error.request_id = actor.request_id
                raise error

            if line.resolution == "ADJUSTED":
                conflict = ConflictError(
                    "inventory stocktake line was already confirmed",
                    code="STOCKTAKE_LINE_ALREADY_CONFIRMED",
                    details={
                        "conflict_object": "inventory_stocktake_line",
                        "object_id": line.id,
                        "expected_version": parsed.expected_line_version,
                        "actual_version": line.version,
                        "affected_lines": [line.id],
                        "retryable": False,
                        "suggested_action": "reload_stocktake",
                    },
                )
                conflict.request_id = actor.request_id
                raise conflict

            self._require_line_version(
                actor,
                line,
                expected_version=parsed.expected_line_version,
            )

            line.counted_quantity = parsed.counted_quantity
            line.variance_quantity = (
                parsed.counted_quantity - line.system_quantity
            )
            line.version += 1
            stocktake.version += 1
            session.flush()

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def review(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
            expected_version=expected_version,
        )
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key("review", clean_key)
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_REVIEW",
                "stocktake_id": stocktake_id,
                "expected_version": expected_version,
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=expected_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"COUNTING"},
            )

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            incomplete = [
                line.id
                for line in lines
                if line.resolution != "ADJUSTED"
                and line.counted_quantity is None
            ]
            if incomplete:
                error = BusinessValidationError(
                    "all unresolved stocktake lines must be counted before review",
                    code="STOCKTAKE_COUNT_INCOMPLETE",
                    details={
                        "stocktake_id": stocktake.id,
                        "affected_lines": incomplete,
                    },
                )
                error.request_id = actor.request_id
                raise error

            stocktake.status = "REVIEWING"
            stocktake.version += 1
            session.flush()

            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def rebase_lines(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        command: dict[str, Any],
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
        )
        payload = self._rebase_command(
            command,
            actor,
        )
        if any(
            item["action"] == "BASELINE_ACCEPT"
            for item in payload["lines"]
        ):
            self._require_admin(actor)

        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key(
            "rebase-lines",
            clean_key,
        )
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_REBASE_LINES",
                "stocktake_id": stocktake_id,
                "command": payload,
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=payload["expected_version"],
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"CONFLICTED"},
            )

            requested = {
                item["line_id"]: item["action"]
                for item in payload["lines"]
            }
            locked_lines: list[InventoryStocktakeLine] = []
            for line_id in sorted(requested):
                line = self.stocktake_repository.lock_line(
                    session,
                    actor.tenant_id,
                    stocktake.id,
                    line_id,
                )
                if line is None:
                    error = NotFoundError(
                        "inventory_stocktake_line",
                        line_id,
                    )
                    error.request_id = actor.request_id
                    raise error

                if line.resolution == "ADJUSTED":
                    conflict = ConflictError(
                        "inventory stocktake line was already confirmed",
                        code="STOCKTAKE_LINE_ALREADY_CONFIRMED",
                        details={
                            "conflict_object": "inventory_stocktake_line",
                            "object_id": line.id,
                            "actual_version": line.version,
                            "affected_lines": [line.id],
                            "retryable": False,
                            "suggested_action": "reload_stocktake",
                        },
                    )
                    conflict.request_id = actor.request_id
                    raise conflict

                if line.resolution != "CONFLICTED":
                    conflict = ConflictError(
                        "inventory stocktake line is not conflicted",
                        code="INVENTORY_OPERATION_STATE_CONFLICT",
                        details={
                            "conflict_object": "inventory_stocktake_line",
                            "object_id": line.id,
                            "resolution": line.resolution,
                            "affected_lines": [line.id],
                            "retryable": False,
                        },
                    )
                    conflict.request_id = actor.request_id
                    raise conflict

                locked_lines.append(line)

            balance_ids = sorted(
                {
                    line.balance_id
                    for line in locked_lines
                }
            )
            balances = self.ledger_repository.lock_balances(
                session,
                actor.tenant_id,
                balance_ids,
            )
            balances_by_id = {
                balance.id: balance
                for balance in balances
            }
            for balance in balances:
                session.refresh(balance)

            for line in locked_lines:
                action = requested[line.id]
                balance = balances_by_id[line.balance_id]
                line.system_quantity = balance.on_hand_quantity
                line.snapshot_balance_version = balance.version
                line.conflict_details_json = None

                if action == "RECOUNT":
                    line.counted_quantity = None
                    line.variance_quantity = None
                    line.resolution = "RECOUNT_REQUIRED"
                else:
                    if line.counted_quantity is None:
                        line.variance_quantity = None
                    else:
                        line.variance_quantity = (
                            line.counted_quantity
                            - balance.on_hand_quantity
                        )
                    line.resolution = "BASELINE_ACCEPTED"

                line.version += 1

            stocktake.status = "COUNTING"
            stocktake.version += 1
            session.flush()

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def cancel(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_contributor(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
            expected_version=expected_version,
        )
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key("cancel", clean_key)
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_CANCEL",
                "stocktake_id": stocktake_id,
                "expected_version": expected_version,
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=expected_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed=_CANCELLABLE_STATUSES,
            )

            stocktake.status = "CANCELLED"
            stocktake.cancelled_at = utc_now()
            stocktake.version += 1
            session.flush()

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def preview_confirm(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        command: dict[str, Any],
        idempotency_key: str,
    ) -> InventoryOperationPreviewRead:
        self._require_admin(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
        )
        expected_version = self._preview_expected_version(
            command,
            actor,
        )
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        request_hash = snapshot_service.canonical_hash(
            {
                "operation_type": "STOCKTAKE_CONFIRM",
                "stocktake_id": stocktake_id,
                "expected_version": expected_version,
            }
        )

        existing = self.transaction_repository.get_idempotent(
            session,
            actor.tenant_id,
            "STOCKTAKE_CONFIRM",
            clean_key,
        )
        if existing is not None:
            return self._replay_confirm_preview(
                actor,
                existing,
                request_hash=request_hash,
            )

        with session.begin_nested():
            existing = self.transaction_repository.get_idempotent(
                session,
                actor.tenant_id,
                "STOCKTAKE_CONFIRM",
                clean_key,
            )
            if existing is not None:
                return self._replay_confirm_preview(
                    actor,
                    existing,
                    request_hash=request_hash,
                )

            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=expected_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"REVIEWING"},
            )
            lines = self.stocktake_repository.list_unresolved_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )

            existing = self.transaction_repository.get_idempotent(
                session,
                actor.tenant_id,
                "STOCKTAKE_CONFIRM",
                clean_key,
            )
            if existing is not None:
                return self._replay_confirm_preview(
                    actor,
                    existing,
                    request_hash=request_hash,
                )

            preview_command = {
                "operation_type": "STOCKTAKE_CONFIRM",
                "stocktake_id": stocktake.id,
                "expected_version": expected_version,
                "lines": [
                    {
                        "stocktake_line_id": line.id,
                        "balance_id": line.balance_id,
                        "snapshot_balance_version": (
                            line.snapshot_balance_version
                        ),
                        "system_quantity": format(
                            line.system_quantity,
                            ".4f",
                        ),
                        "counted_quantity": (
                            format(line.counted_quantity, ".4f")
                            if line.counted_quantity is not None
                            else None
                        ),
                        "variance_quantity": (
                            format(line.variance_quantity, ".4f")
                            if line.variance_quantity is not None
                            else None
                        ),
                        "resolution": line.resolution,
                    }
                    for line in lines
                ],
            }
            confirmation_token = secrets.token_urlsafe(32)
            confirmation_token_hash = hashlib.sha256(
                confirmation_token.encode("utf-8")
            ).hexdigest()
            confirmation_expires_at = (
                utc_now() + self.confirm_preview_ttl
            )

            transaction = self.transaction_repository.create_transaction(
                session,
                actor=actor,
                operation_type="STOCKTAKE_CONFIRM",
                idempotency_key=clean_key,
                request_hash=request_hash,
                reason="stocktake confirmation preview",
                status="PREVIEWED",
                reference_type="inventory_stocktake",
                reference_id=str(stocktake.id),
            )
            transaction.confirmation_token_hash = (
                confirmation_token_hash
            )
            transaction.confirmation_expires_at = (
                confirmation_expires_at
            )

            stored_preview = InventoryOperationPreviewRead(
                transaction_id=transaction.id,
                operation_type="STOCKTAKE_CONFIRM",
                transaction_version=transaction.version,
                confirmation_token=None,
                confirmation_expires_at=confirmation_expires_at,
            )
            snapshot = stored_preview.model_dump(mode="json")
            snapshot["_extensions"] = {
                "preview_command": deepcopy(preview_command),
            }
            transaction.response_snapshot_json = snapshot
            session.flush()

            return stored_preview.model_copy(
                update={"confirmation_token": confirmation_token}
            )

    def execute_confirm(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
        *,
        command: dict[str, Any],
        idempotency_key: str,
    ) -> InventoryStocktakeRead:
        self._require_admin(actor)
        self._require_positive_ids(
            actor,
            stocktake_id=stocktake_id,
        )
        payload = self._execute_confirm_command(
            command,
            actor,
        )
        clean_key = self._normalize_idempotency_key(
            idempotency_key,
            actor,
        )
        receipt_key = self._receipt_key(
            "execute-confirm",
            clean_key,
        )
        source_hash = snapshot_service.canonical_hash(
            {
                "operation": "STOCKTAKE_EXECUTE_CONFIRM",
                "stocktake_id": stocktake_id,
                "command": payload,
            }
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                source_hash=source_hash,
            )
            if replay is not None:
                return replay

            receipt = self.receipt_repository.create_pending(
                session,
                actor,
                idempotency_key=receipt_key,
                source_hash=source_hash,
            )
            transaction = (
                self.transaction_repository.lock_transaction(
                    session,
                    actor.tenant_id,
                    payload["transaction_id"],
                )
            )
            if transaction is None:
                error = NotFoundError(
                    "inventory_transaction",
                    payload["transaction_id"],
                )
                error.request_id = actor.request_id
                raise error

            self._require_confirm_transaction(
                actor,
                transaction,
                stocktake_id=stocktake_id,
                expected_version=payload[
                    "expected_transaction_version"
                ],
            )
            self._require_confirmation_token(
                actor,
                transaction,
                payload["confirmation_token"],
            )
            self._require_confirmation_not_expired(
                actor,
                transaction,
            )

            preview_command = self._confirm_preview_command(
                actor,
                transaction,
            )
            preview_stocktake_id = preview_command.get(
                "stocktake_id"
            )
            if preview_stocktake_id != stocktake_id:
                conflict = ConflictError(
                    "inventory operation state conflict",
                    code="INVENTORY_OPERATION_STATE_CONFLICT",
                    details={
                        "conflict_object": "inventory_transaction",
                        "object_id": transaction.id,
                        "stocktake_id": stocktake_id,
                        "preview_stocktake_id": preview_stocktake_id,
                        "retryable": False,
                    },
                )
                conflict.request_id = actor.request_id
                raise conflict

            expected_stocktake_version = (
                self._positive_int_value(
                    preview_command.get(
                        "expected_version"
                    ),
                    "expected_version",
                    actor,
                )
            )
            stocktake = self._lock_stocktake(
                session,
                actor,
                stocktake_id,
            )
            self._require_stocktake_version(
                actor,
                stocktake,
                expected_version=expected_stocktake_version,
            )
            self._require_stocktake_status(
                actor,
                stocktake,
                allowed={"REVIEWING"},
            )

            unresolved = (
                self.stocktake_repository.list_unresolved_lines(
                    session,
                    actor.tenant_id,
                    stocktake.id,
                )
            )
            locked_lines: list[InventoryStocktakeLine] = []
            for line in sorted(
                unresolved,
                key=lambda item: item.id,
            ):
                locked_line = self.stocktake_repository.lock_line(
                    session,
                    actor.tenant_id,
                    stocktake.id,
                    line.id,
                )
                if locked_line is None:
                    error = NotFoundError(
                        "inventory_stocktake_line",
                        line.id,
                    )
                    error.request_id = actor.request_id
                    raise error
                locked_lines.append(locked_line)

            balance_ids = sorted(
                {
                    line.balance_id
                    for line in locked_lines
                }
            )
            locked_balances = self.ledger_repository.lock_balances(
                session,
                actor.tenant_id,
                balance_ids,
            )
            balances_by_id = {
                balance.id: balance
                for balance in locked_balances
            }
            for balance in locked_balances:
                session.refresh(balance)

            conflicts: list[InventoryStocktakeLine] = []
            successful: list[InventoryStocktakeLine] = []
            mutations: list[InventoryBalanceMutation] = []

            for line in locked_lines:
                balance = balances_by_id[line.balance_id]
                if (
                    balance.version
                    != line.snapshot_balance_version
                ):
                    line.resolution = "CONFLICTED"
                    line.confirmed_transaction_id = None
                    line.conflict_details_json = {
                        "code": "STOCKTAKE_VERSION_CONFLICT",
                        "balance_id": balance.id,
                        "expected_version": (
                            line.snapshot_balance_version
                        ),
                        "actual_version": balance.version,
                    }
                    line.version += 1
                    conflicts.append(line)
                    continue

                successful.append(line)
                if (
                    line.variance_quantity is not None
                    and line.variance_quantity != 0
                ):
                    mutations.append(
                        InventoryBalanceMutation(
                            balance_id=balance.id,
                            expected_version=balance.version,
                            deltas=InventoryQuantityDelta(
                                on_hand=line.variance_quantity,
                            ),
                        )
                    )

            terminal_status = (
                "PARTIALLY_COMPLETED"
                if conflicts
                else "COMPLETED"
            )
            if mutations:
                plan = InventoryMutationPlan(
                    operation_type="STOCKTAKE_CONFIRM",
                    reference_type="inventory_stocktake",
                    reference_id=str(stocktake.id),
                    reason="stocktake confirmation",
                    mutations=tuple(mutations),
                    audit_context={
                        "stocktake_id": stocktake.id,
                        "conflicted_line_ids": [
                            line.id
                            for line in conflicts
                        ],
                    },
                )
                self.transaction_service.apply_plan_to_transaction(
                    session,
                    actor,
                    transaction=transaction,
                    plan=plan,
                    required_role=MaintenanceRole.ADMIN,
                    terminal_status=terminal_status,
                )
            else:
                self.transaction_service.complete_preview_without_mutations(
                    session,
                    actor,
                    transaction=transaction,
                    operation_type="STOCKTAKE_CONFIRM",
                    required_role=MaintenanceRole.ADMIN,
                    terminal_status=terminal_status,
                    reason="stocktake confirmation",
                    reference_type="inventory_stocktake",
                    reference_id=str(stocktake.id),
                )

            for line in successful:
                line.resolution = "ADJUSTED"
                line.confirmed_transaction_id = transaction.id
                line.conflict_details_json = None
                line.version += 1

            if conflicts:
                stocktake.status = "CONFLICTED"
            else:
                stocktake.status = "CONFIRMED"
                stocktake.confirmed_at = utc_now()
            stocktake.version += 1
            session.flush()

            lines = self.stocktake_repository.list_lines(
                session,
                actor.tenant_id,
                stocktake.id,
            )
            result = self._read(stocktake, lines)
            self._complete_receipt(
                session,
                receipt,
                result=result,
            )
            return result

    def _replay_confirm_preview(
        self,
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        request_hash: str,
    ) -> InventoryOperationPreviewRead:
        if transaction.request_hash != request_hash:
            conflict = ConflictError(
                "idempotency key was reused with a different stocktake preview command",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        if (
            transaction.status != "PREVIEWED"
            or transaction.operation_type != "STOCKTAKE_CONFIRM"
        ):
            conflict = ConflictError(
                "inventory operation state conflict",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "status": transaction.status,
                    "operation_type": transaction.operation_type,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            conflict = ConflictError(
                "stocktake confirmation preview snapshot is unavailable",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        public_snapshot = {
            key: deepcopy(value)
            for key, value in snapshot.items()
            if key != "_extensions"
        }
        public_snapshot["confirmation_token"] = None
        return InventoryOperationPreviewRead.model_validate(
            public_snapshot
        ).model_copy(deep=True)

    @staticmethod
    def _preview_expected_version(
        command: dict[str, Any],
        actor: ActorContext,
    ) -> int:
        raw_value = command.get("expected_version")
        if (
            isinstance(raw_value, bool)
            or not isinstance(raw_value, int)
            or raw_value <= 0
        ):
            error = BusinessValidationError(
                "stocktake preview expected_version must be a positive integer",
            )
            error.request_id = actor.request_id
            raise error
        return raw_value

    @staticmethod
    def _rebase_command(
        command: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        if not isinstance(command, dict):
            error = BusinessValidationError(
                "stocktake rebase command must be an object",
            )
            error.request_id = actor.request_id
            raise error

        expected_version = (
            InventoryStocktakeService._positive_int_value(
                command.get("expected_version"),
                "expected_version",
                actor,
            )
        )
        raw_lines = command.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            error = BusinessValidationError(
                "stocktake rebase lines are required",
            )
            error.request_id = actor.request_id
            raise error

        normalized_lines: list[dict[str, Any]] = []
        seen_line_ids: set[int] = set()
        for raw_line in raw_lines:
            if not isinstance(raw_line, dict):
                error = BusinessValidationError(
                    "stocktake rebase line must be an object",
                )
                error.request_id = actor.request_id
                raise error

            line_id = (
                InventoryStocktakeService._positive_int_value(
                    raw_line.get("line_id"),
                    "line_id",
                    actor,
                )
            )
            if line_id in seen_line_ids:
                error = BusinessValidationError(
                    "stocktake rebase line ids must be unique",
                )
                error.request_id = actor.request_id
                raise error
            seen_line_ids.add(line_id)

            action = raw_line.get("action")
            if action not in {"RECOUNT", "BASELINE_ACCEPT"}:
                error = BusinessValidationError(
                    "stocktake rebase action is invalid",
                )
                error.request_id = actor.request_id
                raise error

            normalized_lines.append(
                {
                    "line_id": line_id,
                    "action": action,
                }
            )

        return {
            "expected_version": expected_version,
            "lines": sorted(
                normalized_lines,
                key=lambda item: item["line_id"],
            ),
        }

    @staticmethod
    def _execute_confirm_command(
        command: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        if not isinstance(command, dict):
            error = BusinessValidationError(
                "stocktake execute-confirm command must be an object",
            )
            error.request_id = actor.request_id
            raise error

        transaction_id = (
            InventoryStocktakeService._positive_int_value(
                command.get("transaction_id"),
                "transaction_id",
                actor,
            )
        )
        expected_transaction_version = (
            InventoryStocktakeService._positive_int_value(
                command.get(
                    "expected_transaction_version"
                ),
                "expected_transaction_version",
                actor,
            )
        )
        token = command.get("confirmation_token")
        if not isinstance(token, str) or not token:
            error = BusinessValidationError(
                "confirmation token is required",
            )
            error.request_id = actor.request_id
            raise error

        return {
            "transaction_id": transaction_id,
            "expected_transaction_version": (
                expected_transaction_version
            ),
            "confirmation_token": token,
        }

    @staticmethod
    def _positive_int_value(
        value: Any,
        field_name: str,
        actor: ActorContext,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            error = BusinessValidationError(
                f"{field_name} must be a positive integer",
            )
            error.request_id = actor.request_id
            raise error
        return value

    @staticmethod
    def _require_confirm_transaction(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        stocktake_id: int,
        expected_version: int,
    ) -> None:
        if (
            transaction.operation_type
            != "STOCKTAKE_CONFIRM"
            or transaction.status != "PREVIEWED"
            or transaction.reference_type
            != "inventory_stocktake"
            or transaction.reference_id
            != str(stocktake_id)
        ):
            conflict = ConflictError(
                "inventory operation state conflict",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "status": transaction.status,
                    "operation_type": transaction.operation_type,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        if transaction.version != expected_version:
            conflict = ConflictError(
                "inventory transaction version conflict",
                code="INVENTORY_TRANSACTION_VERSION_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "expected_version": expected_version,
                    "actual_version": transaction.version,
                    "retryable": True,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

    @staticmethod
    def _require_confirmation_token(
        actor: ActorContext,
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
            error = BusinessValidationError(
                "confirmation token is invalid",
                code="INVENTORY_CONFIRMATION_TOKEN_INVALID",
            )
            error.request_id = actor.request_id
            raise error

    @classmethod
    def _require_confirmation_not_expired(
        cls,
        actor: ActorContext,
        transaction: InventoryTransaction,
    ) -> None:
        expires_at = transaction.confirmation_expires_at
        if expires_at is None:
            error = BusinessValidationError(
                "confirmation expiry is unavailable",
                code="INVENTORY_CONFIRMATION_EXPIRED",
            )
            error.request_id = actor.request_id
            raise error

        if cls._as_utc(expires_at) <= utc_now():
            error = BusinessValidationError(
                "confirmation token has expired",
                code="INVENTORY_CONFIRMATION_EXPIRED",
            )
            error.request_id = actor.request_id
            raise error

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _confirm_preview_command(
        actor: ActorContext,
        transaction: InventoryTransaction,
    ) -> dict[str, Any]:
        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            conflict = ConflictError(
                "stocktake confirmation preview is unavailable",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
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
                "stocktake confirmation preview is unavailable",
                code="INVENTORY_OPERATION_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transaction",
                    "object_id": transaction.id,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict
        return deepcopy(preview_command)

    def _replay_receipt(
        self,
        session: Session,
        actor: ActorContext,
        *,
        receipt_key: str,
        source_hash: str,
    ) -> InventoryStocktakeRead | None:
        receipt = self.receipt_repository.get(
            session,
            actor.tenant_id,
            receipt_key,
        )
        if receipt is None:
            return None

        if receipt.source_hash != source_hash:
            conflict = ConflictError(
                "idempotency key was reused with a different stocktake command",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "inventory_target_receipt",
                    "object_id": receipt.id,
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        if receipt.result_json is None:
            conflict = ConflictError(
                "stocktake command is already in progress",
                details={
                    "conflict_object": "inventory_target_receipt",
                    "object_id": receipt.id,
                    "retryable": True,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        return InventoryStocktakeRead.model_validate(
            deepcopy(receipt.result_json)
        ).model_copy(deep=True)

    def _complete_receipt(
        self,
        session: Session,
        receipt: InventoryTargetReceipt,
        *,
        result: InventoryStocktakeRead,
    ) -> None:
        self.receipt_repository.complete(
            session,
            receipt,
            result=result.model_dump(mode="json"),
            completed_at=utc_now(),
        )

    def _lock_stocktake(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
    ) -> InventoryStocktake:
        stocktake = self.stocktake_repository.lock(
            session,
            actor.tenant_id,
            stocktake_id,
        )
        if stocktake is None:
            error = NotFoundError(
                "inventory_stocktake",
                stocktake_id,
            )
            error.request_id = actor.request_id
            raise error
        return stocktake

    @staticmethod
    def _require_stocktake_version(
        actor: ActorContext,
        stocktake: InventoryStocktake,
        *,
        expected_version: int,
    ) -> None:
        if stocktake.version == expected_version:
            return

        conflict = ConflictError(
            "inventory stocktake version conflict",
            code="STOCKTAKE_VERSION_CONFLICT",
            details={
                "conflict_object": "inventory_stocktake",
                "object_id": stocktake.id,
                "expected_version": expected_version,
                "actual_version": stocktake.version,
                "affected_lines": [],
                "retryable": False,
                "suggested_action": "reload_stocktake",
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _require_line_version(
        actor: ActorContext,
        line: InventoryStocktakeLine,
        *,
        expected_version: int,
    ) -> None:
        if line.version == expected_version:
            return

        conflict = ConflictError(
            "inventory stocktake line version conflict",
            code="STOCKTAKE_VERSION_CONFLICT",
            details={
                "conflict_object": "inventory_stocktake_line",
                "object_id": line.id,
                "expected_version": expected_version,
                "actual_version": line.version,
                "affected_lines": [line.id],
                "retryable": False,
                "suggested_action": "reload_stocktake",
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _require_stocktake_status(
        actor: ActorContext,
        stocktake: InventoryStocktake,
        *,
        allowed: set[str] | frozenset[str],
    ) -> None:
        if stocktake.status in allowed:
            return

        conflict = ConflictError(
            "inventory stocktake state conflict",
            code="INVENTORY_OPERATION_STATE_CONFLICT",
            details={
                "conflict_object": "inventory_stocktake",
                "object_id": stocktake.id,
                "status": stocktake.status,
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _read(
        stocktake: InventoryStocktake,
        lines: list[InventoryStocktakeLine],
    ) -> InventoryStocktakeRead:
        return InventoryStocktakeRead(
            id=stocktake.id,
            tenant_id=stocktake.tenant_id,
            warehouse_id=stocktake.warehouse_id,
            location_id=stocktake.location_id,
            status=stocktake.status,
            snapshot_at=stocktake.snapshot_at,
            actor_user_id=stocktake.actor_user_id,
            actor_roles=list(stocktake.actor_roles_json),
            request_id=stocktake.request_id,
            version=stocktake.version,
            confirmed_at=stocktake.confirmed_at,
            cancelled_at=stocktake.cancelled_at,
            lines=tuple(
                InventoryStocktakeLineRead(
                    id=line.id,
                    stocktake_id=line.stocktake_id,
                    balance_id=line.balance_id,
                    spare_part_id=line.spare_part_id,
                    lot_id=line.lot_id,
                    serial_item_id=line.serial_item_id,
                    system_quantity=line.system_quantity,
                    counted_quantity=line.counted_quantity,
                    variance_quantity=line.variance_quantity,
                    snapshot_balance_version=line.snapshot_balance_version,
                    confirmed_transaction_id=line.confirmed_transaction_id,
                    resolution=line.resolution,
                    conflict_details=deepcopy(line.conflict_details_json),
                    version=line.version,
                )
                for line in sorted(lines, key=lambda item: item.id)
            ),
        )

    @staticmethod
    def _receipt_key(operation: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()
        return f"stocktake-{operation}:{digest}"

    @staticmethod
    def _normalize_idempotency_key(
        value: str,
        actor: ActorContext,
    ) -> str:
        clean = str(value or "").strip()
        if not clean:
            error = BusinessValidationError(
                "idempotency key is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
            error.request_id = actor.request_id
            raise error
        return clean

    @staticmethod
    def _create_command(
        command: StocktakeCreateCommand | dict[str, Any],
        actor: ActorContext,
    ) -> StocktakeCreateCommand:
        if isinstance(command, StocktakeCreateCommand):
            return command
        try:
            return StocktakeCreateCommand.model_validate(command)
        except ValidationError as exc:
            error = BusinessValidationError(
                "invalid stocktake create command",
                details=exc.errors(),
            )
            error.request_id = actor.request_id
            raise error from exc

    @staticmethod
    def _count_command(
        command: StocktakeCountCommand | dict[str, Any],
        actor: ActorContext,
    ) -> StocktakeCountCommand:
        if isinstance(command, StocktakeCountCommand):
            return command
        try:
            return StocktakeCountCommand.model_validate(command)
        except ValidationError as exc:
            error = BusinessValidationError(
                "invalid stocktake count command",
                details=exc.errors(),
            )
            error.request_id = actor.request_id
            raise error from exc

    @staticmethod
    def _require_contributor(actor: ActorContext) -> None:
        if _ROLE_RANK[actor.role] >= _ROLE_RANK[MaintenanceRole.CONTRIBUTOR]:
            return
        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.CONTRIBUTOR.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )

    @staticmethod
    def _require_admin(actor: ActorContext) -> None:
        if actor.role is MaintenanceRole.ADMIN:
            return
        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.ADMIN.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )

    @staticmethod
    def _require_positive_ids(
        actor: ActorContext,
        **values: int,
    ) -> None:
        if all(value > 0 for value in values.values()):
            return
        error = BusinessValidationError(
            "stocktake ids and expected versions must be positive",
        )
        error.request_id = actor.request_id
        raise error
