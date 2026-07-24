from app.repositories.ai_execution_repository import AIExecutionRepository, ai_execution_repository
from app.repositories.ai_report_repository import AIReportRepository, ai_report_repository
from app.repositories.ai_review_repository import AIReviewRepository, ai_review_repository
from app.repositories.ai_session_repository import AISessionRepository, ai_session_repository
from app.repositories.configuration_repository import (
    ConfigurationItemRepository,
    ConfigurationRepository,
)
from app.repositories.demand_calculation_repository import DemandCalculationRepository
from app.repositories.demand_scenario_repository import (
    DemandScenarioTemplateRepository,
    DemandScenarioVersionRepository,
)
from app.repositories.equipment_repository import EquipmentRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.part_repository import PartRepository
from app.repositories.reliability_repository import ReliabilityRepository
from app.repositories.repair_repository import RepairRepository
from app.repositories.spare_part_repository import SparePartRepository
from app.repositories.supplier_offer_repository import SupplierOfferRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.warehouse_repository import WarehouseRepository

__all__ = [
    "AIExecutionRepository",
    "AIReportRepository",
    "AIReviewRepository",
    "AISessionRepository",
    "ConfigurationItemRepository",
    "ConfigurationRepository",
    "DemandCalculationRepository",
    "DemandScenarioTemplateRepository",
    "DemandScenarioVersionRepository",
    "EquipmentRepository",
    "InventoryRepository",
    "PartRepository",
    "ReliabilityRepository",
    "RepairRepository",
    "SparePartRepository",
    "SupplierOfferRepository",
    "SupplierRepository",
    "WarehouseRepository",
    "ai_execution_repository",
    "ai_report_repository",
    "ai_review_repository",
    "ai_session_repository",
]
