from __future__ import annotations

from typing import Any

from maintenance_ai.enums import ModelCapability, SensitivityLevel
from maintenance_ai.exceptions import SensitiveRemoteCallBlockedError
from maintenance_ai.providers import StructuredCompletionRequest, TextMessage
from maintenance_ai.routing import ModelRegistry, ModelRouter
from maintenance_ai.scenarios import (
    RuleScenarioParser,
    ScenarioDraft,
    assess_clarifications,
    merge_field_values,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError
from app.models import (
    AIConfirmationRequest,
    AIExecutionPlan,
    AIPlanStep,
    AISessionSnapshot,
    DemandCalculation,
)
from app.models.enums import (
    AIConfirmationStatus,
    AIExecutionMode,
    AIPlanStatus,
    AIPlanStepStatus,
    AISessionStatus,
    AIToolCallStatus,
    CalculationStatus,
)
from app.repositories.ai_execution_repository import ai_execution_repository
from app.services.ai_confirmation_service import ai_confirmation_service
from app.services.ai_model_runtime import AIModelRuntime
from app.services.ai_plan_service import ai_plan_service
from app.services.ai_session_service import ai_session_service
from app.services.ai_tool_adapters import compute_tool_idempotency_key
from app.services.ai_tool_registry import ToolExecutionContext, ai_tool_registry


class AIOrchestrationResult(BaseModel):
    session_id: int
    status: AISessionStatus
    pending_confirmation_id: int | None = None
    confirmation_token: str | None = None
    completed_step_ids: list[str] = Field(default_factory=list)
    scenario_draft: dict[str, Any] | None = None
    linked_calculation_id: int | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


def _latest_snapshot(session: Session, session_id: int) -> AISessionSnapshot | None:
    return session.scalar(
        select(AISessionSnapshot)
        .where(AISessionSnapshot.session_id == session_id)
        .order_by(AISessionSnapshot.snapshot_version.desc())
    )


def _merge_drafts(current: ScenarioDraft | None, incoming: ScenarioDraft) -> ScenarioDraft:
    if current is None:
        return incoming
    values: dict[str, Any] = {}
    for name in ScenarioDraft.model_fields:
        if name in {"assumptions", "blocking_issues"}:
            values[name] = list(dict.fromkeys([*getattr(current, name), *getattr(incoming, name)]))
        else:
            values[name] = merge_field_values(
                getattr(current, name),
                getattr(incoming, name),
            )
    return ScenarioDraft(**values)


class AIOrchestrationService:
    def __init__(self, runtime_factory=AIModelRuntime.from_settings) -> None:
        self.runtime_factory = runtime_factory

    @staticmethod
    def _validate_model_override(
        *,
        sensitivity_level: str,
        model_override: str | None,
    ) -> None:
        if not model_override:
            return
        settings = get_settings()
        try:
            registry = ModelRegistry.from_yaml(
                settings.ai_models_config_path,
                settings.ai_routes_config_path,
            )
            ModelRouter(registry).route(
                "scenario_parsing",
                SensitivityLevel(sensitivity_level),
                {ModelCapability.STRUCTURED_OUTPUT},
                override=model_override,
            )
        except SensitiveRemoteCallBlockedError as exc:
            raise BusinessValidationError(
                "sensitive data cannot be sent to the requested remote model",
                code="SENSITIVE_REMOTE_CALL_BLOCKED",
                details={"model_override": model_override},
            ) from exc

    async def handle_message(
        self,
        session: Session,
        session_id: int,
        content: str,
        *,
        user_id: str,
        permissions: set[str],
        workspace_id: str = "default",
        model_override: str | None = None,
    ) -> AIOrchestrationResult:
        del workspace_id
        ai_session = ai_session_service.get(session, session_id)
        self._validate_model_override(
            sensitivity_level=ai_session.sensitivity_level,
            model_override=model_override,
        )
        ai_session_service.add_message(
            session,
            session_id,
            role="USER",
            message_type="USER_TEXT",
            content=content,
            structured_content={"model_override": model_override} if model_override else None,
        )
        normalized = content.lower()

        if any(term in normalized for term in ("sql", "shell", "访问文件", "http://", "https://")):
            ai_session.status = AISessionStatus.COMPLETED
            session.commit()
            ai_session_service.append_event(
                session,
                session_id,
                "COMPLETED",
                {"message": "高权限通用工具不在白名单中"},
            )
            return AIOrchestrationResult(
                session_id=session_id,
                status=ai_session.status,
                summary={"refused": True, "reason": "TOOL_NOT_REGISTERED"},
            )

        if "正式" in content and ("计算" in content or "需求" in content):
            snapshot = _latest_snapshot(session, session_id)
            draft = (
                ScenarioDraft.model_validate(snapshot.scenario_draft_json)
                if snapshot and snapshot.scenario_draft_json
                else None
            )
            readiness = assess_clarifications(draft) if draft else None
            if readiness is None or readiness.readiness.value != "READY_FOR_PREVIEW":
                raise BusinessValidationError(
                    "high-risk scenario fields must be confirmed before formal calculation",
                    code="SCENARIO_CLARIFICATION_REQUIRED",
                    details={
                        "missing_fields": []
                        if readiness is None
                        else list(readiness.missing_fields)
                    },
                )
            if ai_session.active_scenario_version_id is None:
                raise BusinessValidationError(
                    "a published scenario version must be selected before formal calculation",
                    code="SCENARIO_VERSION_REQUIRED",
                )

            plan = ai_plan_service.create_and_validate(session, session_id, content)
            steps = list(
                session.scalars(
                    select(AIPlanStep)
                    .where(AIPlanStep.plan_id == plan.id)
                    .order_by(AIPlanStep.step_index)
                ).all()
            )
            preview_payload = {
                "scenario_version_id": ai_session.active_scenario_version_id,
                "requested_mode": "AUTO",
            }
            calculation_payload = {
                **preview_payload,
                "calculation_name": f"AI会话{ai_session.session_code}需求计算",
                "execution_preference": "ASYNC",
                "random_seed": 20260724,
            }
            calculate_step: AIPlanStep | None = None
            for step in steps:
                if step.tool_name == "prepare_demand_scenario":
                    step.input_template_json = {
                        "scenario_version_id": ai_session.active_scenario_version_id
                    }
                elif step.tool_name == "preview_demand_calculation":
                    step.input_template_json = preview_payload
                elif step.tool_name == "start_demand_calculation":
                    step.input_template_json = calculation_payload
                    calculate_step = step
            session.commit()
            if calculate_step is None:
                raise BusinessValidationError(
                    "calculation plan has no formal calculation step",
                    code="PLAN_VALIDATION_FAILED",
                )
            confirmation, token = ai_confirmation_service.create(
                session,
                session_id=session_id,
                operation_name="start_demand_calculation",
                confirmation_level="EXPLICIT",
                input_payload=calculation_payload,
                risk_level="HIGH",
            )
            confirmation.plan_step_id = calculate_step.id
            ai_session.status = AISessionStatus.CONFIRMATION_REQUIRED
            session.commit()
            ai_session_service.append_event(
                session,
                session_id,
                "CONFIRMATION_REQUIRED",
                {
                    "confirmation_id": confirmation.id,
                    "operation_name": confirmation.operation_name,
                    "input_digest": confirmation.input_digest,
                },
            )
            return AIOrchestrationResult(
                session_id=session_id,
                status=ai_session.status,
                pending_confirmation_id=confirmation.id,
                confirmation_token=token,
                scenario_draft=draft.model_dump(mode="json"),
            )

        ai_session.status = AISessionStatus.UNDERSTANDING
        session.commit()
        rule_draft = RuleScenarioParser().parse(content)
        request_metadata: dict[str, Any] = {
            "rule_fallback_data": rule_draft.model_dump(mode="json")
        }
        if model_override:
            request_metadata["model_override"] = model_override
        try:
            runtime = self.runtime_factory()
            completion = await runtime.complete_structured(
                session,
                session_id=session_id,
                request=StructuredCompletionRequest(
                    messages=(TextMessage(role="user", content=content),),
                    function_name="scenario_parsing",
                    sensitivity=SensitivityLevel(ai_session.sensitivity_level),
                    prompt_name="scenario-parser",
                    prompt_version="1.0",
                    schema_version="1.0",
                    metadata=request_metadata,
                ),
                response_model=ScenarioDraft,
            )
            incoming = ScenarioDraft.model_validate(completion.data)
            execution_mode = completion.execution_mode.value
            llm_generated = completion.llm_generated
            fallback_reason = completion.fallback_reason
        except SensitiveRemoteCallBlockedError as exc:
            raise BusinessValidationError(
                "sensitive data cannot be sent to the requested remote model",
                code="SENSITIVE_REMOTE_CALL_BLOCKED",
                details={"model_override": model_override},
            ) from exc
        except Exception as exc:
            incoming = rule_draft
            execution_mode = "RULE_FALLBACK"
            llm_generated = False
            fallback_reason = f"runtime failure: {type(exc).__name__}"
        previous_snapshot = _latest_snapshot(session, session_id)
        previous = (
            ScenarioDraft.model_validate(previous_snapshot.scenario_draft_json)
            if previous_snapshot and previous_snapshot.scenario_draft_json
            else None
        )
        draft = _merge_drafts(previous, incoming)
        clarification = assess_clarifications(draft)
        ai_session.status = (
            AISessionStatus.CLARIFICATION_REQUIRED
            if clarification.readiness.value == "CLARIFICATION_REQUIRED"
            else AISessionStatus.PLANNED
        )
        ai_session.execution_mode = AIExecutionMode(execution_mode)
        session.commit()
        ai_session_service.create_snapshot(
            session,
            session_id,
            scenario_draft=draft.model_dump(mode="json"),
            field_sources={
                key: value.get("source_type")
                for key, value in draft.model_dump(mode="json").items()
                if isinstance(value, dict) and value.get("source_type")
            },
        )
        ai_session_service.append_event(
            session,
            session_id,
            "FALLBACK_TRIGGERED" if execution_mode == "RULE_FALLBACK" else "MODEL_ROUTED",
            {
                "execution_mode": execution_mode,
                "llm_generated": llm_generated,
                "reason": fallback_reason,
            },
        )
        ai_session_service.append_event(
            session,
            session_id,
            "CLARIFICATION_REQUIRED"
            if ai_session.status is AISessionStatus.CLARIFICATION_REQUIRED
            else "SCENARIO_DRAFT_UPDATED",
            {
                "readiness": clarification.readiness.value,
                "questions": list(clarification.questions),
            },
        )
        return AIOrchestrationResult(
            session_id=session_id,
            status=ai_session.status,
            scenario_draft=draft.model_dump(mode="json"),
            summary={"execution_mode": execution_mode, "llm_generated": llm_generated},
        )

    async def resume(
        self,
        session: Session,
        session_id: int,
        *,
        user_id: str,
        permissions: set[str],
        workspace_id: str = "default",
    ) -> AIOrchestrationResult:
        del user_id, permissions, workspace_id
        ai_session = ai_session_service.get(session, session_id)
        completed = list(
            session.scalars(
                select(AIPlanStep)
                .join(AIExecutionPlan, AIExecutionPlan.id == AIPlanStep.plan_id)
                .where(
                    AIExecutionPlan.session_id == session_id,
                    AIPlanStep.status == AIPlanStepStatus.COMPLETED,
                )
                .order_by(AIPlanStep.step_index)
            ).all()
        )
        return AIOrchestrationResult(
            session_id=session_id,
            status=ai_session.status,
            completed_step_ids=[row.step_code for row in completed],
            linked_calculation_id=ai_session.active_calculation_id,
        )

    async def execute_plan(
        self,
        session: Session,
        session_id: int,
        *,
        user_id: str,
        permissions: set[str],
        workspace_id: str = "default",
    ) -> AIOrchestrationResult:
        ai_session = ai_session_service.get(session, session_id)
        if ai_session.active_calculation_id is not None:
            calculation = session.get(DemandCalculation, ai_session.active_calculation_id)
            if calculation is not None and calculation.status in {
                CalculationStatus.PENDING,
                CalculationStatus.RUNNING,
            }:
                ai_session.status = AISessionStatus.WAITING_ASYNC_TASK
                session.commit()
                return await self.resume(
                    session,
                    session_id,
                    user_id=user_id,
                    permissions=permissions,
                    workspace_id=workspace_id,
                )
            if calculation is None or calculation.status in {
                CalculationStatus.FAILED,
                CalculationStatus.CANCELLED,
                CalculationStatus.INTERRUPTED,
            }:
                ai_session.status = AISessionStatus.PARTIALLY_COMPLETED
                session.commit()
                return await self.resume(
                    session,
                    session_id,
                    user_id=user_id,
                    permissions=permissions,
                    workspace_id=workspace_id,
                )

        plan = session.scalar(
            select(AIExecutionPlan)
            .where(AIExecutionPlan.session_id == session_id)
            .order_by(AIExecutionPlan.id.desc())
        )
        if plan is None:
            return await self.resume(
                session,
                session_id,
                user_id=user_id,
                permissions=permissions,
                workspace_id=workspace_id,
            )
        plan.status = AIPlanStatus.EXECUTING
        ai_session.status = AISessionStatus.EXECUTING
        session.commit()
        steps = list(
            session.scalars(
                select(AIPlanStep)
                .where(AIPlanStep.plan_id == plan.id)
                .order_by(AIPlanStep.step_index)
            ).all()
        )
        completed_codes = {
            step.step_code for step in steps if step.status is AIPlanStepStatus.COMPLETED
        }
        for step in steps:
            if step.status is AIPlanStepStatus.COMPLETED:
                continue
            if not set(step.depends_on_json or []).issubset(completed_codes):
                continue
            definition = ai_tool_registry.get(step.tool_name or "")
            approved_confirmation = session.scalar(
                select(AIConfirmationRequest).where(
                    AIConfirmationRequest.session_id == session_id,
                    AIConfirmationRequest.plan_step_id == step.id,
                    AIConfirmationRequest.status == AIConfirmationStatus.APPROVED,
                )
            )
            if approved_confirmation is None and step.tool_name == "run_demand_assessment":
                approved_confirmation = session.scalar(
                    select(AIConfirmationRequest).where(
                        AIConfirmationRequest.session_id == session_id,
                        AIConfirmationRequest.operation_name == "start_demand_calculation",
                        AIConfirmationRequest.status == AIConfirmationStatus.APPROVED,
                    )
                )
            approved = approved_confirmation is not None
            if definition.confirmation_level.value in {"EXPLICIT", "SECONDARY"} and not approved:
                confirmation, token = ai_confirmation_service.create(
                    session,
                    session_id=session_id,
                    operation_name=definition.name,
                    confirmation_level=definition.confirmation_level.value,
                    input_payload=step.input_template_json or {},
                    risk_level=step.risk_level,
                )
                confirmation.plan_step_id = step.id
                ai_session.status = AISessionStatus.CONFIRMATION_REQUIRED
                session.commit()
                return AIOrchestrationResult(
                    session_id=session_id,
                    status=ai_session.status,
                    pending_confirmation_id=confirmation.id,
                    confirmation_token=token,
                    completed_step_ids=sorted(completed_codes),
                )
            input_payload = dict(step.input_template_json or {})
            if step.tool_name in {"run_demand_assessment", "get_calculation_status"}:
                input_payload.setdefault("calculation_id", ai_session.active_calculation_id)
            key = compute_tool_idempotency_key(
                session_id=session_id,
                plan_step_id=step.id,
                tool_version=definition.version,
                payload=input_payload,
            )
            existing = ai_execution_repository.get_tool_call_by_idempotency_key(session, key)
            if existing is not None and existing.status is AIToolCallStatus.SUCCEEDED:
                step.status = AIPlanStepStatus.COMPLETED
                step.result_reference_json = existing.output_reference_json
                completed_codes.add(step.step_code)
                session.commit()
                continue
            call = ai_execution_repository.create_tool_call(
                session,
                session_id=session_id,
                plan_step_id=step.id,
                tool_name=definition.name,
                tool_version=definition.version,
                input_payload=input_payload,
                idempotency_key=key,
            )
            call.status = AIToolCallStatus.RUNNING
            step.status = AIPlanStepStatus.RUNNING
            session.commit()
            ai_session_service.append_event(
                session,
                session_id,
                "TOOL_STARTED",
                {"tool_call_id": call.id, "tool_name": definition.name},
            )
            try:
                output = ai_tool_registry.execute(
                    session,
                    definition.name,
                    input_payload,
                    ToolExecutionContext(
                        user_id=user_id,
                        workspace_id=workspace_id,
                        permissions=permissions,
                        intent=plan.intent,
                        sensitivity_level=ai_session.sensitivity_level,
                        session_id=session_id,
                        plan_step_id=step.id,
                        confirmation_approved=approved,
                        business_idempotency_key=key,
                    ),
                )
                call.status = AIToolCallStatus.SUCCEEDED
                call.output_summary_json = output
                call.output_reference_json = output
                step.status = AIPlanStepStatus.COMPLETED
                step.result_reference_json = output
                completed_codes.add(step.step_code)
                if output.get("calculation_id"):
                    ai_session.active_calculation_id = output["calculation_id"]
                session.commit()
                ai_session_service.append_event(
                    session,
                    session_id,
                    "TOOL_COMPLETED",
                    {"tool_call_id": call.id, "tool_name": definition.name},
                )
                if definition.name == "start_demand_calculation":
                    ai_session.status = AISessionStatus.WAITING_ASYNC_TASK
                    session.commit()
                    ai_session_service.append_event(
                        session,
                        session_id,
                        "CALCULATION_LINKED",
                        {"calculation_id": ai_session.active_calculation_id},
                    )
                    return AIOrchestrationResult(
                        session_id=session_id,
                        status=ai_session.status,
                        completed_step_ids=sorted(completed_codes),
                        linked_calculation_id=ai_session.active_calculation_id,
                    )
            except Exception as exc:
                call.status = AIToolCallStatus.FAILED
                call.error_code = getattr(exc, "code", type(exc).__name__.upper())
                call.error_message = str(exc)[:2000]
                step.status = AIPlanStepStatus.FAILED
                ai_session.status = AISessionStatus.PARTIALLY_COMPLETED
                session.commit()
                raise
        if all(step.status is AIPlanStepStatus.COMPLETED for step in steps):
            plan.status = AIPlanStatus.COMPLETED
            ai_session.status = AISessionStatus.COMPLETED
            session.commit()
            ai_session_service.append_event(session, session_id, "COMPLETED", {})
        return AIOrchestrationResult(
            session_id=session_id,
            status=ai_session.status,
            completed_step_ids=sorted(completed_codes),
            linked_calculation_id=ai_session.active_calculation_id,
        )


ai_orchestration_service = AIOrchestrationService()
