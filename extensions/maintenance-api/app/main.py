from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.responses import success_response
from app.db.session import SessionLocal
from app.schemas.common import SuccessResponse
from app.workers import (
    ai_task_executor,
    calculation_group_executor,
    demand_task_executor,
    recover_interrupted_ai_tasks,
    recover_interrupted_calculations,
)
from app.workers.import_executor import (
    import_task_executor,
    recover_stale_import_tasks,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    del application
    session = SessionLocal()
    try:
        recover_interrupted_calculations(session)
        recover_interrupted_ai_tasks(session)
        recover_stale_import_tasks(
            session,
            file_store=import_task_executor.file_store,
            executor=import_task_executor,
        )
    finally:
        session.close()
    yield
    import_task_executor.shutdown(wait=False)
    ai_task_executor.shutdown(wait=False)
    demand_task_executor.shutdown(wait=False)
    calculation_group_executor.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/")
    def root() -> SuccessResponse[dict[str, str]]:
        return success_response(
            {"service": "maintenance-api", "docs": "/docs"},
            message="Maintenance Support API is running",
        )

    return application


app = create_app()
