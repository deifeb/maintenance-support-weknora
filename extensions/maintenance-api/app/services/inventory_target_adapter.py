from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from pydantic import ValidationError
from sqlalchemy import false, select, update
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
    InventoryTargetReceipt,
    InventoryTargetReceiptStatus,
    Warehouse,
)
from app.models.mixins import utc_now
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.inventory_target_receipt_repository import (
    InventoryTargetReceiptRepository,
)
from app.schemas.inventory import InventoryQuantities
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.schemas.inventory_target import InventoryTargetReceiptResult
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_query_service import (
    InventoryQueryService,
    inventory_query_service,
)
from app.services.inventory_transaction_service import (
    InventoryTransactionService,
    inventory_transaction_service,
)
from app.services.snapshot_service import snapshot_service

_RECEIPT_CONSTRAINT = "uq_inventory_target_receipt_tenant_key"
_SQLITE_RECEIPT_UNIQUE_ERROR = (
    "UNIQUE constraint failed: inventory_target_receipts.tenant_id, "
    "inventory_target_receipts.idempotency_key"
)
_PHYSICAL_FIELDS = (
    "on_hand_quantity",
    "reserved_quantity",
    "damaged_quantity",
    "quarantined_quantity",
    "in_transit_quantity",
)
_DELTA_FIELDS = (
    "on_hand",
    "reserved",
    "damaged",
    "quarantined",
    "in_transit",
)


@dataclass(frozen=True, slots=True)
class InventoryTargetResult:
    created_identity: bool
    operation_type: str | None
    transaction_id: int | None
    replayed: bool


