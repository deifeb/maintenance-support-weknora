from fastapi import APIRouter

from app.api.v1.inventory import (
    operations,
    queries,
    reservations,
    stocktakes,
    transfers,
)

router = APIRouter(prefix="/inventory")
router.include_router(queries.router)
router.include_router(reservations.router)
router.include_router(operations.router)
router.include_router(transfers.router)
router.include_router(stocktakes.router)
