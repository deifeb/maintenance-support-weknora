from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.security.actor import ActorContext
from app.security.permissions import require_viewer
from app.services.business_card_service import business_card_service

router = APIRouter()


@router.get(
    "/sessions/{session_id}/messages/{trigger_message_id}/business-cards"
)
def get_exact_turn_business_cards(
    session_id: int,
    trigger_message_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    projection = business_card_service.recover_exact_turn(
        session,
        actor,
        session_id,
        trigger_message_id,
    )
    return success_response(
        projection.model_dump(mode="json"),
        actor=actor,
    )
