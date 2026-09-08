from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.dashboard import DashboardSummary
from app.security.actor import ActorContext
from app.security.permissions import require_viewer
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/summary",
    response_model=MaintenanceSuccessResponse[DashboardSummary],
)
def get_dashboard_summary(
    response: Response,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    response.headers["Cache-Control"] = "no-store"
    return success_response(
        dashboard_service.summary(session, actor),
        "Dashboard summary generated",
        actor=actor,
    )
