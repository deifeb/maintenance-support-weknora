from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIEvent,
    AIMessage,
    AISession,
    AISessionSnapshot,
)
from app.models.enums import (
    AIExecutionMode,
    AIMessageRole,
    AIMessageType,
    AISessionStatus,
)
from app.repositories.base import tenant_loader_criteria


class AISessionRepository:
    def create_session(
        self,
        session: Session,
        tenant_id: str,
        *,
        title: str,
        sensitivity_level: str,
        created_by: str | None = None,
    ) -> AISession:
        row = AISession(
            tenant_id=tenant_id,
            session_code=(
                f"AI-{uuid.uuid4().hex[:12].upper()}"
            ),
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

    def get(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> AISession | None:
        return session.scalar(
            select(AISession)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AISession.id == session_id,
                AISession.tenant_id == tenant_id,
            )
        )

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> AISession | None:
        return session.scalar(
            select(AISession)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AISession.id == session_id,
                AISession.tenant_id == tenant_id,
            )
            .with_for_update()
        )

    def _require_session(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> AISession:
        row = self.get(
            session,
            tenant_id,
            session_id,
        )
        if row is None:
            raise LookupError(
                f"AI session {session_id} not found"
            )
        return row

    def add_message(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        role: str,
        message_type: str,
        content: str,
        structured_content: dict[str, Any] | None = None,
    ) -> AIMessage:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        sequence = (
            session.scalar(
                select(
                    func.coalesce(
                        func.max(AIMessage.sequence),
                        0,
                    )
                ).where(
                    AIMessage.tenant_id == tenant_id,
                    AIMessage.session_id == session_id,
                )
            )
            or 0
        )
        row = AIMessage(
            tenant_id=tenant_id,
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
        tenant_id: str,
        session_id: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        visibility: str = "USER",
    ) -> AIEvent:
        parent = self._require_session(
            session,
            tenant_id,
            session_id,
        )
        parent.last_event_sequence += 1
        event = AIEvent(
            tenant_id=tenant_id,
            session_id=session_id,
            sequence=parent.last_event_sequence,
            event_type=event_type,
            event_version="1.0",
            payload_json=payload,
            visibility=visibility,
        )
        session.add(event)
        session.flush()
        return event

    def list_events(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        after_sequence: int = 0,
    ) -> list[AIEvent]:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        return list(
            session.scalars(
                select(AIEvent)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIEvent.tenant_id == tenant_id,
                    AIEvent.session_id == session_id,
                    AIEvent.sequence > after_sequence,
                )
                .order_by(AIEvent.sequence)
            ).all()
        )

    def create_snapshot(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        current_state: str,
        scenario_draft: dict[str, Any] | None = None,
        field_sources: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
        pending_confirmations: (
            list[dict[str, Any]] | None
        ) = None,
        completed_step_ids: list[str] | None = None,
        evidence_package_ids: list[int] | None = None,
    ) -> AISessionSnapshot:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        version = (
            session.scalar(
                select(
                    func.coalesce(
                        func.max(
                            AISessionSnapshot.snapshot_version
                        ),
                        0,
                    )
                ).where(
                    AISessionSnapshot.tenant_id
                    == tenant_id,
                    AISessionSnapshot.session_id
                    == session_id,
                )
            )
            or 0
        )
        row = AISessionSnapshot(
            tenant_id=tenant_id,
            session_id=session_id,
            snapshot_version=int(version) + 1,
            current_state=current_state,
            scenario_draft_json=scenario_draft,
            field_sources_json=field_sources,
            execution_context_json=execution_context,
            pending_confirmations_json=(
                pending_confirmations
            ),
            completed_step_ids_json=completed_step_ids,
            evidence_package_ids_json=evidence_package_ids,
        )
        session.add(row)
        session.flush()
        return row

    def latest_snapshot(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> AISessionSnapshot | None:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        return session.scalar(
            select(AISessionSnapshot)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AISessionSnapshot.tenant_id == tenant_id,
                AISessionSnapshot.session_id == session_id,
            )
            .order_by(
                AISessionSnapshot.snapshot_version.desc()
            )
            .limit(1)
        )

    def materialization_snapshot(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        idempotency_key: str,
    ) -> AISessionSnapshot | None:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        snapshots = session.scalars(
            select(AISessionSnapshot)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AISessionSnapshot.tenant_id == tenant_id,
                AISessionSnapshot.session_id == session_id,
            )
            .order_by(
                AISessionSnapshot.snapshot_version.desc()
            )
        )
        for snapshot in snapshots:
            materialization = (
                snapshot.execution_context_json or {}
            ).get("materialization")
            if (
                isinstance(materialization, dict)
                and materialization.get("idempotency_key")
                == idempotency_key
            ):
                return snapshot
        return None

    def list_recent_messages(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        limit: int,
    ) -> list[AIMessage]:
        self._require_session(
            session,
            tenant_id,
            session_id,
        )
        rows = list(
            session.scalars(
                select(AIMessage)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIMessage.tenant_id == tenant_id,
                    AIMessage.session_id == session_id,
                )
                .order_by(AIMessage.sequence.desc())
                .limit(limit)
            ).all()
        )
        rows.reverse()
        return rows


ai_session_repository = AISessionRepository()
