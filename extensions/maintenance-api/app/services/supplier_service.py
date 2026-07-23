from app.repositories import SupplierRepository
from app.schemas.supplier import SupplierRead
from app.services.base import CrudService


class SupplierService(CrudService):
    def __init__(self) -> None:
        super().__init__(SupplierRepository(), resource_name="supplier", read_schema=SupplierRead)


supplier_service = SupplierService()