class InventoryTargetAdapter:
    def __init__(
        self,
        *,
        repository: InventoryRepository | None = None,
        receipt_repository: InventoryTargetReceiptRepository | None = None,
        query_service: InventoryQueryService | None = None,
        transaction_service: InventoryTransactionService | None = None,
    ) -> None:
        self.repository = repository or InventoryRepository()
        self.receipt_repository = (
            receipt_repository or InventoryTargetReceiptRepository()
        )
        self.query_service = query_service or inventory_query_service
        self.transaction_service = (
            transaction_service or inventory_transaction_service
        )

    def apply_target(
        self,
        session: Session,
        actor: ActorContext,
        *,
        warehouse_id: int,
        spare_part_id: int,
        quantities: InventoryQuantities,
        notes: str | None,
        idempotency_key: str,
        source_payload: Mapping[str, object],
        reason: str,
    ) -> InventoryTargetResult:
        self._require_admin(actor)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        source_hash = snapshot_service.canonical_hash(source_payload)
        receipt, replay = self._reserve_source(
            session,
            actor,
            idempotency_key=clean_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

        warehouse = session.scalar(
            select(Warehouse)
            .where(
                Warehouse.tenant_id == actor.tenant_id,
                Warehouse.id == warehouse_id,
            )
            .with_for_update()
        )
        if warehouse is None:
            raise NotFoundError("warehouse", warehouse_id)

        policy = self.repository.get_policy_by_business_key(
            session,
            actor.tenant_id,
            warehouse_id,
            spare_part_id,
        )
        balance = self.repository.get_default_balance_by_business_key(
            session,
            actor.tenant_id,
            warehouse_id,
            spare_part_id,
        )
        if (policy is None) != (balance is None):
            raise ConflictError(
                "inventory default identity is incomplete",
                details={
                    "conflict_object": "inventory_default_identity",
                    "retryable": False,
                },
            )

        current = self._current_values(
            session,
            actor,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
        )
        target = {
            field: getattr(quantities, field)
            for field in _PHYSICAL_FIELDS
        }
        default_values = {
            field: (
                getattr(balance, field)
                if balance is not None
                else Decimal("0")
            )
            for field in _PHYSICAL_FIELDS
        }
        self._require_reachable(
            current=current,
            default_values=default_values,
            target=target,
        )

        policy_data = {
            "safety_stock": quantities.safety_stock,
            "reorder_point": quantities.reorder_point,
            "maximum_stock": quantities.maximum_stock,
            "notes": notes,
        }
        created_identity = policy is None
        if created_identity:
            balance, policy = self.repository.create_default_identity(
                session,
                actor.tenant_id,
                warehouse_id=warehouse_id,
                spare_part_id=spare_part_id,
                policy_data=policy_data,
            )
        else:
            assert policy is not None and balance is not None
            changes = {
                key: value
                for key, value in policy_data.items()
                if getattr(policy, key) != value
            }
            if changes:
                self.repository.update_policy(
                    session,
                    actor.tenant_id,
                    policy,
                    changes,
                )

        delta = InventoryQuantityDelta(
            **{
                delta_field: target[field] - current[field]
                for field, delta_field in zip(
                    _PHYSICAL_FIELDS,
                    _DELTA_FIELDS,
                    strict=True,
                )
            }
        )
        if all(value == 0 for value in delta.model_dump().values()):
            result = InventoryTargetReceiptResult(
                created_identity=created_identity,
                operation_type=None,
                transaction_id=None,
            )
        else:
            operation_type = "OPENING" if created_identity else "ADJUST"
            command = getattr(
                self.transaction_service,
                operation_type.lower(),
            )
            transaction = command(
                session,
                actor,
                balance_id=balance.id,
                expected_version=balance.version,
                deltas=delta,
                reason=reason,
                idempotency_key=clean_key,
            )
            result = InventoryTargetReceiptResult(
                created_identity=created_identity,
                operation_type=operation_type,
                transaction_id=transaction.id,
            )
        self.receipt_repository.complete(
            session,
            receipt,
            result=result.model_dump(mode="json"),
            completed_at=utc_now(),
        )
        return InventoryTargetResult(
            **result.model_dump(),
            replayed=False,
        )

    def _reserve_source(
        self,
        session: Session,
        actor: ActorContext,
        *,
        idempotency_key: str,
        source_hash: str,
    ) -> tuple[InventoryTargetReceipt, InventoryTargetResult | None]:
        existing = self.receipt_repository.get(
            session,
            actor.tenant_id,
            idempotency_key,
        )
        if existing is not None:
            return existing, self._replay_source(actor, existing, source_hash)

        self._ensure_savepoint_parent_transaction(session)
        try:
            with session.begin_nested():
                receipt = self.receipt_repository.create_pending(
                    session,
                    actor,
                    idempotency_key=idempotency_key,
                    source_hash=source_hash,
                )
            return receipt, None
        except IntegrityError as exc:
            if not self._is_receipt_constraint_violation(exc):
                raise
            winner = self.receipt_repository.get(
                session,
                actor.tenant_id,
                idempotency_key,
            )
            if winner is None:
                conflict = ConflictError(
                    "inventory target reservation conflict",
                    code="INVENTORY_TARGET_RESERVATION_CONFLICT",
                    details={
                        "conflict_object": "inventory_target_receipt",
                        "retryable": True,
                    },
                )
                conflict.request_id = actor.request_id
                raise conflict from exc
            return winner, self._replay_source(actor, winner, source_hash)

    def _current_values(
        self,
        session: Session,
        actor: ActorContext,
        *,
        warehouse_id: int,
        spare_part_id: int,
    ) -> dict[str, Decimal]:
        summaries = self.query_service.summary_for_part(
            session,
            actor,
            spare_part_id,
        )
        summary = next(
            (item for item in summaries if item.warehouse_id == warehouse_id),
            None,
        )
        return {
            field: getattr(summary, field) if summary is not None else Decimal("0")
            for field in _PHYSICAL_FIELDS
        }

    @staticmethod
    def _require_reachable(
        *,
        current: dict[str, Decimal],
        default_values: dict[str, Decimal],
        target: dict[str, Decimal],
    ) -> None:
        result_default = {
            field: target[field] - (current[field] - default_values[field])
            for field in _PHYSICAL_FIELDS
        }
        unreachable = [
            delta_field
            for field, delta_field in zip(
                _PHYSICAL_FIELDS,
                _DELTA_FIELDS,
                strict=True,
            )
            if result_default[field] < 0
        ]
        allocated = sum(
            result_default[field]
            for field in (
                "reserved_quantity",
                "damaged_quantity",
                "quarantined_quantity",
            )
        )
        if not unreachable and allocated > result_default["on_hand_quantity"]:
            unreachable.append("allocation")
        if unreachable:
            raise BusinessValidationError(
                "inventory target cannot be represented without changing granular facts",
                code="INVENTORY_TARGET_UNREACHABLE",
                details={
                    "unreachable_components": unreachable,
                    "retryable": False,
                },
            )

    @staticmethod
    def _replay_source(
        actor: ActorContext,
        receipt: InventoryTargetReceipt,
        source_hash: str,
    ) -> InventoryTargetResult:
        if receipt.source_hash != source_hash:
            InventoryTargetAdapter._raise_reused(actor, receipt.idempotency_key)
        if receipt.status is not InventoryTargetReceiptStatus.COMPLETED:
            InventoryTargetAdapter._raise_unavailable(actor)
        try:
            result = InventoryTargetReceiptResult.model_validate(receipt.result_json)
        except ValidationError as exc:
            unavailable = InventoryTargetAdapter._unavailable(actor)
            raise unavailable from exc
        return InventoryTargetResult(
            **result.model_dump(),
            replayed=True,
        )

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        clean_key = idempotency_key.strip()
        if not clean_key or len(clean_key) > 128:
            raise BusinessValidationError(
                "idempotency key is invalid",
                code="INVALID_IDEMPOTENCY_KEY",
            )
        return clean_key

    @staticmethod
    def _is_receipt_constraint_violation(exc: IntegrityError) -> bool:
        diagnostic = getattr(exc.orig, "diag", None)
        if getattr(diagnostic, "constraint_name", None) == _RECEIPT_CONSTRAINT:
            return True
        return str(exc.orig) == _SQLITE_RECEIPT_UNIQUE_ERROR

    @staticmethod
    def _ensure_savepoint_parent_transaction(session: Session) -> None:
        if session.get_bind().dialect.name == "sqlite":
            session.execute(
                update(InventoryBalance)
                .where(false())
                .values(version=InventoryBalance.version)
            )

    @staticmethod
    def _require_admin(actor: ActorContext) -> None:
        if actor.role is not MaintenanceRole.ADMIN:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _raise_reused(actor: ActorContext, key: str) -> None:
        conflict = ConflictError(
            "idempotency key was reused",
            code="IDEMPOTENCY_KEY_REUSED",
            details={
                "conflict_object": "inventory_target_receipt",
                "idempotency_key": key,
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

    @staticmethod
    def _unavailable(actor: ActorContext) -> ConflictError:
        conflict = ConflictError(
            "idempotent response is unavailable",
            code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            details={
                "conflict_object": "inventory_target_receipt",
                "retryable": True,
            },
        )
        conflict.request_id = actor.request_id
        return conflict

    @staticmethod
    def _raise_unavailable(actor: ActorContext) -> None:
        raise InventoryTargetAdapter._unavailable(actor)


inventory_target_adapter = InventoryTargetAdapter()
