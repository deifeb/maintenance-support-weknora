from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories import DemandScenarioVersionRepository
from app.repositories.ai_session_repository import (
    AISessionRepository,
    ai_session_repository,
)
from app.security.actor import ActorContext


class AISessionService:
    def __init__(
        self,
        *,
        repository: AISessionRepository | None = None,
        scenario_repository: (
            DemandScenarioVersionRepository | None
        ) = None,
    ) -> None:
        self.repository = repository or ai_session_repository
        self.scenario_repository = (
            scenario_repository
            or DemandScenarioVersionRepository()
        )

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        title: str,
        sensitivity_level: str,
        active_scenario_version_id: int | None = None,
    ):
        if active_scenario_version_id is not None:
            scenario = self.scenario_repository.get_by_id(
                session,
                actor.tenant_id,
                active_scenario_version_id,
            )
            if scenario is None:
                raise NotFoundError(
                    "demand_scenario_version",
                    active_scenario_version_id,
                )

        row = self.repository.create_session(
            session,
            actor.tenant_id,
            title=title,
            sensitivity_level=sensitivity_level,
            created_by=actor.user_id,
        )
        row.active_scenario_version_id = (
            active_scenario_version_id
        )
        session.commit()
        session.refresh(row)
        return row

    def get(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
    ):
        row = self.repository.get(
            session,
            actor.tenant_id,
            session_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_session",
                session_id,
            )
        return row

    def add_message(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        role: str,
        message_type: str,
        content: str,
        structured_content: dict | None = None,
    ):
        self.get(
            session,
            actor,
            session_id,
        )
        try:
            row = self.repository.add_message(
                session,
                actor.tenant_id,
                session_id,
                role=role,
                message_type=message_type,
                content=content,
                structured_content=structured_content,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc
        session.commit()
        session.refresh(row)
        return row

    def append_event(
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
            event = self.repository.append_event(
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
        session.commit()
        session.refresh(event)
        return event

    def create_snapshot(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        scenario_draft: dict | None = None,
        field_sources: dict | None = None,
        execution_context: dict | None = None,
        pending_confirmations: (
            list[dict] | None
        ) = None,
        completed_step_ids: list[str] | None = None,
        evidence_package_ids: list[int] | None = None,
    ):
        current = self.get(
            session,
            actor,
            session_id,
        )
        try:
            row = self.repository.create_snapshot(
                session,
                actor.tenant_id,
                session_id,
                current_state=current.status.value,
                scenario_draft=scenario_draft,
                field_sources=field_sources,
                execution_context=execution_context,
                pending_confirmations=(
                    pending_confirmations
                ),
                completed_step_ids=completed_step_ids,
                evidence_package_ids=evidence_package_ids,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc
        session.commit()
        session.refresh(row)
        return row


ai_session_service = AISessionService()
