from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryTransaction,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.security.actor import ActorContext


class InventoryTransactionRepository:
    def get_transaction(
        self,
        session: Session,
        tenant_id: str,
        transaction_id: int,
    ) -> InventoryTransaction | None:
        return session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.id == transaction_id,
            )
        )

    def lock_transaction(
        self,
        session: Session,
        tenant_id: str,
        transaction_id: int,
    ) -> InventoryTransaction | None:
        return session.scalar(
            select(InventoryTransaction)
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.id == transaction_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def get_idempotent(
        self,
        session: Session,
        tenant_id: str,
        operation_type: str,
        idempotency_key: str,
    ) -> InventoryTransaction | None:
        return session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.operation_type == operation_type,
                InventoryTransaction.idempotency_key == idempotency_key,
            )
        )

    def create_transaction(
        self,
        session: Session,
        *,
        actor: ActorContext,
        operation_type: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        status: str = "COMPLETED",
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> InventoryTransaction:
        transaction = InventoryTransaction(
            tenant_id=actor.tenant_id,
            operation_type=operation_type,
            status=status,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
            version=1,
        )
        session.add(transaction)
        session.flush()
        return transaction

    def append_entry(
        self,
        session: Session,
        *,
        transaction: InventoryTransaction,
        balance: InventoryBalance,
        deltas: InventoryQuantityDelta,
        state_before: dict[str, Any],
        state_after: dict[str, Any],
        before_balance_version: int,
        resulting_balance_version: int,
        serial_item_id: int | None = None,
    ) -> InventoryLedgerEntry:
        entry = InventoryLedgerEntry(
            tenant_id=transaction.tenant_id,
            transaction_id=transaction.id,
            balance_id=balance.id,
            spare_part_id=balance.spare_part_id,
            warehouse_id=balance.warehouse_id,
            location_id=balance.location_id,
            lot_id=balance.lot_id,
            serial_item_id=serial_item_id,
            on_hand_delta=deltas.on_hand,
            reserved_delta=deltas.reserved,
            damaged_delta=deltas.damaged,
            quarantined_delta=deltas.quarantined,
            in_transit_delta=deltas.in_transit,
            state_before_json=state_before,
            state_after_json=state_after,
            before_balance_version=before_balance_version,
            resulting_balance_version=resulting_balance_version,
        )
        session.add(entry)
        session.flush()
        return entry

    def append_entries(
        self,
        session: Session,
        *,
        transaction: InventoryTransaction,
        entries: Sequence[dict[str, Any]],
    ) -> list[InventoryLedgerEntry]:
        return [
            self.append_entry(
                session,
                transaction=transaction,
                **entry_values,
            )
            for entry_values in entries
        ]

    def list_entries(
        self,
        session: Session,
        tenant_id: str,
        transaction_id: int,
    ) -> list[InventoryLedgerEntry]:
        return list(
            session.scalars(
                select(InventoryLedgerEntry)
                .where(
                    InventoryLedgerEntry.tenant_id == tenant_id,
                    InventoryLedgerEntry.transaction_id == transaction_id,
                )
                .order_by(InventoryLedgerEntry.id)
            ).all()
        )

    def complete(
        self,
        session: Session,
        transaction: InventoryTransaction,
        *,
        completed_at: datetime,
        response_snapshot: dict,
    ) -> None:
        transaction.completed_at = completed_at
        transaction.response_snapshot_json = response_snapshot
        session.flush()


def decimal_state(
    *,
    on_hand: Decimal,
    reserved: Decimal,
    damaged: Decimal,
    quarantined: Decimal,
    in_transit: Decimal,
) -> dict[str, str]:
    return {
        "on_hand": format(on_hand, ".4f"),
        "reserved": format(reserved, ".4f"),
        "damaged": format(damaged, ".4f"),
        "quarantined": format(quarantined, ".4f"),
        "in_transit": format(in_transit, ".4f"),
    }
