from collections.abc import Sequence
from math import ceil

from sqlalchemy.orm import Session

from app.repositories.inventory_ledger_repository import InventoryLedgerRepository
from app.schemas.common import PageData
from app.schemas.inventory_ledger import InventoryBalanceRead, InventorySummaryRead
from app.security.actor import ActorContext

SUMMARY_PART_ID_CHUNK_SIZE = 500


class InventoryQueryService:
    def __init__(self, repository: InventoryLedgerRepository | None = None) -> None:
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
        )
        serial_ids = self.repository.serial_item_ids_by_balance(
            session,
            actor.tenant_id,
            balances,
        )
        items = [
            InventoryBalanceRead.model_validate(balance).model_copy(
                update={
                    "serial_item_ids": serial_ids.get(balance.id, []),
                    "serial_item_id": self._single_serial_id(serial_ids.get(balance.id, [])),
                }
            )
            for balance in balances
        ]
        return self._page(items, page, page_size, total)

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
                for index in range(0, len(identifiers), SUMMARY_PART_ID_CHUNK_SIZE)
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
    def _single_serial_id(serial_item_ids: list[int]) -> int | None:
        return serial_item_ids[0] if len(serial_item_ids) == 1 else None

    @staticmethod
    def _page(items, page: int, page_size: int, total: int) -> PageData:
        return PageData(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )


inventory_query_service = InventoryQueryService()
