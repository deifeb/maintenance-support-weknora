from app.repositories import EquipmentRepository
from app.schemas.equipment import EquipmentModelRead
from app.services.base import CrudService


class EquipmentService(CrudService):
    def __init__(self) -> None:
        super().__init__(
            EquipmentRepository(),
            resource_name="equipment_model",
            read_schema=EquipmentModelRead,
        )


equipment_service = EquipmentService()
