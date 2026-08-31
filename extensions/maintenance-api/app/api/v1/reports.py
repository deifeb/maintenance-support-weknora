from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.report_center import (
    ReportCenterItemRead,
    ReportCenterQuery,
    ReportCenterSortBy,
    ReportCenterSortOrder,
    ReportJobCreateRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.report_center_service import (
    report_center_query_service,
)

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]


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


@router.post("/jobs")
def create_report_job(
    payload: ReportJobCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        report_center_query_service.create_job(
            session,
            actor,
            payload,
        ),
        actor=actor,
    )


@router.get("/jobs/{job_id}")
def get_report_job_status(
    job_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    return success_response(
        report_center_query_service.job_status(
            session,
            actor,
            job_id,
        ),
        actor=actor,
    )


@router.get("/{report_id}")
def get_report_detail(
    report_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    return success_response(
        report_center_query_service.detail(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.get("/{report_id}/versions")
def list_report_versions(
    report_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    return success_response(
        report_center_query_service.versions(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.post("/{report_id}/regenerate")
def regenerate_report(
    report_id: int,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        report_center_query_service.regenerate(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.get("/{report_id}/exports/{format}")
def export_report(
    report_id: int,
    format: str,
    session: SessionDep,
    actor: ViewerDep,
):
    content, content_type, file_name = (
        report_center_query_service.export(
            session,
            actor,
            report_id,
            format,
        )
    )
    return Response(
        content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                "attachment; "
                f'filename="{file_name}"'
            ),
            "X-Request-ID": actor.request_id,
        },
    )
