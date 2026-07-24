from app.repositories import WarehouseRepository
from app.schemas.inventory import WarehouseRead
from app.services.base import CrudService


class WarehouseService(CrudService):
    def __init__(self) -> None:
        super().__init__(
            WarehouseRepository(), resource_name="warehouse", read_schema=WarehouseRead
        )


warehouse_service = WarehouseService()
