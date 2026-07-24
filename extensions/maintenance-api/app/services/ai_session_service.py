from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.ai_session_repository import ai_session_repository


class AISessionService:
    def create(
        self,
        session: Session,
        *,
        title: str,
        sensitivity_level: str,
        created_by: str | None = None,
        active_scenario_version_id: int | None = None,
    ):
        row = ai_session_repository.create_session(
            session,
            title=title,
            sensitivity_level=sensitivity_level,
            created_by=created_by,
        )
        row.active_scenario_version_id = active_scenario_version_id
        session.commit()
        session.refresh(row)
        return row

    def get(self, session: Session, session_id: int):
        row = ai_session_repository.get(session, session_id)
        if row is None:
            raise NotFoundError("ai_session", session_id)
        return row

    def add_message(
        self,
        session: Session,
        session_id: int,
        *,
        role: str,
        message_type: str,
        content: str,
        structured_content: dict | None = None,
    ):
        self.get(session, session_id)
        row = ai_session_repository.add_message(
            session,
            session_id,
            role=role,
            message_type=message_type,
            content=content,
            structured_content=structured_content,
        )
        session.commit()
        session.refresh(row)
        return row

    def append_event(
        self,
        session: Session,
        session_id: int,
        event_type: str,
        payload: dict,
    ):
        event = ai_session_repository.append_event(
            session,
            session_id,
            event_type,
            payload,
        )
        session.commit()
        session.refresh(event)
        return event

    def create_snapshot(
        self,
        session: Session,
        session_id: int,
        *,
        scenario_draft: dict | None = None,
        field_sources: dict | None = None,
        execution_context: dict | None = None,
    ):
        current = self.get(session, session_id)
        row = ai_session_repository.create_snapshot(
            session,
            session_id,
            current_state=current.status.value,
            scenario_draft=scenario_draft,
            field_sources=field_sources,
            execution_context=execution_context,
        )
        session.commit()
        session.refresh(row)
        return row


ai_session_service = AISessionService()
