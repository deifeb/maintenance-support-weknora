from __future__ import annotations

import hashlib
import hmac
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
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
    InventoryTargetReceiptStatus,
    InventoryTransaction,
    SerializedItem,
    WarehouseLocation,
)
from app.models.mixins import utc_now
from app.repositories.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from app.repositories.inventory_target_receipt_repository import (
    InventoryTargetReceiptRepository,
)
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
)
from app.repositories.inventory_transfer_repository import (
    InventoryTransferRepository,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
    InventoryOperationPreviewRead,
)
from app.schemas.inventory_transfer import (
    TransferCreateCommand,
    TransferLineRead,
    TransferRead,
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

_DEFAULT_PREVIEW_TTL = timedelta(minutes=15)


class InventoryTransferService:
    def __init__(
        self,
        *,
        transfer_repository: (
            InventoryTransferRepository | None
        ) = None,
        receipt_repository: (
            InventoryTargetReceiptRepository | None
        ) = None,
        transaction_repository: (
            InventoryTransactionRepository | None
        ) = None,
        ledger_repository: (
            InventoryLedgerRepository | None
        ) = None,
        transaction_service: (
            InventoryTransactionService | None
        ) = None,
        preview_ttl: timedelta = _DEFAULT_PREVIEW_TTL,
    ) -> None:
        self.transfer_repository = (
            transfer_repository
            or InventoryTransferRepository()
        )
        self.receipt_repository = (
            receipt_repository
            or InventoryTargetReceiptRepository()
        )
        self.transaction_repository = (
            transaction_repository
            or InventoryTransactionRepository()
        )
        self.ledger_repository = (
            ledger_repository
            or InventoryLedgerRepository()
        )
        self.transaction_service = (
            transaction_service
            or InventoryTransactionService(
                transaction_repository=(
                    self.transaction_repository
                ),
                ledger_repository=(
                    self.ledger_repository
                ),
            )
        )
        self.preview_ttl = preview_ttl

    # ========================================================
    # CREATE
    # ========================================================

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command: Any,
        idempotency_key: str,
    ) -> TransferRead:
        self._require_contributor(actor)

        clean_key = self._normalize_idempotency_key(
            idempotency_key
        )

        try:
            create_command = (
                command
                if isinstance(
                    command,
                    TransferCreateCommand,
                )
                else TransferCreateCommand.model_validate(
                    self._command_payload(command)
                )
            )
        except ValidationError as exc:
            message = str(exc)

            if (
                "source and target locations must differ"
                in message
            ):
                self._raise_validation(
                    actor,
                    "source and target locations must differ",
                    code="TRANSFER_STATE_CONFLICT",
                    details={
                        "conflict_object": (
                            "inventory_transfer"
                        ),
                        "retryable": False,
                    },
                )

            self._raise_validation(
                actor,
                "inventory transfer command is invalid",
                code="TRANSFER_STATE_CONFLICT",
                details={
                    "conflict_object": (
                        "inventory_transfer"
                    ),
                    "retryable": False,
                    "validation_errors": exc.errors(
                        include_url=False
                    ),
                },
            )

        payload = create_command.model_dump(
            mode="json"
        )
        request_hash = (
            snapshot_service.canonical_hash(
                payload
            )
        )
        receipt_key = self._receipt_key(
            clean_key
        )

        replay = self._replay_receipt(
            session,
            actor,
            receipt_key=receipt_key,
            request_hash=request_hash,
        )

        if replay is not None:
            return replay

        with session.begin_nested():
            replay = self._replay_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                request_hash=request_hash,
            )

            if replay is not None:
                return replay

            receipt = self._claim_receipt(
                session,
                actor,
                receipt_key=receipt_key,
                request_hash=request_hash,
            )

            if receipt.result_json is not None:
                return self._receipt_result(
                    actor,
                    receipt,
                    request_hash=request_hash,
                )

            self._require_target_location(
                session,
                actor,
                warehouse_id=(
                    create_command
                    .target_warehouse_id
                ),
                location_id=(
                    create_command
                    .target_location_id
                ),
            )

            line_values: list[
                dict[str, Any]
            ] = []

            for command_line in (
                create_command.lines
            ):
                source = (
                    self._require_source_balance(
                        session,
                        actor,
                        command_line
                        .source_balance_id,
                    )
                )

                self._require_source_identity(
                    actor,
                    source,
                    command=create_command,
                    line=command_line,
                )

                if (
                    source.version
                    != command_line
                    .expected_source_version
                ):
                    self._raise_conflict(
                        actor,
                        "inventory balance version conflict",
                        code=(
                            "INVENTORY_VERSION_CONFLICT"
                        ),
                        details={
                            "balance_id": source.id,
                            "expected_version": (
                                command_line
                                .expected_source_version
                            ),
                            "actual_version": (
                                source.version
                            ),
                            "conflict_object": (
                                "inventory_balance"
                            ),
                            "retryable": True,
                        },
                    )

                self._require_serial_contract(
                    session,
                    actor,
                    source,
                    serial_item_id=(
                        command_line
                        .serial_item_id
                    ),
                    quantity=(
                        command_line.quantity
                    ),
                )

                target = (
                    self.transfer_repository
                    .resolve_target_balance(
                        session,
                        actor.tenant_id,
                        warehouse_id=(
                            create_command
                            .target_warehouse_id
                        ),
                        location_id=(
                            create_command
                            .target_location_id
                        ),
                        spare_part_id=(
                            command_line
                            .spare_part_id
                        ),
                        lot_id=(
                            command_line.lot_id
                        ),
                    )
                )

                line_values.append(
                    {
                        "spare_part_id": (
                            command_line
                            .spare_part_id
                        ),
                        "source_balance_id": (
                            source.id
                        ),
                        "target_balance_id": (
                            target.id
                        ),
                        "lot_id": (
                            command_line.lot_id
                        ),
                        "serial_item_id": (
                            command_line
                            .serial_item_id
                        ),
                        "requested_quantity": (
                            command_line.quantity
                        ),
                        "expected_source_version": (
                            source.version
                        ),
                        "expected_target_version": (
                            target.version
                        ),
                    }
                )

            transfer = (
                self.transfer_repository
                .create_transfer(
                    session,
                    actor=actor,
                    source_warehouse_id=(
                        create_command
                        .source_warehouse_id
                    ),
                    source_location_id=(
                        create_command
                        .source_location_id
                    ),
                    target_warehouse_id=(
                        create_command
                        .target_warehouse_id
                    ),
                    target_location_id=(
                        create_command
                        .target_location_id
                    ),
                    reference_type=(
                        create_command
                        .reference_type
                    ),
                    reference_id=(
                        create_command
                        .reference_id
                    ),
                    reason=create_command.reason,
                )
            )

            lines = (
                self.transfer_repository
                .create_lines(
                    session,
                    transfer=transfer,
                    lines=line_values,
                )
            )

            result = self._read_transfer(
                transfer,
                lines,
            )

            self.receipt_repository.complete(
                session,
                receipt,
                result=result.model_dump(
                    mode="json"
                ),
                completed_at=utc_now(),
            )

            return result

    # ========================================================
    # DISPATCH PREVIEW
    # ========================================================

    def preview_dispatch(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> InventoryOperationPreviewRead:
        self._require_admin(actor)

        clean_key = (
            self._normalize_idempotency_key(
                idempotency_key
            )
        )

        payload = self._command_payload(
            command
        )

        expected_transfer_version = (
            self._required_positive_int(
                payload,
                "expected_version",
            )
        )

        request_payload = {
            "transfer_id": transfer_id,
            "expected_version": (
                expected_transfer_version
            ),
        }

        request_hash = (
            snapshot_service.canonical_hash(
                request_payload
            )
        )

        existing = (
            self.transaction_repository
            .get_idempotent(
                session,
                actor.tenant_id,
                "TRANSFER_DISPATCH",
                clean_key,
            )
        )

        if existing is not None:
            return (
                self._replay_dispatch_preview(
                    actor,
                    existing,
                    transfer_id=transfer_id,
                    request_hash=request_hash,
                )
            )

        transfer = (
            self.transfer_repository
            .get_transfer(
                session,
                actor.tenant_id,
                transfer_id,
            )
        )

        if transfer is None:
            self._raise_not_found(
                actor,
                "inventory_transfer",
                transfer_id,
            )

        assert transfer is not None

        self._require_dispatch_draft(
            actor,
            transfer,
        )

        self._require_transfer_version(
            actor,
            transfer,
            expected_version=(
                expected_transfer_version
            ),
        )

        lines = (
            self.transfer_repository
            .list_lines(
                session,
                actor.tenant_id,
                transfer.id,
            )
        )

        if not lines:
            self._raise_conflict(
                actor,
                "inventory transfer has no lines",
                code="TRANSFER_STATE_CONFLICT",
                details={
                    "transfer_id": transfer.id,
                    "conflict_object": (
                        "inventory_transfer"
                    ),
                    "retryable": False,
                },
            )

        preview_lines: list[
            dict[str, Any]
        ] = []

        for line in lines:
            source = (
                self._require_dispatch_balance(
                    session,
                    actor,
                    line.source_balance_id,
                )
            )
            target = (
                self._require_dispatch_balance(
                    session,
                    actor,
                    line.target_balance_id,
                )
            )

            self._require_balance_version(
                actor,
                source,
                expected_version=(
                    line.expected_source_version
                ),
            )
            self._require_balance_version(
                actor,
                target,
                expected_version=(
                    line.expected_target_version
                ),
            )

            preview_lines.append(
                {
                    "transfer_line_id": (
                        line.id
                    ),
                    "quantity": format(
                        line.requested_quantity,
                        ".4f",
                    ),
                    "source_balance_id": (
                        line.source_balance_id
                    ),
                    "target_balance_id": (
                        line.target_balance_id
                    ),
                    "expected_source_version": (
                        source.version
                    ),
                    "expected_target_version": (
                        target.version
                    ),
                    "serial_item_id": (
                        line.serial_item_id
                    ),
                }
            )

        private_command = {
            "operation_type": (
                "TRANSFER_DISPATCH"
            ),
            "transfer_id": transfer.id,
            "expected_transfer_version": (
                transfer.version
            ),
            "reason": transfer.reason,
            "lines": preview_lines,
        }

        confirmation_token = (
            secrets.token_urlsafe(32)
        )
        confirmation_token_hash = (
            hashlib.sha256(
                confirmation_token.encode(
                    "utf-8"
                )
            ).hexdigest()
        )
        confirmation_expires_at = (
            utc_now() + self.preview_ttl
        )

        transaction = (
            self.transaction_repository
            .create_transaction(
                session,
                actor=actor,
                operation_type=(
                    "TRANSFER_DISPATCH"
                ),
                idempotency_key=clean_key,
                request_hash=request_hash,
                reason=transfer.reason,
                status="PREVIEWED",
                reference_type=(
                    "INVENTORY_TRANSFER"
                ),
                reference_id=str(
                    transfer.id
                ),
            )
        )

        transaction.confirmation_token_hash = (
            confirmation_token_hash
        )
        transaction.confirmation_expires_at = (
            confirmation_expires_at
        )

        stored_preview = (
            InventoryOperationPreviewRead(
                transaction_id=(
                    transaction.id
                ),
                operation_type=(
                    "TRANSFER_DISPATCH"
                ),
                transaction_version=(
                    transaction.version
                ),
                confirmation_token=None,
                confirmation_expires_at=(
                    confirmation_expires_at
                ),
            )
        )

        snapshot = stored_preview.model_dump(
            mode="json"
        )
        snapshot["_extensions"] = {
            "preview_command": deepcopy(
                private_command
            )
        }

        transaction.response_snapshot_json = (
            snapshot
        )
        session.flush()

        return stored_preview.model_copy(
            update={
                "confirmation_token": (
                    confirmation_token
                )
            }
        )

    # ========================================================
    # DISPATCH EXECUTE
    # ========================================================

    def execute_dispatch(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> TransferRead:
        self._require_admin(actor)

        payload = self._command_payload(
            command
        )
        clean_key = (
            self._normalize_idempotency_key(
                idempotency_key
            )
        )

        transaction_id = (
            self._required_positive_int(
                payload,
                "transaction_id",
            )
        )
        expected_transaction_version = (
            self._required_positive_int(
                payload,
                "expected_transaction_version",
            )
        )
        confirmation_token = (
            self._required_confirmation_token(
                payload
            )
        )

        execute_request_hash = (
            snapshot_service.canonical_hash(
                payload
            )
        )

        with session.begin_nested():
            transfer = (
                self.transfer_repository
                .lock_transfer(
                    session,
                    actor.tenant_id,
                    transfer_id,
                )
            )

            if transfer is None:
                self._raise_not_found(
                    actor,
                    "inventory_transfer",
                    transfer_id,
                )

            assert transfer is not None

            transaction = (
                self.transaction_repository
                .lock_transaction(
                    session,
                    actor.tenant_id,
                    transaction_id,
                )
            )

            if transaction is None:
                self._raise_not_found(
                    actor,
                    "inventory_transaction",
                    transaction_id,
                )

            assert transaction is not None

            self._require_dispatch_transaction(
                actor,
                transaction,
                transfer_id=transfer.id,
            )

            if transaction.status != "PREVIEWED":
                return (
                    self._replay_dispatch_execute(
                        actor,
                        transaction,
                        idempotency_key=(
                            clean_key
                        ),
                        request_hash=(
                            execute_request_hash
                        ),
                    )
                )

            self._require_dispatch_draft(
                actor,
                transfer,
            )

            self._require_transaction_version(
                actor,
                transaction,
                expected_version=(
                    expected_transaction_version
                ),
            )

            self._require_confirmation_token(
                actor,
                transaction,
                confirmation_token,
            )

            self._require_confirmation_not_expired(
                actor,
                transaction,
            )

            private_command = (
                self._preview_command(
                    actor,
                    transaction,
                )
            )

            expected_transfer_version = (
                self._required_positive_int(
                    private_command,
                    "expected_transfer_version",
                )
            )

            self._require_transfer_version(
                actor,
                transfer,
                expected_version=(
                    expected_transfer_version
                ),
            )

            private_lines = (
                private_command.get("lines")
            )

            if (
                not isinstance(
                    private_lines,
                    list,
                )
                or not private_lines
            ):
                self._raise_conflict(
                    actor,
                    "dispatch preview lines are unavailable",
                    code=(
                        "INVENTORY_OPERATION_STATE_CONFLICT"
                    ),
                    details={
                        "transaction_id": (
                            transaction.id
                        ),
                        "conflict_object": (
                            "inventory_transaction"
                        ),
                        "retryable": False,
                    },
                )

            lines = (
                self.transfer_repository
                .list_lines(
                    session,
                    actor.tenant_id,
                    transfer.id,
                )
            )
            line_by_id = {
                line.id: line
                for line in lines
            }

            delta_by_balance: dict[
                int,
                InventoryQuantityDelta,
            ] = {}
            version_by_balance: dict[
                int,
                int,
            ] = {}

            dispatched_line_ids: list[
                int
            ] = []
            serial_item_ids: list[
                int
            ] = []

            for preview_line in (
                private_lines
            ):
                if not isinstance(
                    preview_line,
                    dict,
                ):
                    self._raise_dispatch_preview_invalid(
                        actor,
                        transaction.id,
                    )

                line_id = (
                    self._required_positive_int(
                        preview_line,
                        "transfer_line_id",
                    )
                )

                line = line_by_id.get(
                    line_id
                )

                if line is None:
                    self._raise_conflict(
                        actor,
                        "inventory transfer line changed after preview",
                        code="TRANSFER_STATE_CONFLICT",
                        details={
                            "transfer_id": (
                                transfer.id
                            ),
                            "transfer_line_id": (
                                line_id
                            ),
                            "conflict_object": (
                                "inventory_transfer_line"
                            ),
                            "retryable": True,
                        },
                    )

                assert line is not None

                source_balance_id = (
                    self._required_positive_int(
                        preview_line,
                        "source_balance_id",
                    )
                )
                target_balance_id = (
                    self._required_positive_int(
                        preview_line,
                        "target_balance_id",
                    )
                )
                expected_source_version = (
                    self._required_positive_int(
                        preview_line,
                        "expected_source_version",
                    )
                )
                expected_target_version = (
                    self._required_positive_int(
                        preview_line,
                        "expected_target_version",
                    )
                )

                if (
                    source_balance_id
                    != line.source_balance_id
                    or target_balance_id
                    != line.target_balance_id
                ):
                    self._raise_conflict(
                        actor,
                        "inventory transfer line balance identity changed",
                        code=(
                            "TRANSFER_STATE_CONFLICT"
                        ),
                        details={
                            "transfer_id": (
                                transfer.id
                            ),
                            "transfer_line_id": (
                                line.id
                            ),
                            "conflict_object": (
                                "inventory_transfer_line"
                            ),
                            "retryable": True,
                        },
                    )

                try:
                    quantity = Decimal(
                        str(
                            preview_line[
                                "quantity"
                            ]
                        )
                    )
                except (
                    KeyError,
                    ValueError,
                ) as exc:
                    raise BusinessValidationError(
                        "dispatch quantity is invalid",
                        code=(
                            "TRANSFER_STATE_CONFLICT"
                        ),
                    ) from exc

                if (
                    quantity
                    != line.requested_quantity
                    or line.dispatched_quantity
                    != Decimal("0.0000")
                ):
                    self._raise_conflict(
                        actor,
                        "inventory transfer line changed after preview",
                        code=(
                            "TRANSFER_STATE_CONFLICT"
                        ),
                        details={
                            "transfer_id": (
                                transfer.id
                            ),
                            "transfer_line_id": (
                                line.id
                            ),
                            "conflict_object": (
                                "inventory_transfer_line"
                            ),
                            "retryable": True,
                        },
                    )

                self._merge_dispatch_delta(
                    delta_by_balance,
                    version_by_balance,
                    balance_id=(
                        source_balance_id
                    ),
                    expected_version=(
                        expected_source_version
                    ),
                    on_hand=-quantity,
                )

                self._merge_dispatch_delta(
                    delta_by_balance,
                    version_by_balance,
                    balance_id=(
                        target_balance_id
                    ),
                    expected_version=(
                        expected_target_version
                    ),
                    in_transit=quantity,
                )

                dispatched_line_ids.append(
                    line.id
                )

                if (
                    line.serial_item_id
                    is not None
                ):
                    serial_item_ids.append(
                        line.serial_item_id
                    )

            mutations = tuple(
                InventoryBalanceMutation(
                    balance_id=balance_id,
                    expected_version=(
                        version_by_balance[
                            balance_id
                        ]
                    ),
                    deltas=(
                        delta_by_balance[
                            balance_id
                        ]
                    ),
                )
                for balance_id in sorted(
                    delta_by_balance
                )
            )

            plan = InventoryMutationPlan(
                operation_type=(
                    "TRANSFER_DISPATCH"
                ),
                reference_type=(
                    "INVENTORY_TRANSFER"
                ),
                reference_id=str(
                    transfer.id
                ),
                reason=transfer.reason,
                mutations=mutations,
                audit_context={
                    "transfer_id": (
                        transfer.id
                    ),
                    "transfer_line_ids": (
                        dispatched_line_ids
                    ),
                    "serial_item_ids": (
                        serial_item_ids
                    ),
                    "high_risk_preview": True,
                },
            )

            try:
                self.transaction_service.apply_plan_to_transaction(
                    session,
                    actor,
                    transaction=transaction,
                    plan=plan,
                    required_role=(
                        MaintenanceRole.ADMIN
                    ),
                )
            except BusinessValidationError as exc:
                if (
                    exc.code
                    != "INVENTORY_NEGATIVE_QUANTITY"
                ):
                    raise

                error = BusinessValidationError(
                    "inventory balance cannot become negative",
                    code=(
                        "INVENTORY_NEGATIVE_BALANCE"
                    ),
                    details=exc.details,
                )
                error.request_id = (
                    actor.request_id
                )
                raise error from exc

            for line in lines:
                line.dispatched_quantity = (
                    line.requested_quantity
                )
                line.version += 1

            transfer.status = "DISPATCHED"
            transfer.dispatched_at = utc_now()
            transfer.version += 1

            session.flush()

            result = self._read_transfer(
                transfer,
                lines,
            )

            self._store_dispatch_execute_snapshot(
                session,
                transaction,
                idempotency_key=clean_key,
                request_hash=(
                    execute_request_hash
                ),
                result=result,
            )

            return result

    # ========================================================
    # TASK 7 GREEN SLICE 3 RECEIVE

    def preview_receive(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> InventoryOperationPreviewRead:
        self._require_admin(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        payload = self._command_payload(command)
        expected_transfer_version = self._required_positive_int(
            payload,
            "expected_version",
        )

        raw_lines = payload.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            self._raise_validation(
                actor,
                "receive lines are required",
                code="TRANSFER_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transfer",
                    "retryable": False,
                },
            )

        request_payload = {
            "transfer_id": transfer_id,
            "expected_version": expected_transfer_version,
            "lines": deepcopy(raw_lines),
        }
        request_hash = snapshot_service.canonical_hash(request_payload)

        existing = self.transaction_repository.get_idempotent(
            session,
            actor.tenant_id,
            "TRANSFER_RECEIVE",
            clean_key,
        )
        if existing is not None:
            return self._replay_receive_preview(
                actor,
                existing,
                transfer_id=transfer_id,
                request_hash=request_hash,
            )

        transfer = self.transfer_repository.get_transfer(
            session,
            actor.tenant_id,
            transfer_id,
        )
        if transfer is None:
            self._raise_not_found(actor, "inventory_transfer", transfer_id)
        assert transfer is not None

        self._require_receivable_state(actor, transfer)
        self._require_transfer_version(
            actor,
            transfer,
            expected_version=expected_transfer_version,
        )

        lines = self.transfer_repository.list_lines(
            session,
            actor.tenant_id,
            transfer.id,
        )
        line_by_id = {line.id: line for line in lines}
        private_lines: list[dict[str, Any]] = []
        seen_line_ids: set[int] = set()

        for raw_line in raw_lines:
            if not isinstance(raw_line, dict):
                self._raise_validation(
                    actor,
                    "receive line is invalid",
                    code="TRANSFER_STATE_CONFLICT",
                    details={
                        "conflict_object": "inventory_transfer_line",
                        "retryable": False,
                    },
                )

            line_id = self._required_positive_int(raw_line, "transfer_line_id")
            if line_id in seen_line_ids:
                self._raise_conflict(
                    actor,
                    "duplicate receive line",
                    code="TRANSFER_STATE_CONFLICT",
                    details={
                        "transfer_line_id": line_id,
                        "conflict_object": "inventory_transfer_line",
                        "retryable": False,
                    },
                )
            seen_line_ids.add(line_id)

            line = line_by_id.get(line_id)
            if line is None:
                self._raise_conflict(
                    actor,
                    "inventory transfer line is unavailable",
                    code="TRANSFER_STATE_CONFLICT",
                    details={
                        "transfer_id": transfer.id,
                        "transfer_line_id": line_id,
                        "conflict_object": "inventory_transfer_line",
                        "retryable": False,
                    },
                )
            assert line is not None

            quantity = self._positive_decimal(raw_line, "quantity")
            remaining = line.dispatched_quantity - line.received_quantity
            if quantity > remaining:
                self._raise_receive_exceeds_dispatch(
                    actor,
                    transfer_id=transfer.id,
                    line_id=line.id,
                    requested=quantity,
                    remaining=remaining,
                )

            if line.serial_item_id is not None and quantity != Decimal("1.0000"):
                self._raise_validation(
                    actor,
                    "serialized receive quantity must equal one",
                    code="SERIAL_STATE_CONFLICT",
                    details={
                        "serial_item_id": line.serial_item_id,
                        "conflict_object": "serialized_item",
                        "retryable": False,
                    },
                )

            target = self._require_dispatch_balance(
                session,
                actor,
                line.target_balance_id,
            )

            private_lines.append(
                {
                    "transfer_line_id": line.id,
                    "quantity": format(quantity, ".4f"),
                    "target_balance_id": line.target_balance_id,
                    "expected_target_version": target.version,
                    "serial_item_id": line.serial_item_id,
                }
            )

        private_command = {
            "operation_type": "TRANSFER_RECEIVE",
            "transfer_id": transfer.id,
            "expected_transfer_version": transfer.version,
            "source_warehouse_id": transfer.source_warehouse_id,
            "source_location_id": transfer.source_location_id,
            "target_warehouse_id": transfer.target_warehouse_id,
            "target_location_id": transfer.target_location_id,
            "reason": transfer.reason,
            "lines": private_lines,
        }

        confirmation_token = secrets.token_urlsafe(32)
        confirmation_token_hash = hashlib.sha256(
            confirmation_token.encode("utf-8")
        ).hexdigest()
        confirmation_expires_at = utc_now() + self.preview_ttl

        transaction = self.transaction_repository.create_transaction(
            session,
            actor=actor,
            operation_type="TRANSFER_RECEIVE",
            idempotency_key=clean_key,
            request_hash=request_hash,
            reason=transfer.reason,
            status="PREVIEWED",
            reference_type="INVENTORY_TRANSFER",
            reference_id=str(transfer.id),
        )
        transaction.confirmation_token_hash = confirmation_token_hash
        transaction.confirmation_expires_at = confirmation_expires_at

        stored_preview = InventoryOperationPreviewRead(
            transaction_id=transaction.id,
            operation_type="TRANSFER_RECEIVE",
            transaction_version=transaction.version,
            confirmation_token=None,
            confirmation_expires_at=confirmation_expires_at,
        )
        snapshot = stored_preview.model_dump(mode="json")
        snapshot["_extensions"] = {
            "preview_command": deepcopy(private_command),
        }
        transaction.response_snapshot_json = snapshot
        session.flush()

        return stored_preview.model_copy(
            update={"confirmation_token": confirmation_token}
        )

    def execute_receive(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
        *,
        command: Any,
        idempotency_key: str,
    ) -> TransferRead:
        self._require_admin(actor)
        payload = self._command_payload(command)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        transaction_id = self._required_positive_int(payload, "transaction_id")
        expected_transaction_version = self._required_positive_int(
            payload,
            "expected_transaction_version",
        )
        confirmation_token = self._required_confirmation_token(payload)
        execute_request_hash = snapshot_service.canonical_hash(payload)

        with session.begin_nested():
            transfer = self.transfer_repository.lock_transfer(
                session,
                actor.tenant_id,
                transfer_id,
            )
            if transfer is None:
                self._raise_not_found(actor, "inventory_transfer", transfer_id)
            assert transfer is not None

            transaction = self.transaction_repository.lock_transaction(
                session,
                actor.tenant_id,
                transaction_id,
            )
            if transaction is None:
                self._raise_not_found(actor, "inventory_transaction", transaction_id)
            assert transaction is not None

            self._require_receive_transaction(
                actor,
                transaction,
                transfer_id=transfer.id,
            )

            if transaction.status != "PREVIEWED":
                return self._replay_dispatch_execute(
                    actor,
                    transaction,
                    idempotency_key=clean_key,
                    request_hash=execute_request_hash,
                )

            self._require_receivable_state(actor, transfer)
            self._require_transaction_version(
                actor,
                transaction,
                expected_version=expected_transaction_version,
            )
            self._require_confirmation_token(
                actor,
                transaction,
                confirmation_token,
            )
            self._require_confirmation_not_expired(actor, transaction)

            private_command = self._preview_command(actor, transaction)
            expected_transfer_version = self._required_positive_int(
                private_command,
                "expected_transfer_version",
            )
            self._require_transfer_version(
                actor,
                transfer,
                expected_version=expected_transfer_version,
            )

            private_lines = private_command.get("lines")
            if not isinstance(private_lines, list) or not private_lines:
                self._raise_dispatch_preview_invalid(actor, transaction.id)

            lines = self.transfer_repository.list_lines(
                session,
                actor.tenant_id,
                transfer.id,
            )
            line_by_id = {line.id: line for line in lines}
            delta_by_balance: dict[int, InventoryQuantityDelta] = {}
            version_by_balance: dict[int, int] = {}
            state_mutations_by_balance: dict[int, list[Any]] = {}
            received_by_line: dict[int, Decimal] = {}

            for preview_line in private_lines:
                if not isinstance(preview_line, dict):
                    self._raise_dispatch_preview_invalid(actor, transaction.id)

                line_id = self._required_positive_int(
                    preview_line,
                    "transfer_line_id",
                )
                line = line_by_id.get(line_id)
                if line is None:
                    self._raise_conflict(
                        actor,
                        "inventory transfer line changed after preview",
                        code="TRANSFER_STATE_CONFLICT",
                        details={
                            "transfer_id": transfer.id,
                            "transfer_line_id": line_id,
                            "conflict_object": "inventory_transfer_line",
                            "retryable": True,
                        },
                    )
                assert line is not None

                quantity = self._positive_decimal(preview_line, "quantity")
                target_balance_id = self._required_positive_int(
                    preview_line,
                    "target_balance_id",
                )
                expected_target_version = self._required_positive_int(
                    preview_line,
                    "expected_target_version",
                )

                if target_balance_id != line.target_balance_id:
                    self._raise_conflict(
                        actor,
                        "inventory transfer target changed after preview",
                        code="TRANSFER_STATE_CONFLICT",
                        details={
                            "transfer_id": transfer.id,
                            "transfer_line_id": line.id,
                            "conflict_object": "inventory_transfer_line",
                            "retryable": True,
                        },
                    )

                remaining = line.dispatched_quantity - line.received_quantity
                if quantity > remaining:
                    self._raise_receive_exceeds_dispatch(
                        actor,
                        transfer_id=transfer.id,
                        line_id=line.id,
                        requested=quantity,
                        remaining=remaining,
                    )

                self._merge_dispatch_delta(
                    delta_by_balance,
                    version_by_balance,
                    balance_id=target_balance_id,
                    expected_version=expected_target_version,
                    on_hand=quantity,
                    in_transit=-quantity,
                )
                received_by_line[line.id] = quantity

                if line.serial_item_id is not None:
                    from app.schemas.inventory_operation import InventoryStateMutation

                    state_mutation = InventoryStateMutation(
                        serial_item_id=line.serial_item_id,
                        state_before={
                            "warehouse_id": transfer.source_warehouse_id,
                            "location_id": transfer.source_location_id,
                        },
                        state_after={
                            "warehouse_id": transfer.target_warehouse_id,
                            "location_id": transfer.target_location_id,
                        },
                    )
                    state_mutations_by_balance.setdefault(
                        target_balance_id,
                        [],
                    ).append(state_mutation)

            mutations = tuple(
                InventoryBalanceMutation(
                    balance_id=balance_id,
                    expected_version=version_by_balance[balance_id],
                    deltas=delta_by_balance[balance_id],
                    state_mutations=tuple(
                        state_mutations_by_balance.get(balance_id, ())
                    ),
                )
                for balance_id in sorted(delta_by_balance)
            )

            plan = InventoryMutationPlan(
                operation_type="TRANSFER_RECEIVE",
                reference_type="INVENTORY_TRANSFER",
                reference_id=str(transfer.id),
                reason=transfer.reason,
                mutations=mutations,
                audit_context={
                    "transfer_id": transfer.id,
                    "transfer_line_ids": sorted(received_by_line),
                    "high_risk_preview": True,
                },
            )

            self.transaction_service.apply_plan_to_transaction(
                session,
                actor,
                transaction=transaction,
                plan=plan,
                required_role=MaintenanceRole.ADMIN,
            )

            for line in lines:
                receive_quantity = received_by_line.get(line.id)
                if receive_quantity is None:
                    continue
                line.received_quantity += receive_quantity
                line.version += 1

            completed = all(
                line.received_quantity == line.dispatched_quantity
                for line in lines
            )
            if completed:
                transfer.status = "COMPLETED"
                transfer.completed_at = utc_now()
            else:
                transfer.status = "PARTIALLY_RECEIVED"
            transfer.version += 1
            session.flush()

            result = self._read_transfer(transfer, lines)
            self._store_dispatch_execute_snapshot(
                session,
                transaction,
                idempotency_key=clean_key,
                request_hash=execute_request_hash,
                result=result,
            )
            return result

    def _replay_receive_preview(
        self,
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        transfer_id: int,
        request_hash: str,
    ) -> InventoryOperationPreviewRead:
        self._require_receive_transaction(
            actor,
            transaction,
            transfer_id=transfer_id,
        )
        if transaction.request_hash != request_hash:
            self._raise_conflict(
                actor,
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )

        snapshot = transaction.response_snapshot_json
        if not isinstance(snapshot, dict):
            self._raise_idempotent_unavailable(actor)
        assert isinstance(snapshot, dict)

        public_snapshot = deepcopy(snapshot)
        public_snapshot.pop("_extensions", None)
        try:
            preview = InventoryOperationPreviewRead.model_validate(public_snapshot)
        except ValidationError as exc:
            error = ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
            error.request_id = actor.request_id
            raise error from exc

        return preview.model_copy(update={"confirmation_token": None})

    @staticmethod
    def _require_receive_transaction(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        transfer_id: int,
    ) -> None:
        valid = (
            transaction.operation_type == "TRANSFER_RECEIVE"
            and transaction.reference_type == "INVENTORY_TRANSFER"
            and transaction.reference_id == str(transfer_id)
        )
        if valid:
            return

        error = ConflictError(
            "inventory operation state conflict",
            code="INVENTORY_OPERATION_STATE_CONFLICT",
            details={
                "transaction_id": transaction.id,
                "conflict_object": "inventory_transaction",
                "retryable": False,
            },
        )
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _require_receivable_state(
        actor: ActorContext,
        transfer,
    ) -> None:
        if transfer.status in {"DISPATCHED", "PARTIALLY_RECEIVED"}:
            return

        error = ConflictError(
            "inventory transfer state conflict",
            code="TRANSFER_STATE_CONFLICT",
            details={
                "transfer_id": transfer.id,
                "status": transfer.status,
                "conflict_object": "inventory_transfer",
                "retryable": False,
            },
        )
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _positive_decimal(
        payload: dict[str, Any],
        field_name: str,
    ) -> Decimal:
        raw = payload.get(field_name)
        if isinstance(raw, bool):
            raise BusinessValidationError(
                f"{field_name} must be positive",
                code="TRANSFER_STATE_CONFLICT",
            )
        try:
            value = Decimal(str(raw))
        except Exception as exc:
            raise BusinessValidationError(
                f"{field_name} must be positive",
                code="TRANSFER_STATE_CONFLICT",
            ) from exc
        if not value.is_finite() or value <= 0:
            raise BusinessValidationError(
                f"{field_name} must be positive",
                code="TRANSFER_STATE_CONFLICT",
            )
        return value

    @staticmethod
    def _raise_receive_exceeds_dispatch(
        actor: ActorContext,
        *,
        transfer_id: int,
        line_id: int,
        requested: Decimal,
        remaining: Decimal,
    ) -> None:
        error = ConflictError(
            "transfer receipt exceeds dispatched quantity",
            code="TRANSFER_RECEIPT_EXCEEDS_DISPATCH",
            details={
                "transfer_id": transfer_id,
                "transfer_line_id": line_id,
                "requested_quantity": format(requested, ".4f"),
                "remaining_quantity": format(remaining, ".4f"),
                "conflict_object": "inventory_transfer_line",
                "retryable": False,
            },
        )
        error.request_id = actor.request_id
        raise error

    # TASK 7 GREEN SLICE 4 CANCEL

    def cancel(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TransferRead:
        from sqlalchemy.exc import IntegrityError

        from app.repositories.inventory_target_receipt_repository import (
            inventory_target_receipt_repository,
        )

        self._require_admin(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)

        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version <= 0
        ):
            self._raise_validation(
                actor,
                "expected_version must be a positive integer",
                code="TRANSFER_STATE_CONFLICT",
                details={
                    "conflict_object": "inventory_transfer",
                    "retryable": False,
                },
            )

        request_payload = {
            "operation_type": "TRANSFER_CANCEL",
            "transfer_id": transfer_id,
            "expected_version": expected_version,
        }
        request_hash = snapshot_service.canonical_hash(request_payload)
        receipt_key = (
            "transfer-cancel:"
            + hashlib.sha256(clean_key.encode("utf-8")).hexdigest()
        )

        def replay_receipt(receipt) -> TransferRead:
            if receipt.source_hash != request_hash:
                self._raise_conflict(
                    actor,
                    "idempotency key was reused",
                    code="IDEMPOTENCY_KEY_REUSED",
                    details={
                        "conflict_object": "inventory_transfer",
                        "retryable": False,
                    },
                )

            if not isinstance(receipt.result_json, dict):
                self._raise_idempotent_unavailable(actor)

            try:
                return TransferRead.model_validate(receipt.result_json)
            except ValidationError as exc:
                error = ConflictError(
                    "idempotent response is unavailable",
                    code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                    details={
                        "conflict_object": "inventory_transfer",
                        "retryable": False,
                    },
                )
                error.request_id = actor.request_id
                raise error from exc

        existing = inventory_target_receipt_repository.get(
            session,
            actor.tenant_id,
            receipt_key,
        )
        if existing is not None:
            return replay_receipt(existing)

        try:
            with session.begin_nested():
                receipt = inventory_target_receipt_repository.get(
                    session,
                    actor.tenant_id,
                    receipt_key,
                )
                if receipt is not None:
                    return replay_receipt(receipt)

                receipt = inventory_target_receipt_repository.create_pending(
                    session,
                    actor,
                    idempotency_key=receipt_key,
                    source_hash=request_hash,
                )

                transfer = self.transfer_repository.lock_transfer(
                    session,
                    actor.tenant_id,
                    transfer_id,
                )
                if transfer is None:
                    self._raise_not_found(
                        actor,
                        "inventory_transfer",
                        transfer_id,
                    )
                assert transfer is not None

                self._require_transfer_version(
                    actor,
                    transfer,
                    expected_version=expected_version,
                )

                if transfer.status != "DRAFT":
                    self._raise_conflict(
                        actor,
                        "inventory transfer state conflict",
                        code="TRANSFER_STATE_CONFLICT",
                        details={
                            "transfer_id": transfer.id,
                            "status": transfer.status,
                            "conflict_object": "inventory_transfer",
                            "retryable": False,
                        },
                    )

                transfer.status = "CANCELLED"
                transfer.cancelled_at = utc_now()
                transfer.version += 1
                session.flush()

                lines = self.transfer_repository.list_lines(
                    session,
                    actor.tenant_id,
                    transfer.id,
                )
                result = self._read_transfer(transfer, lines)

                inventory_target_receipt_repository.complete(
                    session,
                    receipt,
                    result=result.model_dump(mode="json"),
                    completed_at=utc_now(),
                )
                return result
        except IntegrityError as exc:
            winner = inventory_target_receipt_repository.get(
                session,
                actor.tenant_id,
                receipt_key,
            )
            if winner is not None:
                return replay_receipt(winner)
            raise exc

    # CREATE HELPERS
    # ========================================================

    def _claim_receipt(
        self,
        session: Session,
        actor: ActorContext,
        *,
        receipt_key: str,
        request_hash: str,
    ):
        try:
            with session.begin_nested():
                return (
                    self.receipt_repository
                    .create_pending(
                        session,
                        actor,
                        idempotency_key=(
                            receipt_key
                        ),
                        source_hash=(
                            request_hash
                        ),
                    )
                )
        except IntegrityError:
            existing = (
                self.receipt_repository
                .get(
                    session,
                    actor.tenant_id,
                    receipt_key,
                )
            )

            if existing is None:
                raise

            if (
                existing.source_hash
                != request_hash
            ):
                self._raise_conflict(
                    actor,
                    "idempotency key was reused",
                    code=(
                        "IDEMPOTENCY_KEY_REUSED"
                    ),
                    details={
                        "conflict_object": (
                            "inventory_transfer"
                        ),
                        "retryable": False,
                    },
                )

            if (
                existing.status
                == InventoryTargetReceiptStatus.COMPLETED
                and existing.result_json
                is not None
            ):
                return existing

            self._raise_conflict(
                actor,
                "inventory transfer create is already in progress",
                code=(
                    "INVENTORY_OPERATION_STATE_CONFLICT"
                ),
                details={
                    "conflict_object": (
                        "inventory_transfer"
                    ),
                    "retryable": True,
                },
            )

    def _replay_receipt(
        self,
        session: Session,
        actor: ActorContext,
        *,
        receipt_key: str,
        request_hash: str,
    ) -> TransferRead | None:
        receipt = (
            self.receipt_repository.get(
                session,
                actor.tenant_id,
                receipt_key,
            )
        )

        if receipt is None:
            return None

        return self._receipt_result(
            actor,
            receipt,
            request_hash=request_hash,
        )

    def _receipt_result(
        self,
        actor: ActorContext,
        receipt,
        *,
        request_hash: str,
    ) -> TransferRead:
        if (
            receipt.source_hash
            != request_hash
        ):
            self._raise_conflict(
                actor,
                "idempotency key was reused",
                code=(
                    "IDEMPOTENCY_KEY_REUSED"
                ),
                details={
                    "conflict_object": (
                        "inventory_transfer"
                    ),
                    "retryable": False,
                },
            )

        if (
            receipt.status
            != InventoryTargetReceiptStatus.COMPLETED
            or receipt.result_json is None
        ):
            self._raise_conflict(
                actor,
                "inventory transfer create is already in progress",
                code=(
                    "INVENTORY_OPERATION_STATE_CONFLICT"
                ),
                details={
                    "conflict_object": (
                        "inventory_transfer"
                    ),
                    "retryable": True,
                },
            )

        return TransferRead.model_validate(
            receipt.result_json
        )

    # ========================================================
    # DISPATCH HELPERS
    # ========================================================

    def _replay_dispatch_preview(
        self,
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        transfer_id: int,
        request_hash: str,
    ) -> InventoryOperationPreviewRead:
        self._require_dispatch_transaction(
            actor,
            transaction,
            transfer_id=transfer_id,
        )

        if (
            transaction.request_hash
            != request_hash
        ):
            self._raise_conflict(
                actor,
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": (
                        "inventory_transaction"
                    ),
                    "retryable": False,
                },
            )

        snapshot = (
            transaction
            .response_snapshot_json
        )

        if not isinstance(
            snapshot,
            dict,
        ):
            self._raise_idempotent_unavailable(
                actor
            )

        assert isinstance(
            snapshot,
            dict,
        )

        public_snapshot = deepcopy(
            snapshot
        )
        public_snapshot.pop(
            "_extensions",
            None,
        )

        try:
            preview = (
                InventoryOperationPreviewRead
                .model_validate(
                    public_snapshot
                )
            )
        except ValidationError as exc:
            raise ConflictError(
                "idempotent response is unavailable",
                code=(
                    "IDEMPOTENT_RESPONSE_UNAVAILABLE"
                ),
                details={
                    "conflict_object": (
                        "inventory_transaction"
                    ),
                    "retryable": False,
                },
            ) from exc

        return preview.model_copy(
            update={
                "confirmation_token": None
            }
        )

    def _replay_dispatch_execute(
        self,
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> TransferRead:
        snapshot = (
            transaction
            .response_snapshot_json
        )

        if not isinstance(
            snapshot,
            dict,
        ):
            self._raise_idempotent_unavailable(
                actor
            )

        assert isinstance(
            snapshot,
            dict,
        )

        extensions = snapshot.get(
            "_extensions"
        )

        execute_extension = (
            extensions.get(
                "transfer_execute"
            )
            if isinstance(
                extensions,
                dict,
            )
            else None
        )

        if not isinstance(
            execute_extension,
            dict,
        ):
            self._raise_conflict(
                actor,
                "inventory operation state conflict",
                code=(
                    "INVENTORY_OPERATION_STATE_CONFLICT"
                ),
                details={
                    "transaction_id": (
                        transaction.id
                    ),
                    "status": (
                        transaction.status
                    ),
                    "conflict_object": (
                        "inventory_transaction"
                    ),
                    "retryable": False,
                },
            )

        assert isinstance(
            execute_extension,
            dict,
        )

        if (
            execute_extension.get(
                "idempotency_key"
            )
            != idempotency_key
            or execute_extension.get(
                "request_hash"
            )
            != request_hash
        ):
            self._raise_conflict(
                actor,
                "idempotency key was reused",
                code=(
                    "IDEMPOTENCY_KEY_REUSED"
                ),
                details={
                    "conflict_object": (
                        "inventory_transaction"
                    ),
                    "retryable": False,
                },
            )

        result = execute_extension.get(
            "result"
        )

        if not isinstance(
            result,
            dict,
        ):
            self._raise_idempotent_unavailable(
                actor
            )

        assert isinstance(
            result,
            dict,
        )

        return TransferRead.model_validate(
            result
        )

    @staticmethod
    def _store_dispatch_execute_snapshot(
        session: Session,
        transaction: InventoryTransaction,
        *,
        idempotency_key: str,
        request_hash: str,
        result: TransferRead,
    ) -> None:
        snapshot = deepcopy(
            transaction
            .response_snapshot_json
        )

        if not isinstance(
            snapshot,
            dict,
        ):
            raise ConflictError(
                "idempotent response is unavailable",
                code=(
                    "IDEMPOTENT_RESPONSE_UNAVAILABLE"
                ),
                details={
                    "conflict_object": (
                        "inventory_transaction"
                    ),
                    "retryable": False,
                },
            )

        extensions = snapshot.get(
            "_extensions"
        )

        if not isinstance(
            extensions,
            dict,
        ):
            extensions = {}

        extensions["transfer_execute"] = {
            "idempotency_key": (
                idempotency_key
            ),
            "request_hash": request_hash,
            "result": result.model_dump(
                mode="json"
            ),
        }

        snapshot["_extensions"] = (
            extensions
        )

        transaction.response_snapshot_json = (
            snapshot
        )
        session.flush()

    @staticmethod
    def _merge_dispatch_delta(
        delta_by_balance: dict[
            int,
            InventoryQuantityDelta,
        ],
        version_by_balance: dict[
            int,
            int,
        ],
        *,
        balance_id: int,
        expected_version: int,
        on_hand: Decimal = Decimal(
            "0.0000"
        ),
        in_transit: Decimal = Decimal(
            "0.0000"
        ),
    ) -> None:
        existing_version = (
            version_by_balance.get(
                balance_id
            )
        )

        if (
            existing_version is not None
            and existing_version
            != expected_version
        ):
            raise ConflictError(
                "inventory balance version conflict",
                code=(
                    "INVENTORY_VERSION_CONFLICT"
                ),
                details={
                    "balance_id": balance_id,
                    "expected_version": (
                        existing_version
                    ),
                    "actual_version": (
                        expected_version
                    ),
                    "conflict_object": (
                        "inventory_balance"
                    ),
                    "retryable": True,
                },
            )

        version_by_balance[
            balance_id
        ] = expected_version

        existing = delta_by_balance.get(
            balance_id
        )

        if existing is None:
            delta_by_balance[
                balance_id
            ] = InventoryQuantityDelta(
                on_hand=on_hand,
                in_transit=in_transit,
            )
            return

        delta_by_balance[
            balance_id
        ] = InventoryQuantityDelta(
            on_hand=(
                existing.on_hand
                + on_hand
            ),
            reserved=(
                existing.reserved
            ),
            damaged=(
                existing.damaged
            ),
            quarantined=(
                existing.quarantined
            ),
            in_transit=(
                existing.in_transit
                + in_transit
            ),
        )

    @staticmethod
    def _require_dispatch_transaction(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        transfer_id: int,
    ) -> None:
        valid = (
            transaction.operation_type
            == "TRANSFER_DISPATCH"
            and transaction.reference_type
            == "INVENTORY_TRANSFER"
            and transaction.reference_id
            == str(transfer_id)
        )

        if valid:
            return

        error = ConflictError(
            "inventory operation state conflict",
            code=(
                "INVENTORY_OPERATION_STATE_CONFLICT"
            ),
            details={
                "transaction_id": (
                    transaction.id
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _require_dispatch_draft(
        actor: ActorContext,
        transfer,
    ) -> None:
        if transfer.status == "DRAFT":
            return

        error = ConflictError(
            "inventory transfer state conflict",
            code="TRANSFER_STATE_CONFLICT",
            details={
                "transfer_id": transfer.id,
                "status": transfer.status,
                "conflict_object": (
                    "inventory_transfer"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _require_transfer_version(
        actor: ActorContext,
        transfer,
        *,
        expected_version: int,
    ) -> None:
        if (
            transfer.version
            == expected_version
        ):
            return

        error = ConflictError(
            "inventory transfer version conflict",
            code="TRANSFER_STATE_CONFLICT",
            details={
                "transfer_id": transfer.id,
                "expected_version": (
                    expected_version
                ),
                "actual_version": (
                    transfer.version
                ),
                "conflict_object": (
                    "inventory_transfer"
                ),
                "retryable": True,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _require_transaction_version(
        actor: ActorContext,
        transaction: InventoryTransaction,
        *,
        expected_version: int,
    ) -> None:
        if (
            transaction.version
            == expected_version
        ):
            return

        error = ConflictError(
            "inventory transaction version conflict",
            code=(
                "INVENTORY_TRANSACTION_VERSION_CONFLICT"
            ),
            details={
                "transaction_id": (
                    transaction.id
                ),
                "expected_version": (
                    expected_version
                ),
                "actual_version": (
                    transaction.version
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": True,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _require_confirmation_token(
        actor: ActorContext,
        transaction: InventoryTransaction,
        token: str,
    ) -> None:
        stored_hash = (
            transaction
            .confirmation_token_hash
        )
        presented_hash = (
            hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest()
        )

        valid = (
            isinstance(
                stored_hash,
                str,
            )
            and hmac.compare_digest(
                stored_hash,
                presented_hash,
            )
        )

        if valid:
            return

        error = ConflictError(
            "confirmation token is invalid",
            code=(
                "INVENTORY_CONFIRMATION_TOKEN_INVALID"
            ),
            details={
                "transaction_id": (
                    transaction.id
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @classmethod
    def _require_confirmation_not_expired(
        cls,
        actor: ActorContext,
        transaction: InventoryTransaction,
    ) -> None:
        expires_at = (
            transaction
            .confirmation_expires_at
        )

        if (
            expires_at is not None
            and cls._as_utc(
                expires_at
            )
            > utc_now()
        ):
            return

        error = ConflictError(
            "confirmation token has expired",
            code=(
                "INVENTORY_CONFIRMATION_EXPIRED"
            ),
            details={
                "transaction_id": (
                    transaction.id
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": True,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _preview_command(
        actor: ActorContext,
        transaction: InventoryTransaction,
    ) -> dict[str, Any]:
        snapshot = (
            transaction
            .response_snapshot_json
        )

        if not isinstance(
            snapshot,
            dict,
        ):
            InventoryTransferService._raise_preview_unavailable(
                actor,
                transaction.id,
            )

        assert isinstance(
            snapshot,
            dict,
        )

        extensions = snapshot.get(
            "_extensions"
        )

        preview_command = (
            extensions.get(
                "preview_command"
            )
            if isinstance(
                extensions,
                dict,
            )
            else None
        )

        if not isinstance(
            preview_command,
            dict,
        ):
            InventoryTransferService._raise_preview_unavailable(
                actor,
                transaction.id,
            )

        assert isinstance(
            preview_command,
            dict,
        )

        return deepcopy(
            preview_command
        )

    @staticmethod
    def _raise_preview_unavailable(
        actor: ActorContext,
        transaction_id: int,
    ) -> None:
        error = ConflictError(
            "preview command is unavailable",
            code=(
                "INVENTORY_OPERATION_STATE_CONFLICT"
            ),
            details={
                "transaction_id": (
                    transaction_id
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _raise_dispatch_preview_invalid(
        actor: ActorContext,
        transaction_id: int,
    ) -> None:
        error = ConflictError(
            "dispatch preview command is invalid",
            code=(
                "INVENTORY_OPERATION_STATE_CONFLICT"
            ),
            details={
                "transaction_id": (
                    transaction_id
                ),
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _require_balance_version(
        actor: ActorContext,
        balance: InventoryBalance,
        *,
        expected_version: int,
    ) -> None:
        if (
            balance.version
            == expected_version
        ):
            return

        error = ConflictError(
            "inventory balance version conflict",
            code=(
                "INVENTORY_VERSION_CONFLICT"
            ),
            details={
                "balance_id": balance.id,
                "expected_version": (
                    expected_version
                ),
                "actual_version": (
                    balance.version
                ),
                "conflict_object": (
                    "inventory_balance"
                ),
                "retryable": True,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    def _require_dispatch_balance(
        self,
        session: Session,
        actor: ActorContext,
        balance_id: int,
    ) -> InventoryBalance:
        balance = (
            self.ledger_repository
            .get_balance(
                session,
                actor.tenant_id,
                balance_id,
            )
        )

        if balance is None:
            self._raise_not_found(
                actor,
                "inventory_balance",
                balance_id,
            )

        assert balance is not None

        session.refresh(balance)

        return balance

    # ========================================================
    # SHARED DOMAIN HELPERS
    # ========================================================

    def _require_source_balance(
        self,
        session: Session,
        actor: ActorContext,
        balance_id: int,
    ) -> InventoryBalance:
        balance = session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id
                == actor.tenant_id,
                InventoryBalance.id
                == balance_id,
            )
        )

        if balance is None:
            self._raise_not_found(
                actor,
                "inventory_balance",
                balance_id,
            )

        assert balance is not None
        return balance

    def _require_target_location(
        self,
        session: Session,
        actor: ActorContext,
        *,
        warehouse_id: int,
        location_id: int,
    ) -> WarehouseLocation:
        location = session.scalar(
            select(WarehouseLocation).where(
                WarehouseLocation.tenant_id
                == actor.tenant_id,
                WarehouseLocation.id
                == location_id,
                WarehouseLocation.warehouse_id
                == warehouse_id,
            )
        )

        if location is None:
            self._raise_not_found(
                actor,
                "warehouse_location",
                location_id,
            )

        assert location is not None
        return location

    def _require_source_identity(
        self,
        actor: ActorContext,
        source: InventoryBalance,
        *,
        command: TransferCreateCommand,
        line,
    ) -> None:
        matches = (
            source.warehouse_id
            == command.source_warehouse_id
            and source.location_id
            == command.source_location_id
            and source.spare_part_id
            == line.spare_part_id
            and source.lot_id
            == line.lot_id
        )

        if matches:
            return

        self._raise_validation(
            actor,
            "transfer source identity does not match balance",
            code="TRANSFER_STATE_CONFLICT",
            details={
                "balance_id": source.id,
                "conflict_object": (
                    "inventory_balance"
                ),
                "retryable": False,
            },
        )

    def _require_serial_contract(
        self,
        session: Session,
        actor: ActorContext,
        source: InventoryBalance,
        *,
        serial_item_id: int | None,
        quantity,
    ) -> None:
        if serial_item_id is None:
            return

        serial = session.scalar(
            select(SerializedItem).where(
                SerializedItem.tenant_id
                == actor.tenant_id,
                SerializedItem.id
                == serial_item_id,
            )
        )

        if serial is None:
            self._raise_not_found(
                actor,
                "serialized_item",
                serial_item_id,
            )

        assert serial is not None

        matches = (
            serial.spare_part_id
            == source.spare_part_id
            and serial.warehouse_id
            == source.warehouse_id
            and serial.location_id
            == source.location_id
            and serial.lot_id
            == source.lot_id
            and serial.status
            == "IN_STOCK"
            and quantity == 1
        )

        if matches:
            return

        self._raise_validation(
            actor,
            "serialized item cannot be transferred from source",
            code="SERIAL_STATE_CONFLICT",
            details={
                "serial_item_id": (
                    serial.id
                ),
                "balance_id": source.id,
                "conflict_object": (
                    "serialized_item"
                ),
                "retryable": False,
            },
        )

    @staticmethod
    def _read_transfer(
        transfer,
        lines,
    ) -> TransferRead:
        return TransferRead(
            id=transfer.id,
            tenant_id=transfer.tenant_id,
            status=transfer.status,
            source_warehouse_id=(
                transfer.source_warehouse_id
            ),
            source_location_id=(
                transfer.source_location_id
            ),
            target_warehouse_id=(
                transfer.target_warehouse_id
            ),
            target_location_id=(
                transfer.target_location_id
            ),
            reference_type=(
                transfer.reference_type
            ),
            reference_id=(
                transfer.reference_id
            ),
            reason=transfer.reason,
            actor_user_id=(
                transfer.actor_user_id
            ),
            actor_roles=list(
                transfer.actor_roles_json
            ),
            request_id=(
                transfer.request_id
            ),
            version=transfer.version,
            dispatched_at=(
                transfer.dispatched_at
            ),
            completed_at=(
                transfer.completed_at
            ),
            cancelled_at=(
                transfer.cancelled_at
            ),
            lines=tuple(
                TransferLineRead(
                    id=line.id,
                    transfer_id=(
                        line.transfer_id
                    ),
                    spare_part_id=(
                        line.spare_part_id
                    ),
                    source_balance_id=(
                        line.source_balance_id
                    ),
                    target_balance_id=(
                        line.target_balance_id
                    ),
                    lot_id=line.lot_id,
                    serial_item_id=(
                        line.serial_item_id
                    ),
                    requested_quantity=(
                        line.requested_quantity
                    ),
                    dispatched_quantity=(
                        line.dispatched_quantity
                    ),
                    received_quantity=(
                        line.received_quantity
                    ),
                    expected_source_version=(
                        line.expected_source_version
                    ),
                    expected_target_version=(
                        line.expected_target_version
                    ),
                    version=line.version,
                )
                for line in lines
            ),
        )

    # ========================================================
    # GENERIC INPUT / ERROR / RBAC HELPERS
    # ========================================================

    @staticmethod
    def _receipt_key(
        idempotency_key: str,
    ) -> str:
        digest = hashlib.sha256(
            idempotency_key.encode(
                "utf-8"
            )
        ).hexdigest()

        return (
            f"transfer-create:{digest}"
        )

    @staticmethod
    def _normalize_idempotency_key(
        idempotency_key: str,
    ) -> str:
        clean = (
            idempotency_key.strip()
            if isinstance(
                idempotency_key,
                str,
            )
            else ""
        )

        if not clean:
            raise BusinessValidationError(
                "idempotency key is required",
                code=(
                    "IDEMPOTENCY_KEY_REQUIRED"
                ),
            )

        if len(clean) > 128:
            raise BusinessValidationError(
                "idempotency key is invalid",
                code=(
                    "INVALID_IDEMPOTENCY_KEY"
                ),
            )

        return clean

    @staticmethod
    def _command_payload(
        command: Any,
    ) -> dict[str, Any]:
        if isinstance(
            command,
            BaseModel,
        ):
            raw = command.model_dump(
                mode="json"
            )
        elif isinstance(
            command,
            dict,
        ):
            raw = deepcopy(command)
        else:
            raise BusinessValidationError(
                "inventory transfer command is invalid",
                code=(
                    "TRANSFER_STATE_CONFLICT"
                ),
            )

        normalized = (
            snapshot_service.normalize(
                raw
            )
        )

        if not isinstance(
            normalized,
            dict,
        ):
            raise BusinessValidationError(
                "inventory transfer command is invalid",
                code=(
                    "TRANSFER_STATE_CONFLICT"
                ),
            )

        return normalized

    @staticmethod
    def _required_positive_int(
        payload: dict[str, Any],
        field_name: str,
    ) -> int:
        value = payload.get(
            field_name
        )

        if (
            isinstance(value, bool)
            or not isinstance(
                value,
                int,
            )
            or value <= 0
        ):
            raise BusinessValidationError(
                f"{field_name} must be a positive integer",
                code=(
                    "TRANSFER_STATE_CONFLICT"
                ),
            )

        return value

    @staticmethod
    def _required_confirmation_token(
        payload: dict[str, Any],
    ) -> str:
        token = payload.get(
            "confirmation_token"
        )

        if (
            not isinstance(
                token,
                str,
            )
            or not token
        ):
            raise BusinessValidationError(
                "confirmation token is required",
                code=(
                    "INVENTORY_CONFIRMATION_TOKEN_INVALID"
                ),
            )

        return token

    @staticmethod
    def _as_utc(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    @staticmethod
    def _require_contributor(
        actor: ActorContext,
    ) -> None:
        if (
            _ROLE_RANK[actor.role]
            >= _ROLE_RANK[
                MaintenanceRole.CONTRIBUTOR
            ]
        ):
            return

        raise InsufficientMaintenanceRoleError(
            required_role=(
                MaintenanceRole.CONTRIBUTOR.value
            ),
            actual_role=(
                actor.role.value
            ),
            request_id=(
                actor.request_id
            ),
        )

    @staticmethod
    def _require_admin(
        actor: ActorContext,
    ) -> None:
        if (
            actor.role
            is MaintenanceRole.ADMIN
        ):
            return

        raise InsufficientMaintenanceRoleError(
            required_role=(
                MaintenanceRole.ADMIN.value
            ),
            actual_role=(
                actor.role.value
            ),
            request_id=(
                actor.request_id
            ),
        )

    @staticmethod
    def _raise_not_found(
        actor: ActorContext,
        resource: str,
        resource_id: int,
    ) -> None:
        error = NotFoundError(
            resource,
            resource_id,
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _raise_validation(
        actor: ActorContext,
        message: str,
        *,
        code: str,
        details: dict | None = None,
    ) -> None:
        error = BusinessValidationError(
            message,
            code=code,
            details=details or {},
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _raise_conflict(
        actor: ActorContext,
        message: str,
        *,
        code: str,
        details: dict,
    ) -> None:
        error = ConflictError(
            message,
            code=code,
            details=details,
        )
        error.request_id = (
            actor.request_id
        )
        raise error

    @staticmethod
    def _raise_idempotent_unavailable(
        actor: ActorContext,
    ) -> None:
        error = ConflictError(
            "idempotent response is unavailable",
            code=(
                "IDEMPOTENT_RESPONSE_UNAVAILABLE"
            ),
            details={
                "conflict_object": (
                    "inventory_transaction"
                ),
                "retryable": False,
            },
        )
        error.request_id = (
            actor.request_id
        )
        raise error
