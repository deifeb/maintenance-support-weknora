from fastapi import APIRouter

from app.core.config import get_settings
from app.core.exceptions import DatabaseUnavailableError
from app.core.responses import success_response
from app.db.health import check_database_health
from app.schemas.common import SuccessResponse
from app.schemas.system import HealthData

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=SuccessResponse[HealthData],
)
def health_check() -> SuccessResponse[HealthData]:
    settings = get_settings()
    database_health = check_database_health()

    if database_health.status != "healthy":
        raise DatabaseUnavailableError()

    return success_response(
        data=HealthData(
            status="ok",
            service="maintenance-api",
            version=settings.app_version,
            database=database_health.status,
        ),
        message="Service is healthy",
    )
