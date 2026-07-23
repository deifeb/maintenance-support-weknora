from app.services.configuration_service import configuration_service
from app.services.equipment_service import equipment_service
from app.services.inventory_service import inventory_service
from app.services.part_service import part_service
from app.services.reliability_service import reliability_service
from app.services.spare_part_service import spare_part_service
from app.services.supplier_offer_service import supplier_offer_service
from app.services.supplier_service import supplier_service
from app.services.warehouse_service import warehouse_service

__all__ = [
    "equipment_service",
    "configuration_service",
    "part_service",
    "spare_part_service",
    "reliability_service",
    "warehouse_service",
    "inventory_service",
    "supplier_service",
    "supplier_offer_service",
]
