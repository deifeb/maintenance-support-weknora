import platform
from urllib.parse import urlparse

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.responses import success_response
from app.schemas.common import SuccessResponse
from app.schemas.system import SystemInfoData

router = APIRouter(prefix="/system", tags=["system"])


def get_database_type(database_url: str) -> str:
    scheme = urlparse(database_url).scheme
    return scheme.split("+", maxsplit=1)[0] if scheme else "unknown"


@router.get("/info", response_model=SuccessResponse[SystemInfoData])
def system_info() -> SuccessResponse[SystemInfoData]:
    settings = get_settings()
    return success_response(
        SystemInfoData(
            service="maintenance-api",
            version=settings.app_version,
            environment=settings.app_env,
            api_prefix=settings.api_v1_prefix,
            python_version=platform.python_version(),
            database_type=get_database_type(settings.database_url),
        ),
        message="System information retrieved",
    )
