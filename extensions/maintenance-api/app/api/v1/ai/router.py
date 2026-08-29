from fastapi import APIRouter

from app.api.v1.ai import (
    business_cards,
    confirmations,
    models,
    reports,
    reviews,
    sessions,
)

router = APIRouter(prefix="/ai")
router.include_router(sessions.router)
router.include_router(business_cards.router)
router.include_router(confirmations.router)
router.include_router(models.router)
router.include_router(reviews.router)
router.include_router(reports.router)
