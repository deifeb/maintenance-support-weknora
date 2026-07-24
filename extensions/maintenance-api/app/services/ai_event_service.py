from sqlalchemy.orm import Session

from app.repositories.ai_session_repository import ai_session_repository


class AIEventService:
    def append(
        self,
        session: Session,
        session_id: int,
        event_type: str,
        payload: dict,
        *,
        visibility: str = "USER",
    ):
        return ai_session_repository.append_event(
            session, session_id, event_type, payload, visibility=visibility
        )

    def list(self, session: Session, session_id: int, *, after_sequence: int = 0):
        return ai_session_repository.list_events(session, session_id, after_sequence=after_sequence)


ai_event_service = AIEventService()
