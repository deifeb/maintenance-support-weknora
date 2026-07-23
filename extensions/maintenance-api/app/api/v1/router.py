from fastapi import APIRouter

from app.api.v1.endpoints import system
from app.api.v1.master_data.router import router as master_data_router

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(master_data_router)
