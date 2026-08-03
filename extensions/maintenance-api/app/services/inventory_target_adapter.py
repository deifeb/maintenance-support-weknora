from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models import InventoryTransaction, Warehouse
from app.models.mixins import utc_now
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.inventory_transaction_repository import (
    InventoryTransactionRepository,
)
from app.schemas.inventory import InventoryQuantities
from app.schemas.inventory_ledger import InventoryQuantityDelta
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

_SOURCE_EXTENSION = "inventory_target_source"
_OPERATIONS = ("OPENING", "ADJUST", "TARGET")
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
        transaction_repository: InventoryTransactionRepository | None = None,
        query_service: InventoryQueryService | None = None,
        transaction_service: InventoryTransactionService | None = None,
    ) -> None:
        self.repository = repository or InventoryRepository()
        self.transaction_repository = (
            transaction_repository or InventoryTransactionRepository()
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
        if actor.role is not MaintenanceRole.ADMIN:
            from app.core.exceptions import InsufficientMaintenanceRoleError

            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )
        source_hash = snapshot_service.canonical_hash(source_payload)
        replay = self._replay_source(
            session,
            actor,
            idempotency_key=idempotency_key,
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
            from app.core.exceptions import NotFoundError

            raise NotFoundError("warehouse", warehouse_id)
        replay = self._replay_source(
            session,
            actor,
            idempotency_key=idempotency_key,
            source_hash=source_hash,
        )
        if replay is not None:
            return replay

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

        summaries = self.query_service.summary_for_part(
            session,
            actor,
            spare_part_id,
        )
        summary = next(
            (
                item
                for item in summaries
                if item.warehouse_id == warehouse_id
            ),
            None,
        )
        current = {
            field: (
                getattr(summary, field)
                if summary is not None
                else Decimal("0")
            )
            for field in _PHYSICAL_FIELDS
        }
        target = {
            field: getattr(quantities, field)
            for field in _PHYSICAL_FIELDS
        }
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
            transaction = self.transaction_repository.create_transaction(
                session,
                actor=actor,
                operation_type="TARGET",
                idempotency_key=idempotency_key,
                request_hash=source_hash,
                reason=reason,
            )
            completed_at = utc_now()
            self.transaction_repository.complete(
                session,
                transaction,
                completed_at=completed_at,
                response_snapshot={
                    "_extensions": {
                        _SOURCE_EXTENSION: {
                            "source_hash": source_hash,
                            "created_identity": created_identity,
                            "operation_type": "TARGET",
                        }
                    }
                },
            )
            return InventoryTargetResult(
                created_identity=created_identity,
                operation_type="TARGET",
                transaction_id=transaction.id,
                replayed=False,
            )

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
            idempotency_key=idempotency_key,
        )
        self.transaction_service.store_response_extension(
            session,
            actor,
            transaction_id=transaction.id,
            name=_SOURCE_EXTENSION,
            value={
                "source_hash": source_hash,
                "created_identity": created_identity,
                "operation_type": operation_type,
            },
        )
        return InventoryTargetResult(
            created_identity=created_identity,
            operation_type=operation_type,
            transaction_id=transaction.id,
            replayed=False,
        )

    def _replay_source(
        self,
        session: Session,
        actor: ActorContext,
        *,
        idempotency_key: str,
        source_hash: str,
    ) -> InventoryTargetResult | None:
        receipts = [
            receipt
            for operation in _OPERATIONS
            if (
                receipt := self.transaction_repository.get_idempotent(
                    session,
                    actor.tenant_id,
                    operation,
                    idempotency_key,
                )
            )
            is not None
        ]
        if not receipts:
            return None
        if len(receipts) != 1:
            self._raise_reused(actor, idempotency_key)
        receipt = receipts[0]
        metadata = self._source_metadata(receipt)
        if metadata.get("source_hash") != source_hash:
            self._raise_reused(actor, idempotency_key)
        return InventoryTargetResult(
            created_identity=bool(metadata.get("created_identity")),
            operation_type=str(metadata.get("operation_type")),
            transaction_id=receipt.id,
            replayed=True,
        )

    @staticmethod
    def _source_metadata(receipt: InventoryTransaction) -> dict:
        snapshot = receipt.response_snapshot_json
        extensions = snapshot.get("_extensions") if isinstance(snapshot, dict) else None
        metadata = extensions.get(_SOURCE_EXTENSION) if isinstance(extensions, dict) else None
        if not isinstance(metadata, dict):
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "inventory_transaction",
                    "retryable": False,
                },
            )
        return metadata

    @staticmethod
    def _raise_reused(actor: ActorContext, key: str) -> None:
        conflict = ConflictError(
            "idempotency key was reused",
            code="IDEMPOTENCY_KEY_REUSED",
            details={
                "conflict_object": "inventory_transaction",
                "idempotency_key": key,
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict


inventory_target_adapter = InventoryTargetAdapter()
