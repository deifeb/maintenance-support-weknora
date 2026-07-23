from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Warehouse, WarehouseInventory
from app.repositories.base import BaseRepository


class WarehouseRepository(BaseRepository[Warehouse]):
    def __init__(self) -> None:
        super().__init__(Warehouse)

    def count_references(self, session: Session, identifier: int) -> int:
        return int(
            session.scalar(
                select(func.count()).select_from(WarehouseInventory).where(
                    WarehouseInventory.warehouse_id == identifier
                )
            )
            or 0
        )
