from sqlalchemy.orm import Session

from app.models import Warehouse
from app.repositories.base import BaseRepository
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository


class WarehouseRepository(BaseRepository[Warehouse]):
    def __init__(self) -> None:
        super().__init__(Warehouse)
        self.inventory_ledger_repository = InventoryLedgerRepository()

    def count_references(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> int:
        return self.inventory_ledger_repository.count_warehouse_references(
            session,
            tenant_id,
            identifier,
        )
