from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories import (
    AIEvidenceRepository,
    AIExecutionRepository,
    AISessionRepository,
)
from app.schemas.ai_model import (
    AIContextMessage,
    AIContextRead,
)
from app.security.actor import ActorContext


class AIContextService:
    def __init__(
        self,
        *,
        session_repository: (
            AISessionRepository | None
        ) = None,
        execution_repository: (
            AIExecutionRepository | None
        ) = None,
        evidence_repository: (
            AIEvidenceRepository | None
        ) = None,
    ) -> None:
        self.session_repository = (
            session_repository
            or AISessionRepository()
        )
        self.execution_repository = (
            execution_repository
            or AIExecutionRepository()
        )
        self.evidence_repository = (
            evidence_repository
            or AIEvidenceRepository()
        )

    def build_context(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        recent_message_count: int = 12,
    ) -> AIContextRead:
        ai_session = self.session_repository.get(
            session,
            actor.tenant_id,
            session_id,
        )
        if ai_session is None:
            raise NotFoundError(
                "ai_session",
                session_id,
            )

        recent = (
            self.session_repository
            .list_recent_messages(
                session,
                actor.tenant_id,
                session_id,
                limit=recent_message_count,
            )
        )
        snapshot = (
            self.session_repository.latest_snapshot(
                session,
                actor.tenant_id,
                session_id,
            )
        )
        plan = self.execution_repository.latest_plan(
            session,
            actor.tenant_id,
            session_id,
        )
        completed_tools = (
            self.execution_repository
            .list_completed_tool_calls(
                session,
                actor.tenant_id,
                session_id,
                limit=20,
            )
        )
        pending = (
            self.execution_repository
            .list_pending_confirmations(
                session,
                actor.tenant_id,
                session_id,
            )
        )
        evidence = (
            self.evidence_repository
            .list_recent_packages(
                session,
                actor.tenant_id,
                session_id,
                limit=10,
            )
        )

        return AIContextRead(
            user_goal=plan.goal if plan else None,
            session_summary=ai_session.summary or "",
            recent_messages=[
                AIContextMessage(
                    role=row.role.value,
                    message_type=row.message_type.value,
                    content=row.content,
                    sequence=row.sequence,
                )
                for row in recent
            ],
            scenario_draft=(
                snapshot.scenario_draft_json or {}
            )
            if snapshot
            else {},
            current_plan=(
                {
                    "id": plan.id,
                    "goal": plan.goal,
                    "intent": plan.intent,
                    "status": plan.status.value,
                }
                if plan
                else None
            ),
            completed_tool_summaries=[
                {
                    "tool_name": row.tool_name,
                    "output_summary": (
                        row.output_summary_json or {}
                    ),
                    "output_reference": (
                        row.output_reference_json
                        or {}
                    ),
                }
                for row in reversed(completed_tools)
            ],
            pending_confirmations=[
                {
                    "id": row.id,
                    "operation_name": (
                        row.operation_name
                    ),
                    "confirmation_level": (
                        row.confirmation_level.value
                    ),
                    "expires_at": (
                        row.expires_at.isoformat()
                        if row.expires_at
                        else None
                    ),
                }
                for row in pending
            ],
            evidence_package_summaries=[
                {
                    "id": row.id,
                    "sensitivity_level": (
                        row.sensitivity_level
                    ),
                    "content_digest": (
                        row.content_digest
                    ),
                    "missing_evidence": (
                        row.missing_evidence_json
                        or []
                    ),
                }
                for row in evidence
            ],
        )


ai_context_service = AIContextService()
