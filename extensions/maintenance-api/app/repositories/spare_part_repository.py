from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ConfigurationItem,
    ReliabilityProfile,
    SparePart,
    SupplierOffer,
)
from app.repositories.base import BaseRepository
from app.repositories.inventory_ledger_repository import InventoryLedgerRepository


class SparePartRepository(BaseRepository[SparePart]):
    def __init__(self) -> None:
        super().__init__(SparePart)
        self.inventory_ledger_repository = InventoryLedgerRepository()

    def count_references(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> int:
        counts = [
            session.scalar(
                select(func.count())
                .select_from(ConfigurationItem)
                .where(
                    ConfigurationItem.tenant_id == tenant_id,
                    ConfigurationItem.spare_part_id == identifier,
                )
            ),
            session.scalar(
                select(func.count())
                .select_from(ReliabilityProfile)
                .where(
                    ReliabilityProfile.tenant_id == tenant_id,
                    ReliabilityProfile.spare_part_id == identifier,
                )
            ),
            self.inventory_ledger_repository.count_balance_references(
                session,
                tenant_id,
                spare_part_id=identifier,
            ),
            session.scalar(
                select(func.count())
                .select_from(SupplierOffer)
                .where(
                    SupplierOffer.tenant_id == tenant_id,
                    SupplierOffer.spare_part_id == identifier,
                )
            ),
        ]
        return sum(int(value or 0) for value in counts)
