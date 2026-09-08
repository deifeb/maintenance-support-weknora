from collections import defaultdict
from collections.abc import Sequence
from copy import deepcopy
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import (
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryReservationLine,
    InventoryStocktake,
    InventoryStocktakeLine,
    InventoryTransaction,
    InventoryTransfer,
    InventoryTransferLine,
)
from app.repositories.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from app.schemas.common import PageData
from app.schemas.inventory_ledger import (
    InventoryBalanceRead,
    InventoryLedgerEntryRead,
    InventorySummaryRead,
    InventoryTransactionRead,
)
from app.schemas.inventory_reservation import (
    InventoryReservationLineRead,
    InventoryReservationRead,
)
from app.schemas.inventory_stocktake import (
    InventoryStocktakeLineRead,
    InventoryStocktakeRead,
)
from app.schemas.inventory_transfer import TransferLineRead, TransferRead
from app.security.actor import ActorContext

SUMMARY_PART_ID_CHUNK_SIZE = 500
_ZERO = Decimal("0.0000")

_TRANSACTION_SORT_FIELDS = {
    "id": InventoryTransaction.id,
    "operation_type": InventoryTransaction.operation_type,
    "status": InventoryTransaction.status,
    "completed_at": InventoryTransaction.completed_at,
}
_RESERVATION_SORT_FIELDS = {
    "id": InventoryReservation.id,
    "status": InventoryReservation.status,
    "expires_at": InventoryReservation.expires_at,
}
_TRANSFER_SORT_FIELDS = {
    "id": InventoryTransfer.id,
    "status": InventoryTransfer.status,
    "dispatched_at": InventoryTransfer.dispatched_at,
    "completed_at": InventoryTransfer.completed_at,
}
_STOCKTAKE_SORT_FIELDS = {
    "id": InventoryStocktake.id,
    "status": InventoryStocktake.status,
    "snapshot_at": InventoryStocktake.snapshot_at,
    "confirmed_at": InventoryStocktake.confirmed_at,
}

_NULLABLE_TRANSACTION_SORTS = frozenset({"completed_at"})
_NULLABLE_RESERVATION_SORTS = frozenset({"expires_at"})
_NULLABLE_TRANSFER_SORTS = frozenset({"dispatched_at", "completed_at"})
_NULLABLE_STOCKTAKE_SORTS = frozenset({"confirmed_at"})
_SORT_ORDERS = frozenset({"asc", "desc"})


