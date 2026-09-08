from app.repositories import SparePartRepository
from app.schemas.catalog import SparePartRead
from app.services.base import CrudService


class SparePartService(CrudService):
    def __init__(self) -> None:
        super().__init__(
            SparePartRepository(), resource_name="spare_part", read_schema=SparePartRead
        )


spare_part_service = SparePartService()
