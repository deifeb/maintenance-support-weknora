from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIConfirmationRequest,
    AIExecutionPlan,
    AIModelCall,
    AIPlanStep,
    AISession,
    AIToolCall,
)
from app.models.enums import (
    AIConfirmationLevel,
    AIConfirmationStatus,
    AIModelCallStatus,
    AIPlanStatus,
    AIPlanStepStatus,
    AIToolCallStatus,
)
from app.repositories.base import tenant_loader_criteria

ModelT = TypeVar("ModelT")


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT | None:
    return session.scalar(
        select(model)
        .options(tenant_loader_criteria(tenant_id))
        .execution_options(populate_existing=True)
        .where(
            model.id == identifier,
            model.tenant_id == tenant_id,
        )
    )


def _require_owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT:
    row = _owned(
        session,
        tenant_id,
        model,
        identifier,
    )
    if row is None:
        raise LookupError(
            f"{model.__name__} {identifier} not found"
        )
    return row


class AIExecutionRepository:
    def create_plan(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int,
        goal: str,
        intent: str,
        plan_version: str = "1.0",
    ) -> AIExecutionPlan:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        row = AIExecutionPlan(
            tenant_id=tenant_id,
            session_id=session_id,
            goal=goal,
            intent=intent,
            plan_version=plan_version,
            status=AIPlanStatus.CREATED,
        )
        session.add(row)
        session.flush()
        return row

    def get_plan(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> AIExecutionPlan | None:
        return _owned(
            session,
            tenant_id,
            AIExecutionPlan,
            plan_id,
        )

    def latest_plan(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> AIExecutionPlan | None:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        return session.scalar(
            select(AIExecutionPlan)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AIExecutionPlan.tenant_id == tenant_id,
                AIExecutionPlan.session_id == session_id,
            )
            .order_by(AIExecutionPlan.id.desc())
            .limit(1)
        )

    def add_step(
        self,
        session: Session,
        tenant_id: str,
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
        _require_owned(
            session,
            tenant_id,
            AIExecutionPlan,
            plan_id,
        )
        row = AIPlanStep(
            tenant_id=tenant_id,
            plan_id=plan_id,
            step_index=step_index,
            step_code=step_code,
            action_type=action_type,
            tool_name=tool_name,
            input_template_json=input_template,
            depends_on_json=depends_on,
            confirmation_level=AIConfirmationLevel(
                confirmation_level
            ),
            risk_level=risk_level,
        )
        session.add(row)
        session.flush()
        return row

    def get_step(
        self,
        session: Session,
        tenant_id: str,
        step_id: int,
    ) -> AIPlanStep | None:
        return _owned(
            session,
            tenant_id,
            AIPlanStep,
            step_id,
        )

    def list_steps(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> list[AIPlanStep]:
        _require_owned(
            session,
            tenant_id,
            AIExecutionPlan,
            plan_id,
        )
        return list(
            session.scalars(
                select(AIPlanStep)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIPlanStep.tenant_id == tenant_id,
                    AIPlanStep.plan_id == plan_id,
                )
                .order_by(AIPlanStep.step_index)
            ).all()
        )

    def list_completed_steps(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> list[AIPlanStep]:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        return list(
            session.scalars(
                select(AIPlanStep)
                .join(
                    AIExecutionPlan,
                    AIExecutionPlan.id
                    == AIPlanStep.plan_id,
                )
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIPlanStep.tenant_id == tenant_id,
                    AIExecutionPlan.tenant_id
                    == tenant_id,
                    AIExecutionPlan.session_id
                    == session_id,
                    AIPlanStep.status
                    == AIPlanStepStatus.COMPLETED,
                )
                .order_by(AIPlanStep.step_index)
            ).all()
        )

    def create_tool_call(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int,
        tool_name: str,
        tool_version: str,
        input_payload: dict[str, Any],
        idempotency_key: str | None = None,
        plan_step_id: int | None = None,
    ) -> AIToolCall:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        if plan_step_id is not None:
            _require_owned(
                session,
                tenant_id,
                AIPlanStep,
                plan_step_id,
            )
        if idempotency_key:
            existing = (
                self.get_tool_call_by_idempotency_key(
                    session,
                    tenant_id,
                    idempotency_key,
                )
            )
            if existing is not None:
                return existing
        row = AIToolCall(
            tenant_id=tenant_id,
            session_id=session_id,
            plan_step_id=plan_step_id,
            tool_name=tool_name,
            tool_version=tool_version,
            input_payload_json=input_payload,
            input_digest=canonical_digest(
                input_payload
            ),
            idempotency_key=idempotency_key,
            status=AIToolCallStatus.PENDING,
        )
        session.add(row)
        session.flush()
        return row

    def get_tool_call(
        self,
        session: Session,
        tenant_id: str,
        tool_call_id: int,
    ) -> AIToolCall | None:
        return _owned(
            session,
            tenant_id,
            AIToolCall,
            tool_call_id,
        )

    def get_tool_call_by_idempotency_key(
        self,
        session: Session,
        tenant_id: str,
        key: str,
    ) -> AIToolCall | None:
        return session.scalar(
            select(AIToolCall)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AIToolCall.tenant_id == tenant_id,
                AIToolCall.idempotency_key == key,
            )
        )

    def list_completed_tool_calls(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        limit: int = 20,
    ) -> list[AIToolCall]:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        return list(
            session.scalars(
                select(AIToolCall)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIToolCall.tenant_id == tenant_id,
                    AIToolCall.session_id == session_id,
                    AIToolCall.status
                    == AIToolCallStatus.SUCCEEDED,
                )
                .order_by(AIToolCall.id.desc())
                .limit(limit)
            ).all()
        )

    def create_confirmation(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int,
        operation_name: str,
        confirmation_level: str,
        input_preview: dict[str, Any],
        input_digest: str,
        confirmation_token_hash: str,
        risk_level: str,
        data_externalization: bool = False,
        expires_at: datetime | None = None,
        plan_step_id: int | None = None,
    ) -> AIConfirmationRequest:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        if plan_step_id is not None:
            _require_owned(
                session,
                tenant_id,
                AIPlanStep,
                plan_step_id,
            )
        row = AIConfirmationRequest(
            tenant_id=tenant_id,
            session_id=session_id,
            plan_step_id=plan_step_id,
            operation_name=operation_name,
            confirmation_level=AIConfirmationLevel(
                confirmation_level
            ),
            status=AIConfirmationStatus.PENDING,
            input_preview_json=input_preview,
            input_digest=input_digest,
            confirmation_token_hash=(
                confirmation_token_hash
            ),
            risk_level=risk_level,
            data_externalization=data_externalization,
            expires_at=expires_at,
        )
        session.add(row)
        session.flush()
        return row

    def get_confirmation(
        self,
        session: Session,
        tenant_id: str,
        confirmation_id: int,
    ) -> AIConfirmationRequest | None:
        return _owned(
            session,
            tenant_id,
            AIConfirmationRequest,
            confirmation_id,
        )

    def list_pending_confirmations(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
    ) -> list[AIConfirmationRequest]:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        return list(
            session.scalars(
                select(AIConfirmationRequest)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIConfirmationRequest.tenant_id
                    == tenant_id,
                    AIConfirmationRequest.session_id
                    == session_id,
                    AIConfirmationRequest.status
                    == AIConfirmationStatus.PENDING,
                )
                .order_by(AIConfirmationRequest.id)
            ).all()
        )

    def find_approved_confirmation(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int,
        plan_step_id: int | None = None,
        operation_name: str | None = None,
    ) -> AIConfirmationRequest | None:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        stmt = select(AIConfirmationRequest).where(
            AIConfirmationRequest.tenant_id
            == tenant_id,
            AIConfirmationRequest.session_id
            == session_id,
            AIConfirmationRequest.status
            == AIConfirmationStatus.APPROVED,
        )
        if plan_step_id is not None:
            stmt = stmt.where(
                AIConfirmationRequest.plan_step_id
                == plan_step_id
            )
        if operation_name is not None:
            stmt = stmt.where(
                AIConfirmationRequest.operation_name
                == operation_name
            )
        return session.scalar(
            stmt.options(
                tenant_loader_criteria(tenant_id)
            )
            .execution_options(populate_existing=True)
            .order_by(AIConfirmationRequest.id.desc())
            .limit(1)
        )

    def create_model_call(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int | None,
        request_id: str,
        function_name: str,
        provider: str,
        model: str,
        prompt_name: str,
        prompt_version: str,
        sensitivity_level: str,
        input_digest: str,
        schema_version: str | None = None,
        status: AIModelCallStatus | str = (
            AIModelCallStatus.PENDING
        ),
    ) -> AIModelCall:
        if session_id is not None:
            _require_owned(
                session,
                tenant_id,
                AISession,
                session_id,
            )
        row = AIModelCall(
            tenant_id=tenant_id,
            session_id=session_id,
            request_id=request_id,
            function_name=function_name,
            provider=provider,
            model=model,
            status=AIModelCallStatus(status),
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            schema_version=schema_version,
            sensitivity_level=sensitivity_level,
            input_digest=input_digest,
        )
        session.add(row)
        session.flush()
        return row

    def get_model_call(
        self,
        session: Session,
        tenant_id: str,
        model_call_id: int,
    ) -> AIModelCall | None:
        return _owned(
            session,
            tenant_id,
            AIModelCall,
            model_call_id,
        )


ai_execution_repository = AIExecutionRepository()
