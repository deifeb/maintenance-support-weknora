from fastapi import APIRouter

from app.api.v1.master_data import (
    configurations,
    equipment_models,
    exports,
    imports,
    inventories,
    parts,
    reliability,
    spare_parts,
    supplier_offers,
    suppliers,
    warehouses,
)

router = APIRouter(prefix="/master-data")
router.include_router(equipment_models.router)
router.include_router(configurations.router)
router.include_router(parts.router)
router.include_router(spare_parts.router)
router.include_router(reliability.router)
router.include_router(warehouses.router)
router.include_router(inventories.router)
router.include_router(suppliers.router)
router.include_router(supplier_offers.router)
router.include_router(exports.router)
router.include_router(imports.router)
