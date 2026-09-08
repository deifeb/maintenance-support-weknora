from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.ai_session_repository import (
    AISessionRepository,
    ai_session_repository,
)
from app.security.actor import ActorContext


class AIEventService:
    def __init__(
        self,
        *,
        repository: AISessionRepository | None = None,
    ) -> None:
        self.repository = repository or ai_session_repository

    def append(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        event_type: str,
        payload: dict,
        *,
        visibility: str = "USER",
    ):
        try:
            return self.repository.append_event(
                session,
                actor.tenant_id,
                session_id,
                event_type,
                payload,
                visibility=visibility,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc

    def list(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        after_sequence: int = 0,
    ):
        try:
            return self.repository.list_events(
                session,
                actor.tenant_id,
                session_id,
                after_sequence=after_sequence,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc


ai_event_service = AIEventService()
