from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import (
    AIConfirmationRequest,
    AIEvidencePackage,
    AIExecutionPlan,
    AIMessage,
    AISession,
    AISessionSnapshot,
    AIToolCall,
)
from app.models.enums import AIConfirmationStatus, AIToolCallStatus
from app.schemas.ai_model import AIContextMessage, AIContextRead


class AIContextService:
    def build_context(
        self,
        session: Session,
        session_id: int,
        *,
        recent_message_count: int = 12,
    ) -> AIContextRead:
        ai_session = session.get(AISession, session_id)
        if ai_session is None:
            raise NotFoundError("ai_session", session_id)
        recent = list(
            session.scalars(
                select(AIMessage)
                .where(AIMessage.session_id == session_id)
                .order_by(AIMessage.sequence.desc())
                .limit(recent_message_count)
            ).all()
        )
        recent.reverse()
        snapshot = session.scalar(
            select(AISessionSnapshot)
            .where(AISessionSnapshot.session_id == session_id)
            .order_by(AISessionSnapshot.snapshot_version.desc())
        )
        plan = session.scalar(
            select(AIExecutionPlan)
            .where(AIExecutionPlan.session_id == session_id)
            .order_by(AIExecutionPlan.id.desc())
        )
        completed_tools = list(
            session.scalars(
                select(AIToolCall)
                .where(
                    AIToolCall.session_id == session_id,
                    AIToolCall.status == AIToolCallStatus.SUCCEEDED,
                )
                .order_by(AIToolCall.id.desc())
                .limit(20)
            ).all()
        )
        pending = list(
            session.scalars(
                select(AIConfirmationRequest).where(
                    AIConfirmationRequest.session_id == session_id,
                    AIConfirmationRequest.status == AIConfirmationStatus.PENDING,
                )
            ).all()
        )
        evidence = list(
            session.scalars(
                select(AIEvidencePackage)
                .where(AIEvidencePackage.session_id == session_id)
                .order_by(AIEvidencePackage.id.desc())
                .limit(10)
            ).all()
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
            scenario_draft=(snapshot.scenario_draft_json or {}) if snapshot else {},
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
                    "output_summary": row.output_summary_json or {},
                    "output_reference": row.output_reference_json or {},
                }
                for row in reversed(completed_tools)
            ],
            pending_confirmations=[
                {
                    "id": row.id,
                    "operation_name": row.operation_name,
                    "confirmation_level": row.confirmation_level.value,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                }
                for row in pending
            ],
            evidence_package_summaries=[
                {
                    "id": row.id,
                    "sensitivity_level": row.sensitivity_level,
                    "content_digest": row.content_digest,
                    "missing_evidence": row.missing_evidence_json or [],
                }
                for row in evidence
            ],
        )


ai_context_service = AIContextService()
