from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InventoryTargetReceipt,
    InventoryTargetReceiptStatus,
)
from app.security.actor import ActorContext


class InventoryTargetReceiptRepository:
    def get(
        self,
        session: Session,
        tenant_id: str,
        idempotency_key: str,
    ) -> InventoryTargetReceipt | None:
        return session.scalar(
            select(InventoryTargetReceipt).where(
                InventoryTargetReceipt.tenant_id == tenant_id,
                InventoryTargetReceipt.idempotency_key == idempotency_key,
            )
        )

    def create_pending(
        self,
        session: Session,
        actor: ActorContext,
        *,
        idempotency_key: str,
        source_hash: str,
    ) -> InventoryTargetReceipt:
        receipt = InventoryTargetReceipt(
            tenant_id=actor.tenant_id,
            idempotency_key=idempotency_key,
            source_hash=source_hash,
            status=InventoryTargetReceiptStatus.PENDING,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
        )
        session.add(receipt)
        session.flush()
        return receipt

    def complete(
        self,
        session: Session,
        receipt: InventoryTargetReceipt,
        *,
        result: dict,
        completed_at: datetime,
    ) -> None:
        receipt.status = InventoryTargetReceiptStatus.COMPLETED
        receipt.result_json = result
        receipt.completed_at = completed_at
        receipt.version += 1
        session.flush()


inventory_target_receipt_repository = InventoryTargetReceiptRepository()
