from fastapi import APIRouter

from app.api.v1.demand import (
    calculation_groups,
    calculations,
    comparisons,
    model_recommendations,
    repair_profiles,
    scenario_drafts,
    scenarios,
)

router = APIRouter(prefix="/demand")
router.include_router(calculation_groups.router)
router.include_router(model_recommendations.router)
router.include_router(repair_profiles.router)
router.include_router(scenario_drafts.router)
router.include_router(scenarios.router)
router.include_router(calculations.router)
router.include_router(comparisons.router)
