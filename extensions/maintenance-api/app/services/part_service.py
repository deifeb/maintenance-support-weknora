from app.repositories import PartRepository
from app.schemas.catalog import PartRead
from app.services.base import CrudService


class PartService(CrudService):
    def __init__(self) -> None:
        super().__init__(PartRepository(), resource_name="part", read_schema=PartRead)


part_service = PartService()