class InventoryQueryService:
    def __init__(
        self,
        repository: InventoryLedgerRepository | None = None,
    ) -> None:
        self.repository = repository or InventoryLedgerRepository()

    def list_balances(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        warehouse_id: int | None = None,
        spare_part_id: int | None = None,
        location_id: int | None = None,
        lot_id: int | None = None,
        serial_item_id: int | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PageData[InventoryBalanceRead]:
        balances, total = self.repository.list_balances(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=location_id,
            lot_id=lot_id,
            serial_item_id=serial_item_id,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        lot_states = self.repository.lot_state_by_balance(
            session,
            actor.tenant_id,
            balances,
        )
        serial_ids = self.repository.serial_item_ids_by_balance(
            session,
            actor.tenant_id,
            balances,
        )
        items = [
            self._balance_read(
                balance,
                serial_item_ids=serial_ids.get(balance.id, []),
                lot_state=lot_states.get(balance.id),
            )
            for balance in balances
        ]
        return self._page(items, page, page_size, total)

    def get_balance(
        self,
        session: Session,
        actor: ActorContext,
        balance_id: int,
    ) -> InventoryBalanceRead:
        balance = self.repository.get_balance(
            session,
            actor.tenant_id,
            balance_id,
        )
        if balance is None:
            self._raise_not_found(
                actor,
                "inventory_balance",
                balance_id,
            )

        lot_states = self.repository.lot_state_by_balance(
            session,
            actor.tenant_id,
            [balance],
        )
        serial_ids = self.repository.serial_item_ids_by_balance(
            session,
            actor.tenant_id,
            [balance],
        )
        ids = serial_ids.get(balance.id, [])
        return self._balance_read(
            balance,
            serial_item_ids=ids,
            lot_state=lot_states.get(balance.id),
        )

    def list_transactions(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        operation_type: str | None = None,
        status: str | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PageData[InventoryTransactionRead]:
        conditions = []
        if operation_type is not None:
            conditions.append(
                InventoryTransaction.operation_type == operation_type
            )
        if status is not None:
            conditions.append(InventoryTransaction.status == status)
        if reference_type is not None:
            conditions.append(
                InventoryTransaction.reference_type == reference_type
            )
        if reference_id is not None:
            conditions.append(
                InventoryTransaction.reference_id == reference_id
            )

        rows, total = self._list_tenant_rows(
            session,
            InventoryTransaction,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            conditions=conditions,
            sort_by=sort_by,
            sort_order=sort_order,
            sort_fields=_TRANSACTION_SORT_FIELDS,
            nullable_sort_fields=_NULLABLE_TRANSACTION_SORTS,
        )
        entries_by_transaction = self._group_child_rows(
            session,
            InventoryLedgerEntry,
            actor.tenant_id,
            parent_column=InventoryLedgerEntry.transaction_id,
            parent_name="transaction_id",
            parent_ids=[row.id for row in rows],
        )
        items = [
            self._transaction_read(
                transaction,
                entries_by_transaction.get(transaction.id, []),
            )
            for transaction in rows
        ]
        return self._page(items, page, page_size, total)

    def get_transaction(
        self,
        session: Session,
        actor: ActorContext,
        transaction_id: int,
    ) -> InventoryTransactionRead:
        transaction = self._get_tenant_row(
            session,
            InventoryTransaction,
            actor.tenant_id,
            transaction_id,
        )
        if transaction is None:
            self._raise_not_found(
                actor,
                "inventory_transaction",
                transaction_id,
            )

        entries = list(
            session.scalars(
                select(InventoryLedgerEntry)
                .where(
                    InventoryLedgerEntry.tenant_id
                    == actor.tenant_id,
                    InventoryLedgerEntry.transaction_id
                    == transaction.id,
                )
                .order_by(InventoryLedgerEntry.id)
            ).all()
        )
        return self._transaction_read(transaction, entries)

    def list_reservations(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PageData[InventoryReservationRead]:
        conditions = []
        if status is not None:
            conditions.append(InventoryReservation.status == status)
        if owner_type is not None:
            conditions.append(InventoryReservation.owner_type == owner_type)
        if owner_id is not None:
            conditions.append(InventoryReservation.owner_id == owner_id)

        rows, total = self._list_tenant_rows(
            session,
            InventoryReservation,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            conditions=conditions,
            sort_by=sort_by,
            sort_order=sort_order,
            sort_fields=_RESERVATION_SORT_FIELDS,
            nullable_sort_fields=_NULLABLE_RESERVATION_SORTS,
        )
        lines_by_reservation = self._group_child_rows(
            session,
            InventoryReservationLine,
            actor.tenant_id,
            parent_column=InventoryReservationLine.reservation_id,
            parent_name="reservation_id",
            parent_ids=[row.id for row in rows],
        )
        items = [
            self._reservation_read(
                reservation,
                lines_by_reservation.get(reservation.id, []),
            )
            for reservation in rows
        ]
        return self._page(items, page, page_size, total)

    def get_reservation(
        self,
        session: Session,
        actor: ActorContext,
        reservation_id: int,
    ) -> InventoryReservationRead:
        reservation = self._get_tenant_row(
            session,
            InventoryReservation,
            actor.tenant_id,
            reservation_id,
        )
        if reservation is None:
            self._raise_not_found(
                actor,
                "inventory_reservation",
                reservation_id,
            )

        lines = list(
            session.scalars(
                select(InventoryReservationLine)
                .where(
                    InventoryReservationLine.tenant_id
                    == actor.tenant_id,
                    InventoryReservationLine.reservation_id
                    == reservation.id,
                )
                .order_by(InventoryReservationLine.id)
            ).all()
        )
        return self._reservation_read(reservation, lines)

    def list_transfers(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        source_warehouse_id: int | None = None,
        source_location_id: int | None = None,
        target_warehouse_id: int | None = None,
        target_location_id: int | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PageData[TransferRead]:
        conditions = []
        if status is not None:
            conditions.append(InventoryTransfer.status == status)
        if source_warehouse_id is not None:
            conditions.append(
                InventoryTransfer.source_warehouse_id == source_warehouse_id
            )
        if source_location_id is not None:
            conditions.append(
                InventoryTransfer.source_location_id == source_location_id
            )
        if target_warehouse_id is not None:
            conditions.append(
                InventoryTransfer.target_warehouse_id == target_warehouse_id
            )
        if target_location_id is not None:
            conditions.append(
                InventoryTransfer.target_location_id == target_location_id
            )
        if reference_type is not None:
            conditions.append(
                InventoryTransfer.reference_type == reference_type
            )
        if reference_id is not None:
            conditions.append(InventoryTransfer.reference_id == reference_id)

        rows, total = self._list_tenant_rows(
            session,
            InventoryTransfer,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            conditions=conditions,
            sort_by=sort_by,
            sort_order=sort_order,
            sort_fields=_TRANSFER_SORT_FIELDS,
            nullable_sort_fields=_NULLABLE_TRANSFER_SORTS,
        )
        lines_by_transfer = self._group_child_rows(
            session,
            InventoryTransferLine,
            actor.tenant_id,
            parent_column=InventoryTransferLine.transfer_id,
            parent_name="transfer_id",
            parent_ids=[row.id for row in rows],
        )
        items = [
            self._transfer_read(
                transfer,
                lines_by_transfer.get(transfer.id, []),
            )
            for transfer in rows
        ]
        return self._page(items, page, page_size, total)

    def get_transfer(
        self,
        session: Session,
        actor: ActorContext,
        transfer_id: int,
    ) -> TransferRead:
        transfer = self._get_tenant_row(
            session,
            InventoryTransfer,
            actor.tenant_id,
            transfer_id,
        )
        if transfer is None:
            self._raise_not_found(
                actor,
                "inventory_transfer",
                transfer_id,
            )

        lines = list(
            session.scalars(
                select(InventoryTransferLine)
                .where(
                    InventoryTransferLine.tenant_id
                    == actor.tenant_id,
                    InventoryTransferLine.transfer_id
                    == transfer.id,
                )
                .order_by(InventoryTransferLine.id)
            ).all()
        )
        return self._transfer_read(transfer, lines)

    def list_stocktakes(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        warehouse_id: int | None = None,
        location_id: int | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PageData[InventoryStocktakeRead]:
        conditions = []
        if status is not None:
            conditions.append(InventoryStocktake.status == status)
        if warehouse_id is not None:
            conditions.append(InventoryStocktake.warehouse_id == warehouse_id)
        if location_id is not None:
            conditions.append(InventoryStocktake.location_id == location_id)

        rows, total = self._list_tenant_rows(
            session,
            InventoryStocktake,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            conditions=conditions,
            sort_by=sort_by,
            sort_order=sort_order,
            sort_fields=_STOCKTAKE_SORT_FIELDS,
            nullable_sort_fields=_NULLABLE_STOCKTAKE_SORTS,
        )
        lines_by_stocktake = self._group_child_rows(
            session,
            InventoryStocktakeLine,
            actor.tenant_id,
            parent_column=InventoryStocktakeLine.stocktake_id,
            parent_name="stocktake_id",
            parent_ids=[row.id for row in rows],
        )
        items = [
            self._stocktake_read(
                stocktake,
                lines_by_stocktake.get(stocktake.id, []),
            )
            for stocktake in rows
        ]
        return self._page(items, page, page_size, total)

    def get_stocktake(
        self,
        session: Session,
        actor: ActorContext,
        stocktake_id: int,
    ) -> InventoryStocktakeRead:
        stocktake = self._get_tenant_row(
            session,
            InventoryStocktake,
            actor.tenant_id,
            stocktake_id,
        )
        if stocktake is None:
            self._raise_not_found(
                actor,
                "inventory_stocktake",
                stocktake_id,
            )

        lines = list(
            session.scalars(
                select(InventoryStocktakeLine)
                .where(
                    InventoryStocktakeLine.tenant_id
                    == actor.tenant_id,
                    InventoryStocktakeLine.stocktake_id
                    == stocktake.id,
                )
                .order_by(InventoryStocktakeLine.id)
            ).all()
        )
        return self._stocktake_read(stocktake, lines)

    def list_summaries(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        warehouse_id: int | None = None,
        spare_part_id: int | None = None,
        location_id: int | None = None,
        lot_id: int | None = None,
        serial_item_id: int | None = None,
        compatibility_identity: bool = False,
    ) -> PageData[InventorySummaryRead]:
        rows, total = self.repository.list_summaries(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=location_id,
            lot_id=lot_id,
            serial_item_id=serial_item_id,
            compatibility_identity=compatibility_identity,
        )
        return self._page(
            [InventorySummaryRead.model_validate(row) for row in rows],
            page,
            page_size,
            total,
        )

    def summaries_for_parts(
        self,
        session: Session,
        actor: ActorContext,
        spare_part_ids: Sequence[int] | None = None,
    ) -> list[InventorySummaryRead]:
        if spare_part_ids is None:
            chunks: list[Sequence[int] | None] = [None]
        else:
            identifiers = sorted(set(spare_part_ids))
            if not identifiers:
                return []
            chunks = [
                identifiers[index : index + SUMMARY_PART_ID_CHUNK_SIZE]
                for index in range(
                    0,
                    len(identifiers),
                    SUMMARY_PART_ID_CHUNK_SIZE,
                )
            ]
        summaries = [
            InventorySummaryRead.model_validate(row)
            for chunk in chunks
            for row in self.repository.summaries_for_parts(
                session,
                actor.tenant_id,
                chunk,
            )
        ]
        return sorted(
            summaries,
            key=lambda summary: (
                summary.warehouse_id,
                summary.spare_part_id,
            ),
        )

    def summary_for_part(
        self,
        session: Session,
        actor: ActorContext,
        spare_part_id: int,
    ) -> list[InventorySummaryRead]:
        return self.summaries_for_parts(
            session,
            actor,
            [spare_part_id],
        )

    def inventory_export_rows(
        self,
        session: Session,
        actor: ActorContext,
        *,
        keyword: str,
        warehouse_id: int | None,
        spare_part_id: int | None,
        sort_by: str,
        sort_order: str,
        limit: int,
    ) -> list[dict]:
        return self.repository.inventory_export_rows(
            session,
            actor.tenant_id,
            keyword=keyword,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
        )

    def count_low_stock_spare_parts(
        self,
        session: Session,
        actor: ActorContext,
    ) -> int:
        return self.repository.count_low_stock_spare_parts(
            session,
            actor.tenant_id,
        )

    @staticmethod
    def _list_tenant_rows(
        session: Session,
        model: Any,
        tenant_id: str,
        *,
        page: int,
        page_size: int,
        conditions: Sequence[Any] = (),
        sort_by: str = "id",
        sort_order: str = "asc",
        sort_fields: dict[str, Any],
        nullable_sort_fields: frozenset[str] = frozenset(),
    ) -> tuple[list[Any], int]:
        sort_expression = sort_fields.get(sort_by)
        if sort_expression is None:
            raise ValueError(f"unsupported sort_by: {sort_by}")
        if sort_order not in _SORT_ORDERS:
            raise ValueError(f"unsupported sort_order: {sort_order}")

        all_conditions = [model.tenant_id == tenant_id, *conditions]
        ordering: list[Any] = []
        if sort_by in nullable_sort_fields:
            ordering.append(
                case((sort_expression.is_(None), 1), else_=0).asc()
            )

        primary = (
            sort_expression.desc()
            if sort_order == "desc"
            else sort_expression.asc()
        )
        ordering.append(primary)
        if sort_by != "id":
            ordering.append(
                model.id.desc() if sort_order == "desc" else model.id.asc()
            )

        statement = (
            select(model)
            .where(*all_conditions)
            .order_by(*ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total = int(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(*all_conditions)
            )
            or 0
        )
        return list(session.scalars(statement).all()), total

    @staticmethod
    def _get_tenant_row(
        session: Session,
        model: Any,
        tenant_id: str,
        identifier: int,
    ) -> Any | None:
        return session.scalar(
            select(model).where(
                model.tenant_id == tenant_id,
                model.id == identifier,
            )
        )

    @staticmethod
    def _group_child_rows(
        session: Session,
        model: Any,
        tenant_id: str,
        *,
        parent_column: Any,
        parent_name: str,
        parent_ids: list[int],
    ) -> dict[int, list[Any]]:
        if not parent_ids:
            return {}

        rows = session.scalars(
            select(model)
            .where(
                model.tenant_id == tenant_id,
                parent_column.in_(parent_ids),
            )
            .order_by(parent_column, model.id)
        ).all()

        grouped: defaultdict[int, list[Any]] = defaultdict(list)
        for row in rows:
            grouped[int(getattr(row, parent_name))].append(row)
        return dict(grouped)

    @staticmethod
    def _transaction_read(
        transaction: InventoryTransaction,
        entries: Sequence[InventoryLedgerEntry],
    ) -> InventoryTransactionRead:
        return InventoryTransactionRead(
            id=transaction.id,
            tenant_id=transaction.tenant_id,
            operation_type=transaction.operation_type,
            status=transaction.status,
            idempotency_key=transaction.idempotency_key,
            request_hash=transaction.request_hash,
            reason=transaction.reason,
            actor_user_id=transaction.actor_user_id,
            actor_roles=list(transaction.actor_roles_json),
            request_id=transaction.request_id,
            version=transaction.version,
            completed_at=transaction.completed_at,
            entries=[
                InventoryLedgerEntryRead.model_validate(entry)
                for entry in sorted(entries, key=lambda item: item.id)
            ],
        )

    @staticmethod
    def _reservation_read(
        reservation: InventoryReservation,
        lines: Sequence[InventoryReservationLine],
    ) -> InventoryReservationRead:
        ordered = tuple(sorted(lines, key=lambda item: item.id))
        requested = sum(
            (line.requested_quantity for line in ordered),
            _ZERO,
        )
        reserved = sum(
            (line.reserved_quantity for line in ordered),
            _ZERO,
        )
        issued = sum(
            (line.issued_quantity for line in ordered),
            _ZERO,
        )
        released = sum(
            (line.released_quantity for line in ordered),
            _ZERO,
        )
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
            lines=tuple(
                InventoryReservationLineRead.model_validate(line)
                for line in ordered
            ),
        )

    @staticmethod
    def _transfer_read(
        transfer: InventoryTransfer,
        lines: Sequence[InventoryTransferLine],
    ) -> TransferRead:
        return TransferRead(
            id=transfer.id,
            tenant_id=transfer.tenant_id,
            status=transfer.status,
            source_warehouse_id=transfer.source_warehouse_id,
            source_location_id=transfer.source_location_id,
            target_warehouse_id=transfer.target_warehouse_id,
            target_location_id=transfer.target_location_id,
            reference_type=transfer.reference_type,
            reference_id=transfer.reference_id,
            reason=transfer.reason,
            actor_user_id=transfer.actor_user_id,
            actor_roles=list(transfer.actor_roles_json),
            request_id=transfer.request_id,
            version=transfer.version,
            dispatched_at=transfer.dispatched_at,
            completed_at=transfer.completed_at,
            cancelled_at=transfer.cancelled_at,
            lines=tuple(
                TransferLineRead(
                    id=line.id,
                    transfer_id=line.transfer_id,
                    spare_part_id=line.spare_part_id,
                    source_balance_id=line.source_balance_id,
                    target_balance_id=line.target_balance_id,
                    lot_id=line.lot_id,
                    serial_item_id=line.serial_item_id,
                    requested_quantity=line.requested_quantity,
                    dispatched_quantity=line.dispatched_quantity,
                    received_quantity=line.received_quantity,
                    expected_source_version=(
                        line.expected_source_version
                    ),
                    expected_target_version=(
                        line.expected_target_version
                    ),
                    version=line.version,
                )
                for line in sorted(lines, key=lambda item: item.id)
            ),
        )

    @staticmethod
    def _stocktake_read(
        stocktake: InventoryStocktake,
        lines: Sequence[InventoryStocktakeLine],
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
                    snapshot_balance_version=(
                        line.snapshot_balance_version
                    ),
                    confirmed_transaction_id=(
                        line.confirmed_transaction_id
                    ),
                    resolution=line.resolution,
                    conflict_details=deepcopy(
                        line.conflict_details_json
                    ),
                    version=line.version,
                )
                for line in sorted(lines, key=lambda item: item.id)
            ),
        )

    @staticmethod
    def _balance_read(
        balance: Any,
        *,
        serial_item_ids: list[int],
        lot_state: tuple[int, bool] | None,
    ) -> InventoryBalanceRead:
        return InventoryBalanceRead.model_validate(balance).model_copy(
            update={
                "serial_item_ids": serial_item_ids,
                "serial_item_id": InventoryQueryService._single_serial_id(
                    serial_item_ids
                ),
                "lot_version": (
                    lot_state[0]
                    if lot_state is not None
                    else None
                ),
                "lot_is_frozen": (
                    lot_state[1]
                    if lot_state is not None
                    else None
                ),
            }
        )

    @staticmethod
    def _raise_not_found(
        actor: ActorContext,
        resource: str,
        identifier: int,
    ) -> None:
        error = NotFoundError(resource, identifier)
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _single_serial_id(
        serial_item_ids: list[int],
    ) -> int | None:
        return (
            serial_item_ids[0]
            if len(serial_item_ids) == 1
            else None
        )

    @staticmethod
    def _page(
        items,
        page: int,
        page_size: int,
        total: int,
    ) -> PageData:
        return PageData(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )


inventory_query_service = InventoryQueryService()
