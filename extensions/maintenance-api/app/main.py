from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.responses import success_response
from app.schemas.common import SuccessResponse


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )

    @application.get("/")
    def root() -> SuccessResponse[dict[str, str]]:
        return success_response(
            data={
                "service": "maintenance-api",
                "docs": "/docs",
            },
            message="Maintenance Support API is running",
        )

    return application


app = create_app()
