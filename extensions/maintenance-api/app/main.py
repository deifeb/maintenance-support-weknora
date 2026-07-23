from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    register_exception_handlers(application)
    application.include_router(health_router)

    return application


app = create_app()
