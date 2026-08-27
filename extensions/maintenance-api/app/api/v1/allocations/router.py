from fastapi import APIRouter

from app.api.v1.allocations import plans, rules

# PLAN05_4D_TASK6_GREEN_D: compose rule and plan routes only.
router = APIRouter()
router.include_router(rules.router)
router.include_router(plans.router)
