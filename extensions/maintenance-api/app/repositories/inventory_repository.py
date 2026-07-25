from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WarehouseInventory
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class InventoryRepository(BaseRepository[WarehouseInventory]):
    def __init__(self) -> None:
        super().__init__(WarehouseInventory)

    def get_by_business_key(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
        spare_part_id: int,
    ) -> WarehouseInventory | None:
        return session.scalar(
            select(WarehouseInventory)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                WarehouseInventory.tenant_id == tenant_id,
                WarehouseInventory.warehouse_id == warehouse_id,
                WarehouseInventory.spare_part_id == spare_part_id,
            )
        )
