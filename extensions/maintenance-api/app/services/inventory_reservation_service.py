from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    InventoryBalance,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
)
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository
from app.repositories.inventory_reservation_repository import (
    InventoryReservationRepository,
)
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
)
from app.schemas.inventory_reservation import (
    CancelCommand,
    ExpireCommand,
    InventoryReservationLineRead,
    InventoryReservationRead,
    IssueCommand,
    ReleaseCommand,
    ReservationQuantityLine,
    ReserveCommand,
    ReturnCommand,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_fefo_service import FEFOCandidate, select_fefo
from app.services.inventory_transaction_service import InventoryTransactionService
from app.services.snapshot_service import snapshot_service

OperationType = Literal["RESERVE", "UNRESERVE", "ISSUE", "RETURN"]
_ZERO = Decimal("0.0000")
_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_TERMINAL_RESERVATION_STATUSES = frozenset(
    {"FULFILLED", "RELEASED", "CANCELLED", "EXPIRED"}
)


class InventoryReservationService:
    def __init__(
        self,
        *,
        reservation_repository: InventoryReservationRepository | None = None,
        ledger_repository: InventoryLedgerRepository | None = None,
        transaction_repository: InventoryTransactionRepository | None = None,
        transaction_service: InventoryTransactionService | None = None,
    ) -> None:
        self.reservation_repository = (
            reservation_repository or InventoryReservationRepository()
        )
        self.ledger_repository = ledger_repository or InventoryLedgerRepository()
        self.transaction_repository = (
            transaction_repository or InventoryTransactionRepository()
        )
        self.transaction_service = transaction_service or InventoryTransactionService(
            transaction_repository=self.transaction_repository,
            ledger_repository=self.ledger_repository,
        )

    def reserve(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command: ReserveCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = self._request_hash("RESERVE", command)
        replay = self._replay_existing(
            session,
            actor,
            operation_type="RESERVE",
            idempotency_key=clean_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        candidates = self.ledger_repository.list_fefo_candidates(
            session,
            actor.tenant_id,
            spare_part_id=command.spare_part_id,
            warehouse_id=command.warehouse_id,
            location_id=command.location_id,
            lot_id=command.lot_id,
            serial_item_id=command.serial_item_id,
        )
        selection = select_fefo(
            candidates,
            command.requested_quantity,
            as_of=command.as_of,
        )
        if selection.unfilled_quantity > _ZERO and not command.allow_partial:
            error = BusinessValidationError(
                "available inventory cannot satisfy the reservation",
                code="INSUFFICIENT_AVAILABLE_INVENTORY",
                details={
                    "requested_quantity": format(command.requested_quantity, ".4f"),
                    "unfilled_quantity": format(selection.unfilled_quantity, ".4f"),
                },
            )
            error.request_id = actor.request_id
            raise error

        selected = self._selected_candidates(candidates, selection.lines)
        mutations: list[InventoryBalanceMutation] = []
        line_values: list[dict[str, Any]] = []
        for rank, (candidate, quantity) in enumerate(selected, start=1):
            expected_version = command.expected_balance_versions.get(
                candidate.balance_id
            )
            if expected_version is None:
                self._raise_conflict(
                    actor,
                    "expected balance version is missing",
                    details={
                        "balance_id": candidate.balance_id,
                        "conflict_object": "inventory_balance",
                        "retryable": True,
                    },
                )
            mutations.append(
                InventoryBalanceMutation(
                    balance_id=candidate.balance_id,
                    expected_version=expected_version,
                    deltas=InventoryQuantityDelta(reserved=quantity),
                )
            )
            line_values.append(
                {
                    "spare_part_id": command.spare_part_id,
                    "balance_id": candidate.balance_id,
                    "lot_id": candidate.lot_id,
                    "serial_item_id": candidate.serial_item_id,
                    "requested_quantity": quantity,
                    "reserved_quantity": quantity,
                    "expected_balance_version": expected_version,
                    "fefo_rank": rank,
                    "fefo_override_reason": command.fefo_override_reason,
                    "recommended_selection_json": {
                        "balance_id": candidate.balance_id,
                        "quantity": format(quantity, ".4f"),
                        "rank": rank,
                    },
                    "actual_selection_json": {
                        "balance_id": candidate.balance_id,
                        "quantity": format(quantity, ".4f"),
                        "rank": rank,
                    },
                }
            )
        if line_values and selection.unfilled_quantity > _ZERO:
            line_values[-1]["requested_quantity"] += selection.unfilled_quantity

        with session.begin_nested():
            replay = self._replay_existing(
                session,
                actor,
                operation_type="RESERVE",
                idempotency_key=clean_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay
            reservation = self.reservation_repository.create(
                session,
                actor=actor,
                owner_type=command.owner_type,
                owner_id=command.owner_id,
                expires_at=command.expires_at,
                allow_partial=command.allow_partial,
            )
            if mutations:
                transaction_read = self.transaction_service.apply_plan(
                    session,
                    actor,
                    plan=InventoryMutationPlan(
                        operation_type="RESERVE",
                        reference_type="INVENTORY_RESERVATION",
                        reference_id=str(reservation.id),
                        reason="reserve inventory",
                        mutations=tuple(mutations),
                        audit_context={
                            "reservation_id": reservation.id,
                            "owner_type": command.owner_type,
                            "owner_id": command.owner_id,
                            "requested_quantity": format(
                                command.requested_quantity, ".4f"
                            ),
                        },
                    ),
                    idempotency_key=clean_key,
                    required_role=MaintenanceRole.CONTRIBUTOR,
                )
                transaction_id = transaction_read.id
            else:
                transaction_id = self._create_empty_reservation_transaction(
                    session,
                    actor,
                    reservation=reservation,
                    idempotency_key=clean_key,
                    request_hash=request_hash,
                ).id
            lines = self.reservation_repository.create_lines(
                session,
                reservation=reservation,
                lines=line_values,
            )
            result = self._read_reservation(
                reservation,
                lines,
                requested_quantity=command.requested_quantity,
                line_errors=selection.warnings,
            )
            self._store_operation_snapshot(
                session,
                actor,
                transaction_id=transaction_id,
                request_hash=request_hash,
                result=result,
            )
            return result

    def issue(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: IssueCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        return self._change_reserved_quantities(
            session,
            actor,
            reservation_id,
            command=command,
            idempotency_key=idempotency_key,
            operation_type="ISSUE",
            direction="issue",
        )

    def release(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: ReleaseCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        return self._change_reserved_quantities(
            session,
            actor,
            reservation_id,
            command=command,
            idempotency_key=idempotency_key,
            operation_type="UNRESERVE",
            direction="release",
        )

    def return_items(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: ReturnCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = self._request_hash(
            "RETURN",
            command,
            reservation_id=reservation_id,
        )
        replay = self._replay_existing(
            session,
            actor,
            operation_type="RETURN",
            idempotency_key=clean_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            reservation, lines = self._lock_and_validate(
                session,
                actor,
                reservation_id,
                expected_version=command.expected_version,
                allow_terminal=True,
            )
            line_by_id = {line.id: line for line in lines}
            issue_transaction_ids = {item.issue_transaction_id for item in command.lines}
            if len(issue_transaction_ids) != 1:
                self._raise_validation(
                    actor,
                    "return lines must reference one issue transaction",
                    code="RETURN_ISSUE_REFERENCE_INVALID",
                )
            issue_transaction_id = next(iter(issue_transaction_ids))
            issue_transaction = self.transaction_repository.get_transaction(
                session,
                actor.tenant_id,
                issue_transaction_id,
            )
            if issue_transaction is None or issue_transaction.operation_type != "ISSUE":
                self._raise_validation(
                    actor,
                    "return must reference an issue transaction",
                    code="RETURN_ISSUE_REFERENCE_INVALID",
                )

            mutations: list[InventoryBalanceMutation] = []
            for item in self._unique_command_lines(command.lines, actor):
                line = line_by_id.get(item.reservation_line_id)
                if line is None or item.quantity > line.issued_quantity:
                    self._raise_validation(
                        actor,
                        "return quantity exceeds issued quantity",
                        code="RETURN_QUANTITY_INVALID",
                    )
                balance = self._require_balance(session, actor, line.balance_id)
                mutations.append(
                    InventoryBalanceMutation(
                        balance_id=line.balance_id,
                        expected_version=balance.version,
                        deltas=InventoryQuantityDelta(on_hand=item.quantity),
                    )
                )

            transaction_read = self.transaction_service.apply_plan(
                session,
                actor,
                plan=InventoryMutationPlan(
                    operation_type="RETURN",
                    reference_type="INVENTORY_TRANSACTION",
                    reference_id=str(issue_transaction_id),
                    reason="return issued inventory",
                    mutations=tuple(mutations),
                    audit_context={"reservation_id": reservation.id},
                ),
                idempotency_key=clean_key,
                required_role=MaintenanceRole.CONTRIBUTOR,
            )
            reservation.version += 1
            session.flush()
            result = self._read_reservation(reservation, lines)
            self._store_operation_snapshot(
                session,
                actor,
                transaction_id=transaction_read.id,
                request_hash=request_hash,
                result=result,
            )
            return result

    def cancel(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: CancelCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        return self._release_terminal(
            session,
            actor,
            reservation_id,
            observed_version=command.expected_version,
            idempotency_key=idempotency_key,
            command=command,
            status="CANCELLED",
            reason="cancel inventory reservation",
        )

    def expire(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: ExpireCommand,
        idempotency_key: str,
    ) -> InventoryReservationRead:
        return self._release_terminal(
            session,
            actor,
            reservation_id,
            observed_version=command.observed_version,
            idempotency_key=idempotency_key,
            command=command,
            status="EXPIRED",
            reason="expire inventory reservation",
            as_of=command.as_of,
        )

    def _change_reserved_quantities(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        command: IssueCommand | ReleaseCommand,
        idempotency_key: str,
        operation_type: OperationType,
        direction: Literal["issue", "release"],
    ) -> InventoryReservationRead:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = self._request_hash(
            operation_type,
            command,
            reservation_id=reservation_id,
        )
        replay = self._replay_existing(
            session,
            actor,
            operation_type=operation_type,
            idempotency_key=clean_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            reservation, lines = self._lock_and_validate(
                session,
                actor,
                reservation_id,
                expected_version=command.expected_version,
            )
            command_lines: Sequence[ReservationQuantityLine]
            if direction == "release" and not command.lines:
                command_lines = tuple(
                    ReservationQuantityLine(
                        reservation_line_id=line.id,
                        quantity=self._remaining_quantity(line),
                    )
                    for line in lines
                    if self._remaining_quantity(line) > _ZERO
                )
            else:
                command_lines = command.lines
            command_lines = self._unique_command_lines(command_lines, actor)
            if not command_lines:
                self._raise_validation(
                    actor,
                    "reservation has no remaining quantity",
                    code="RESERVATION_NO_REMAINING_QUANTITY",
                )

            line_by_id = {line.id: line for line in lines}
            mutations: list[InventoryBalanceMutation] = []
            affected: list[tuple[InventoryReservationLine, Decimal]] = []
            for item in command_lines:
                line = line_by_id.get(item.reservation_line_id)
                if line is None:
                    self._raise_validation(
                        actor,
                        "reservation line was not found",
                        code="RESERVATION_LINE_NOT_FOUND",
                    )
                remaining = self._remaining_quantity(line)
                if item.quantity > remaining:
                    self._raise_validation(
                        actor,
                        "quantity exceeds remaining reserved inventory",
                        code="RESERVATION_QUANTITY_EXCEEDS_REMAINING",
                    )
                balance = self._require_balance(session, actor, line.balance_id)
                mutations.append(
                    InventoryBalanceMutation(
                        balance_id=line.balance_id,
                        expected_version=balance.version,
                        deltas=InventoryQuantityDelta(
                            on_hand=-item.quantity if direction == "issue" else _ZERO,
                            reserved=-item.quantity,
                        ),
                    )
                )
                affected.append((line, item.quantity))

            transaction_read = self.transaction_service.apply_plan(
                session,
                actor,
                plan=InventoryMutationPlan(
                    operation_type=operation_type,
                    reference_type="INVENTORY_RESERVATION",
                    reference_id=str(reservation.id),
                    reason=(
                        "issue reserved inventory"
                        if direction == "issue"
                        else "release reserved inventory"
                    ),
                    mutations=tuple(mutations),
                    audit_context={"reservation_id": reservation.id},
                ),
                idempotency_key=clean_key,
                required_role=MaintenanceRole.CONTRIBUTOR,
            )
            for line, quantity in affected:
                if direction == "issue":
                    line.issued_quantity += quantity
                else:
                    line.released_quantity += quantity
                line.version += 1
            reservation.version += 1
            if all(self._remaining_quantity(line) == _ZERO for line in lines):
                reservation.status = (
                    "FULFILLED" if direction == "issue" else "RELEASED"
                )
            elif any(line.issued_quantity > _ZERO for line in lines):
                reservation.status = "PARTIALLY_ISSUED"
            session.flush()
            result = self._read_reservation(reservation, lines)
            self._store_operation_snapshot(
                session,
                actor,
                transaction_id=transaction_read.id,
                request_hash=request_hash,
                result=result,
            )
            return result

    def _release_terminal(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        observed_version: int,
        idempotency_key: str,
        command: CancelCommand | ExpireCommand,
        status: Literal["CANCELLED", "EXPIRED"],
        reason: str,
        as_of: datetime | None = None,
    ) -> InventoryReservationRead:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = self._request_hash(
            "UNRESERVE",
            command,
            reservation_id=reservation_id,
            action=status,
        )
        replay = self._replay_existing(
            session,
            actor,
            operation_type="UNRESERVE",
            idempotency_key=clean_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        with session.begin_nested():
            reservation, lines = self._lock_and_validate(
                session,
                actor,
                reservation_id,
                expected_version=observed_version,
            )
            if status == "EXPIRED":
                if reservation.expires_at is None or self._as_utc(
                    reservation.expires_at
                ) > self._as_utc(as_of):
                    self._raise_validation(
                        actor,
                        "reservation has not expired",
                        code="RESERVATION_NOT_EXPIRED",
                    )
            mutations: list[InventoryBalanceMutation] = []
            affected: list[tuple[InventoryReservationLine, Decimal]] = []
            for line in lines:
                remaining = self._remaining_quantity(line)
                if remaining <= _ZERO:
                    continue
                balance = self._require_balance(session, actor, line.balance_id)
                mutations.append(
                    InventoryBalanceMutation(
                        balance_id=line.balance_id,
                        expected_version=balance.version,
                        deltas=InventoryQuantityDelta(reserved=-remaining),
                    )
                )
                affected.append((line, remaining))
            if not mutations:
                self._raise_validation(
                    actor,
                    "reservation has no remaining quantity",
                    code="RESERVATION_NO_REMAINING_QUANTITY",
                )
            transaction_read = self.transaction_service.apply_plan(
                session,
                actor,
                plan=InventoryMutationPlan(
                    operation_type="UNRESERVE",
                    reference_type="INVENTORY_RESERVATION",
                    reference_id=str(reservation.id),
                    reason=reason,
                    mutations=tuple(mutations),
                    audit_context={
                        "reservation_id": reservation.id,
                        "terminal_status": status,
                    },
                ),
                idempotency_key=clean_key,
                required_role=MaintenanceRole.CONTRIBUTOR,
            )
            for line, quantity in affected:
                line.released_quantity += quantity
                line.version += 1
            reservation.status = status
            reservation.version += 1
            session.flush()
            result = self._read_reservation(reservation, lines)
            self._store_operation_snapshot(
                session,
                actor,
                transaction_id=transaction_read.id,
                request_hash=request_hash,
                result=result,
            )
            return result

    def _lock_and_validate(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
        *,
        expected_version: int,
        allow_terminal: bool = False,
    ) -> tuple[InventoryReservation, list[InventoryReservationLine]]:
        aggregate = self.reservation_repository.lock_aggregate(
            session,
            actor.tenant_id,
            reservation_id,
        )
        if aggregate is None:
            error = NotFoundError("inventory_reservation", reservation_id)
            error.request_id = actor.request_id
            raise error
        reservation, lines = aggregate
        if reservation.version != expected_version:
            self._raise_conflict(
                actor,
                "inventory reservation version conflict",
                details={
                    "expected_version": expected_version,
                    "actual_version": reservation.version,
                    "conflict_object": "inventory_reservation",
                    "retryable": True,
                },
            )
        if not allow_terminal and reservation.status in _TERMINAL_RESERVATION_STATUSES:
            self._raise_conflict(
                actor,
                "inventory reservation is terminal",
                details={
                    "status": reservation.status,
                    "conflict_object": "inventory_reservation",
                    "retryable": False,
                },
            )
        return reservation, lines

    def _require_balance(
        self,
        session: Session,
        actor: ActorContext,
        balance_id: int,
    ) -> InventoryBalance:
        balance = self.ledger_repository.get_balance(
            session,
            actor.tenant_id,
            balance_id,
        )
        if balance is None:
            error = NotFoundError("inventory_balance", balance_id)
            error.request_id = actor.request_id
            raise error
        return balance

    @staticmethod
    def _selected_candidates(
        candidates: Sequence[FEFOCandidate],
        selection_lines: Sequence,
    ) -> list[tuple[FEFOCandidate, Decimal]]:
        candidates_by_balance: dict[int, list[FEFOCandidate]] = {}
        for candidate in candidates:
            candidates_by_balance.setdefault(candidate.balance_id, []).append(candidate)
        selected: list[tuple[FEFOCandidate, Decimal]] = []
        index_by_balance: dict[int, int] = {}
        for line in selection_lines:
            options = candidates_by_balance[line.balance_id]
            index = index_by_balance.get(line.balance_id, 0)
            candidate = options[min(index, len(options) - 1)]
            index_by_balance[line.balance_id] = index + 1
            if selected and selected[-1][0].balance_id == candidate.balance_id:
                previous_candidate, previous_quantity = selected[-1]
                selected[-1] = (
                    previous_candidate,
                    previous_quantity + line.quantity,
                )
            else:
                selected.append((candidate, line.quantity))
        return selected

    @staticmethod
    def _remaining_quantity(line: InventoryReservationLine) -> Decimal:
        return line.reserved_quantity - line.issued_quantity - line.released_quantity

    @staticmethod
    def _unique_command_lines(
        lines: Sequence[ReservationQuantityLine],
        actor: ActorContext,
    ) -> tuple[ReservationQuantityLine, ...]:
        ordered = tuple(lines)
        identifiers = [line.reservation_line_id for line in ordered]
        if len(identifiers) != len(set(identifiers)):
            error = BusinessValidationError(
                "reservation command contains duplicate lines",
                code="RESERVATION_DUPLICATE_LINE",
            )
            error.request_id = actor.request_id
            raise error
        return ordered

    def _replay_existing(
        self,
        session: Session,
        actor: ActorContext,
        *,
        operation_type: OperationType,
        idempotency_key: str,
        request_hash: str,
    ) -> InventoryReservationRead | None:
        transaction = self.transaction_repository.get_idempotent(
            session,
            actor.tenant_id,
            operation_type,
            idempotency_key,
        )
        if transaction is None:
            return None
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
            self._raise_conflict(
                actor,
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            )
        extensions = snapshot.get("_extensions")
        reservation_snapshot = (
            extensions.get("reservation") if isinstance(extensions, dict) else None
        )
        if not isinstance(reservation_snapshot, dict):
            self._raise_conflict(
                actor,
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            )
        return InventoryReservationRead.model_validate(
            deepcopy(reservation_snapshot)
        ).model_copy(deep=True)

    def _store_operation_snapshot(
        self,
        session: Session,
        actor: ActorContext,
        *,
        transaction_id: int,
        request_hash: str,
        result: InventoryReservationRead,
    ) -> None:
        transaction = self.transaction_repository.get_transaction(
            session,
            actor.tenant_id,
            transaction_id,
        )
        if transaction is None:
            raise RuntimeError("inventory transaction disappeared")
        transaction.request_hash = request_hash
        snapshot = deepcopy(transaction.response_snapshot_json)
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot["request_hash"] = request_hash
        extensions = snapshot.get("_extensions")
        if not isinstance(extensions, dict):
            extensions = {}
        extensions["reservation"] = result.model_dump(mode="json")
        snapshot["_extensions"] = extensions
        transaction.response_snapshot_json = snapshot
        session.flush()

    def _create_empty_reservation_transaction(
        self,
        session: Session,
        actor: ActorContext,
        *,
        reservation: InventoryReservation,
        idempotency_key: str,
        request_hash: str,
    ) -> InventoryTransaction:
        transaction = self.transaction_repository.create_transaction(
            session,
            actor=actor,
            operation_type="RESERVE",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            reason="reserve inventory",
            reference_type="INVENTORY_RESERVATION",
            reference_id=str(reservation.id),
        )
        transaction.completed_at = datetime.now(timezone.utc)
        transaction.response_snapshot_json = {}
        session.flush()
        return transaction

    @staticmethod
    def _read_reservation(
        reservation: InventoryReservation,
        lines: Sequence[InventoryReservationLine],
        *,
        requested_quantity: Decimal | None = None,
        line_errors: Sequence[str] = (),
    ) -> InventoryReservationRead:
        ordered = tuple(sorted(lines, key=lambda item: item.id))
        reserved = sum((line.reserved_quantity for line in ordered), _ZERO)
        requested = (
            requested_quantity
            if requested_quantity is not None
            else sum((line.requested_quantity for line in ordered), _ZERO)
        )
        issued = sum((line.issued_quantity for line in ordered), _ZERO)
        released = sum((line.released_quantity for line in ordered), _ZERO)
        return InventoryReservationRead(
            id=reservation.id,
            tenant_id=reservation.tenant_id,
            owner_type=reservation.owner_type,
            owner_id=reservation.owner_id,
            status=reservation.status,
            expires_at=reservation.expires_at,
            allow_partial=reservation.allow_partial,
            actor_user_id=reservation.actor_user_id,
            actor_roles=list(reservation.actor_roles_json),
            request_id=reservation.request_id,
            version=reservation.version,
            requested_quantity=requested,
            reserved_quantity=reserved,
            issued_quantity=issued,
            released_quantity=released,
            unfilled_quantity=max(requested - reserved, _ZERO),
            line_errors=tuple(line_errors),
            lines=tuple(
                InventoryReservationLineRead.model_validate(line) for line in ordered
            ),
        )

    @staticmethod
    def _request_hash(
        operation_type: OperationType,
        command: Any,
        *,
        reservation_id: int | None = None,
        action: str | None = None,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "operation_type": operation_type,
                "action": action,
                "reservation_id": reservation_id,
                "command": command.model_dump(mode="json"),
            }
        )

    @staticmethod
    def _normalize_idempotency_key(value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise BusinessValidationError(
                "idempotency key must contain 1 to 128 characters",
                code="INVALID_IDEMPOTENCY_KEY",
            )
        return normalized

    @staticmethod
    def _require_contributor(actor: ActorContext) -> None:
        if _ROLE_RANK[actor.role] < _ROLE_RANK[MaintenanceRole.CONTRIBUTOR]:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.CONTRIBUTOR.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _raise_conflict(
        actor: ActorContext,
        message: str,
        *,
        code: str = "RESOURCE_CONFLICT",
        details: Any | None = None,
    ) -> None:
        error = ConflictError(message, code=code, details=details)
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _raise_validation(
        actor: ActorContext,
        message: str,
        *,
        code: str,
    ) -> None:
        error = BusinessValidationError(message, code=code)
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
