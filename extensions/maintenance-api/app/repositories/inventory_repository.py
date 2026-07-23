from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WarehouseInventory
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[WarehouseInventory]):
    def __init__(self) -> None:
        super().__init__(WarehouseInventory)

    def get_by_business_key(
        self, session: Session, warehouse_id: int, spare_part_id: int
    ) -> WarehouseInventory | None:
        return session.scalar(
            select(WarehouseInventory).where(
                WarehouseInventory.warehouse_id == warehouse_id,
                WarehouseInventory.spare_part_id == spare_part_id,
            )
        )
