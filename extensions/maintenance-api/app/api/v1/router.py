from fastapi import APIRouter

from app.api.v1.ai.router import router as ai_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.demand.router import router as demand_router
from app.api.v1.endpoints import system
from app.api.v1.inventory.router import router as inventory_router
from app.api.v1.master_data.router import router as master_data_router
from app.api.v1.reviews.router import router as reviews_router

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(master_data_router)
api_router.include_router(dashboard_router)
api_router.include_router(demand_router)
api_router.include_router(inventory_router)
api_router.include_router(reviews_router)

api_router.include_router(ai_router)
