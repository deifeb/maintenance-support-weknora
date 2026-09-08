from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.ai_confirmation import (
    AIConfirmationApproveRequest,
    AIConfirmationRejectRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import require_admin
from app.services.ai_confirmation_service import (
    ai_confirmation_service,
)
from app.workers.ai_executor import (
    submit_ai_session,
)

router = APIRouter()


@router.post(
    "/confirmations/{confirmation_id}/approve"
)
def approve(
    confirmation_id: int,
    payload: AIConfirmationApproveRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_admin),
    ],
    session: Session = Depends(get_db_session),
):
    row = ai_confirmation_service.approve(
        session,
        actor,
        confirmation_id,
        token=payload.confirmation_token,
        expected_input_digest=(
            payload.expected_input_digest
        ),
        comment=payload.comment,
    )
    future = submit_ai_session(
        row.session_id,
        actor,
    )
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
            "workflow_submitted": (
                future is not None
            ),
        },
        actor=actor,
    )


@router.post(
    "/confirmations/{confirmation_id}/reject"
)
def reject(
    confirmation_id: int,
    payload: AIConfirmationRejectRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_admin),
    ],
    session: Session = Depends(get_db_session),
):
    row = ai_confirmation_service.reject(
        session,
        actor,
        confirmation_id,
        comment=payload.comment,
    )
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
        },
        actor=actor,
    )
