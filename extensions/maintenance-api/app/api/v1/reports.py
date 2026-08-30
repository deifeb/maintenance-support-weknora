from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from app.schemas.common import MaintenanceSuccessResponse, PageData
from app.schemas.report_center import (
    ReportCenterItemRead,
    ReportCenterQuery,
    ReportCenterSortBy,
    ReportCenterSortOrder,
)
from app.security.actor import ActorContext
from app.security.permissions import require_viewer
from app.services.report_center_service import report_center_query_service

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]


async def reject_tenant_override(request: Request) -> None:
    if "tenant_id" not in request.query_params:
        return
    raise RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": ("query", "tenant_id"),
                "msg": "tenant_id is not accepted",
                "input": request.query_params.get("tenant_id"),
            }
        ]
    )


@router.get(
    "",
    response_model=(
        MaintenanceSuccessResponse[
            PageData[ReportCenterItemRead]
        ]
    ),
    dependencies=[Depends(reject_tenant_override)],
)
def list_reports(
    session: SessionDep,
    actor: ViewerDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None, max_length=255),
    report_type: AIReportType | None = Query(default=None),
    job_status: AIReportJobStatus | None = Query(default=None),
    version_status: AIReportVersionStatus | None = Query(default=None),
    session_id: int | None = Query(default=None, gt=0),
    scenario_version_id: int | None = Query(default=None, gt=0),
    calculation_run_id: int | None = Query(default=None, gt=0),
    review_run_id: int | None = Query(default=None, gt=0),
    sort_by: ReportCenterSortBy = Query(default="created_at"),
    sort_order: ReportCenterSortOrder = Query(default="desc"),
):
    page_data = report_center_query_service.list(
        session,
        actor,
        ReportCenterQuery(
            page=page,
            page_size=page_size,
            keyword=keyword,
            report_type=report_type,
            job_status=job_status,
            version_status=version_status,
            session_id=session_id,
            scenario_version_id=scenario_version_id,
            calculation_run_id=calculation_run_id,
            review_run_id=review_run_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
    )
    return success_response(
        page_data,
        "Report center queried",
        actor=actor,
    )
