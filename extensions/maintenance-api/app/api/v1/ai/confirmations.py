from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.ai_confirmation import AIConfirmationApproveRequest, AIConfirmationRejectRequest
from app.services.ai_confirmation_service import ai_confirmation_service
from app.workers.ai_executor import submit_ai_session

router = APIRouter()


@router.post("/confirmations/{confirmation_id}/approve")
def approve(
    confirmation_id: int,
    payload: AIConfirmationApproveRequest,
    session: Session = Depends(get_db_session),
):
    row = ai_confirmation_service.approve(
        session,
        confirmation_id,
        token=payload.confirmation_token,
        expected_input_digest=payload.expected_input_digest,
        resolved_by="api-user",
        comment=payload.comment,
    )
    future = submit_ai_session(
        row.session_id,
        user_id="api-user",
        permissions={
            "CALCULATION_EXECUTE",
            "CALCULATION_CANCEL",
            "SCENARIO_DRAFT",
            "REPORT_CREATE",
            "REVIEW_EXECUTE",
        },
    )
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
            "workflow_submitted": future is not None,
        }
    )


@router.post("/confirmations/{confirmation_id}/reject")
def reject(
    confirmation_id: int,
    payload: AIConfirmationRejectRequest,
    session: Session = Depends(get_db_session),
):
    row = ai_confirmation_service.reject(
        session,
        confirmation_id,
        resolved_by="api-user",
        comment=payload.comment,
    )
    return success_response({"id": row.id, "status": row.status.value})
