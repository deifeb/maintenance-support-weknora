from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
)
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.ai_report import (
    AIReportCreateRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.ai_report_service import (
    ai_report_service,
)

router = APIRouter()


@router.post("/reports")
def create_report(
    payload: AIReportCreateRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    job = ai_report_service.create(
        session,
        actor,
        payload,
    )
    version = (
        ai_report_service.latest_version(
            session,
            actor,
            job.id,
        )
    )
    return success_response(
        {
            "id": job.id,
            "report_code": job.report_code,
            "status": job.status.value,
            "version_id": version.id,
        },
        actor=actor,
    )


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    return success_response(
        ai_report_service.read(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.get(
    "/reports/{report_id}/versions"
)
def list_report_versions(
    report_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    versions = (
        ai_report_service.list_versions(
            session,
            actor,
            report_id,
        )
    )
    return success_response(
        [
            {
                "id": row.id,
                "version_number": (
                    row.version_number
                ),
                "status": row.status.value,
                "template_version": (
                    row.template_version
                ),
                "content_digest": (
                    row.content_digest
                ),
            }
            for row in versions
        ],
        actor=actor,
    )


@router.post(
    "/reports/{report_id}/generate"
)
def generate_report(
    report_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    ai_report_service.generate(
        session,
        actor,
        report_id,
    )
    return success_response(
        ai_report_service.read(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.post(
    "/reports/{report_id}/validate"
)
def validate_report(
    report_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    ai_report_service.validate(
        session,
        actor,
        report_id,
    )
    return success_response(
        ai_report_service.read(
            session,
            actor,
            report_id,
        ),
        actor=actor,
    )


@router.post(
    "/reports/{report_id}/finalize"
)
def finalize_report(
    report_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_admin),
    ],
    session: Session = Depends(get_db_session),
):
    version = ai_report_service.finalize(
        session,
        actor,
        report_id,
    )
    return success_response(
        {
            "id": version.id,
            "version_number": (
                version.version_number
            ),
            "status": version.status.value,
            "finalized_by": (
                version.finalized_by
            ),
        },
        actor=actor,
    )


@router.get(
    "/reports/{report_id}/exports/{format}"
)
def export_report(
    report_id: int,
    format: str,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    content, content_type, file_name = (
        ai_report_service.export(
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
