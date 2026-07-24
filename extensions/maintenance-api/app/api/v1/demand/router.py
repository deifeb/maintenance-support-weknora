from fastapi import APIRouter

from app.api.v1.demand import calculations, comparisons, repair_profiles, scenarios

router = APIRouter(prefix="/demand")
router.include_router(repair_profiles.router)
router.include_router(scenarios.router)
router.include_router(calculations.router)
router.include_router(comparisons.router)
