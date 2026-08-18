from fastapi import APIRouter

from app.api.v1.reviews import demand_lists

router = APIRouter(prefix="/reviews")
router.include_router(demand_lists.router)
