from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ConfigurationItem,
    ReliabilityProfile,
    SparePart,
    SupplierOffer,
    WarehouseInventory,
)
from app.repositories.base import BaseRepository


class SparePartRepository(BaseRepository[SparePart]):
    def __init__(self) -> None:
        super().__init__(SparePart)

    def count_references(self, session: Session, identifier: int) -> int:
        counts = [
            session.scalar(
                select(func.count())
                .select_from(ConfigurationItem)
                .where(ConfigurationItem.spare_part_id == identifier)
            ),
            session.scalar(
                select(func.count())
                .select_from(ReliabilityProfile)
                .where(ReliabilityProfile.spare_part_id == identifier)
            ),
            session.scalar(
                select(func.count())
                .select_from(WarehouseInventory)
                .where(WarehouseInventory.spare_part_id == identifier)
            ),
            session.scalar(
                select(func.count())
                .select_from(SupplierOffer)
                .where(SupplierOffer.spare_part_id == identifier)
            ),
        ]
        return sum(int(value or 0) for value in counts)
