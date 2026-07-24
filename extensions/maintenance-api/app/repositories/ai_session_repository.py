import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIEvent, AIMessage, AISession, AISessionSnapshot
from app.models.enums import AIExecutionMode, AIMessageRole, AIMessageType, AISessionStatus


class AISessionRepository:
    def create_session(
        self, session: Session, *, title: str, sensitivity_level: str, created_by: str | None = None
    ) -> AISession:
        row = AISession(
            session_code=f"AI-{uuid.uuid4().hex[:12].upper()}",
            title=title,
            status=AISessionStatus.CREATED,
            sensitivity_level=sensitivity_level,
            execution_mode=AIExecutionMode.LLM,
            last_event_sequence=0,
            created_by=created_by,
        )
        session.add(row)
        session.flush()
        return row

    def get(self, session: Session, session_id: int) -> AISession | None:
        return session.get(AISession, session_id)

    def add_message(
        self,
        session: Session,
        session_id: int,
        *,
        role: str,
        message_type: str,
        content: str,
        structured_content: dict[str, Any] | None = None,
    ) -> AIMessage:
        sequence = (
            session.scalar(
                select(func.coalesce(func.max(AIMessage.sequence), 0)).where(
                    AIMessage.session_id == session_id
                )
            )
            or 0
        )
        row = AIMessage(
            session_id=session_id,
            role=AIMessageRole(role),
            message_type=AIMessageType(message_type),
            content=content,
            structured_content_json=structured_content,
            sequence=int(sequence) + 1,
        )
        session.add(row)
        session.flush()
        return row

    def append_event(
        self,
        session: Session,
        session_id: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        visibility: str = "USER",
    ) -> AIEvent:
        row = session.get(AISession, session_id)
        if row is None:
            raise LookupError(f"AI session {session_id} not found")
        row.last_event_sequence += 1
        event = AIEvent(
            session_id=session_id,
            sequence=row.last_event_sequence,
            event_type=event_type,
            event_version="1.0",
            payload_json=payload,
            visibility=visibility,
        )
        session.add(event)
        session.flush()
        return event

    def list_events(
        self, session: Session, session_id: int, *, after_sequence: int = 0
    ) -> list[AIEvent]:
        return list(
            session.scalars(
                select(AIEvent)
                .where(AIEvent.session_id == session_id, AIEvent.sequence > after_sequence)
                .order_by(AIEvent.sequence)
            ).all()
        )

    def create_snapshot(
        self,
        session: Session,
        session_id: int,
        *,
        current_state: str,
        scenario_draft: dict[str, Any] | None = None,
        field_sources: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
        pending_confirmations: list[dict[str, Any]] | None = None,
        completed_step_ids: list[str] | None = None,
        evidence_package_ids: list[int] | None = None,
    ) -> AISessionSnapshot:
        version = (
            session.scalar(
                select(func.coalesce(func.max(AISessionSnapshot.snapshot_version), 0)).where(
                    AISessionSnapshot.session_id == session_id
                )
            )
            or 0
        )
        row = AISessionSnapshot(
            session_id=session_id,
            snapshot_version=int(version) + 1,
            current_state=current_state,
            scenario_draft_json=scenario_draft,
            field_sources_json=field_sources,
            execution_context_json=execution_context,
            pending_confirmations_json=pending_confirmations,
            completed_step_ids_json=completed_step_ids,
            evidence_package_ids_json=evidence_package_ids,
        )
        session.add(row)
        session.flush()
        return row


ai_session_repository = AISessionRepository()
