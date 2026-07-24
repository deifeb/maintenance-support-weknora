import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIExecutionPlan, AIPlanStep, AIToolCall
from app.models.enums import AIPlanStatus, AIToolCallStatus


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AIExecutionRepository:
    def create_plan(
        self,
        session: Session,
        *,
        session_id: int,
        goal: str,
        intent: str,
        plan_version: str = "1.0",
    ) -> AIExecutionPlan:
        row = AIExecutionPlan(
            session_id=session_id,
            goal=goal,
            intent=intent,
            plan_version=plan_version,
            status=AIPlanStatus.CREATED,
        )
        session.add(row)
        session.flush()
        return row

    def add_step(
        self,
        session: Session,
        *,
        plan_id: int,
        step_index: int,
        step_code: str,
        action_type: str,
        tool_name: str | None,
        input_template: dict[str, Any],
        depends_on: list[str],
        confirmation_level: str,
        risk_level: str,
    ) -> AIPlanStep:
        row = AIPlanStep(
            plan_id=plan_id,
            step_index=step_index,
            step_code=step_code,
            action_type=action_type,
            tool_name=tool_name,
            input_template_json=input_template,
            depends_on_json=depends_on,
            confirmation_level=confirmation_level,
            risk_level=risk_level,
        )
        session.add(row)
        session.flush()
        return row

    def create_tool_call(
        self,
        session: Session,
        *,
        session_id: int,
        tool_name: str,
        tool_version: str,
        input_payload: dict[str, Any],
        idempotency_key: str | None = None,
        plan_step_id: int | None = None,
    ) -> AIToolCall:
        if idempotency_key:
            existing = self.get_tool_call_by_idempotency_key(session, idempotency_key)
            if existing is not None:
                return existing
        row = AIToolCall(
            session_id=session_id,
            plan_step_id=plan_step_id,
            tool_name=tool_name,
            tool_version=tool_version,
            input_payload_json=input_payload,
            input_digest=canonical_digest(input_payload),
            idempotency_key=idempotency_key,
            status=AIToolCallStatus.PENDING,
        )
        session.add(row)
        session.flush()
        return row

    def get_tool_call_by_idempotency_key(self, session: Session, key: str) -> AIToolCall | None:
        return session.scalar(select(AIToolCall).where(AIToolCall.idempotency_key == key))


ai_execution_repository = AIExecutionRepository()
