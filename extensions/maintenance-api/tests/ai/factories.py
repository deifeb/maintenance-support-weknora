from datetime import datetime, timezone
from typing import Any

from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel
from maintenance_ai.providers import DeterministicTestProvider, RuleFallbackProvider
from maintenance_ai.routing import ModelDefinition, ModelRegistry, ModelRouter, RouteDefinition
from sqlalchemy import select


def make_router(
    *,
    function_name: str,
    structured_payload: dict[str, Any] | None = None,
    text_payload: str | None = None,
    fail_mode: str | None = None,
) -> ModelRouter:
    fixtures: dict[str, Any] = {}
    if structured_payload is not None:
        fixtures[function_name] = structured_payload
    elif text_payload is not None:
        fixtures[function_name] = text_payload
    provider = DeterministicTestProvider(fixtures=fixtures)
    if fail_mode:
        provider.failures[function_name] = fail_mode
    registry = ModelRegistry(
        models={
            "local-test": ModelDefinition(
                name="local-test",
                provider=ProviderKind.DETERMINISTIC_TEST,
                model="deterministic-test",
                capabilities={
                    ModelCapability.TEXT,
                    ModelCapability.STRUCTURED_OUTPUT,
                    ModelCapability.STREAMING,
                },
                sensitivity_allowed=set(SensitivityLevel),
                context_window=32768,
                enabled=True,
            )
        },
        routes={
            function_name: RouteDefinition(
                primary="local-test",
                fallbacks=("RULE_FALLBACK",),
                required_capabilities={
                    ModelCapability.STRUCTURED_OUTPUT
                    if structured_payload is not None
                    else ModelCapability.TEXT
                },
            )
        },
    )
    return ModelRouter(
        registry,
        providers={"local-test": provider},
        rule_fallback=RuleFallbackProvider(),
    )


def create_ai_session(session, *, status=None, message_count: int = 0, event_count: int = 0):
    from app.models import AIEvent, AIMessage, AISession
    from app.models.enums import AIExecutionMode, AIMessageRole, AIMessageType, AISessionStatus

    row = AISession(
        session_code=f"AI-TEST-{datetime.now(timezone.utc).timestamp():.6f}",
        title="测试 AI 会话",
        status=status or AISessionStatus.CREATED,
        sensitivity_level="INTERNAL",
        execution_mode=AIExecutionMode.LLM,
        last_event_sequence=event_count,
        summary="结构化会话摘要",
        created_by="tester",
    )
    session.add(row)
    session.flush()
    for index in range(1, message_count + 1):
        session.add(
            AIMessage(
                session_id=row.id,
                role=AIMessageRole.USER,
                message_type=AIMessageType.USER_TEXT,
                content=f"message-{index}",
                sequence=index,
            )
        )
    for index in range(1, event_count + 1):
        session.add(
            AIEvent(
                session_id=row.id,
                sequence=index,
                event_type="TEST_EVENT",
                event_version="1.0",
                payload_json={"index": index},
                visibility="USER",
            )
        )
    session.flush()
    return row


def create_ai_session_with_messages(session, *, count: int):
    from app.models import AISessionSnapshot

    row = create_ai_session(session, message_count=count)
    session.add(
        AISessionSnapshot(
            session_id=row.id,
            snapshot_version=1,
            current_state=row.status.value,
            scenario_draft_json={"scenario_name": "测试场景"},
            field_sources_json={},
            execution_context_json={},
            pending_confirmations_json=[],
            completed_step_ids_json=[],
            evidence_package_ids_json=[],
        )
    )
    session.flush()
    return row


def create_ai_session_with_events(session, *, count: int):
    return create_ai_session(session, event_count=count)


def latest_model_call(session):
    from app.models import AIModelCall

    return session.scalar(select(AIModelCall).order_by(AIModelCall.id.desc()))


def create_ready_ai_session(session):
    from app.models import AISessionSnapshot
    from app.models.enums import AISessionStatus

    row = create_ai_session(session, status=AISessionStatus.PLANNED)
    row.active_scenario_version_id = 1

    def field(value, risk="HIGH"):
        return {
            "value": value,
            "source_type": "USER_CONFIRMED",
            "source_reference": None,
            "confidence": 1.0,
            "confirmed": True,
            "risk_level": risk,
        }

    session.add(
        AISessionSnapshot(
            session_id=row.id,
            snapshot_version=1,
            current_state=AISessionStatus.PLANNED.value,
            scenario_draft_json={
                "scenario_name": field("测试场景", "LOW"),
                "equipment_model": field("EQ-001"),
                "configuration_version": field("V1"),
                "equipment_quantity": field(10),
                "duration_days": field(30),
                "stages": field([{"code": "MISSION", "duration_hours": 720}]),
                "usage_intensity": field(1.0, "MEDIUM"),
                "service_level": field(0.95),
                "repair_policy": field("ENABLED"),
                "common_shock_policy": field("DISABLED"),
                "assumptions": [],
                "blocking_issues": [],
            },
            field_sources_json={},
            execution_context_json={},
            pending_confirmations_json=[],
            completed_step_ids_json=[],
            evidence_package_ids_json=[],
        )
    )
    session.flush()
    return row


def create_session_with_completed_query_step(session):
    from app.models import AIExecutionPlan, AIPlanStep, AIToolCall
    from app.models.enums import (
        AIPlanStatus,
        AIPlanStepStatus,
        AISessionStatus,
        AIToolCallStatus,
    )

    row = create_ai_session(session, status=AISessionStatus.PARTIALLY_COMPLETED)
    plan = AIExecutionPlan(
        session_id=row.id,
        goal="查询计算状态",
        intent="TASK_STATUS_QUERY",
        plan_version="1.0",
        validation_status="VALID",
        status=AIPlanStatus.EXECUTING,
    )
    session.add(plan)
    session.flush()
    step = AIPlanStep(
        plan_id=plan.id,
        step_index=1,
        step_code="query-status",
        action_type="CALL_TOOL",
        tool_name="get_calculation_status",
        input_template_json={"calculation_id": 1},
        depends_on_json=[],
        confirmation_level="NONE",
        risk_level="LOW",
        status=AIPlanStepStatus.COMPLETED,
        result_reference_json={"calculation_id": 1},
    )
    session.add(step)
    session.flush()
    session.add(
        AIToolCall(
            session_id=row.id,
            plan_step_id=step.id,
            tool_name="get_calculation_status",
            tool_version="1.0",
            input_payload_json={"calculation_id": 1},
            input_digest="0" * 64,
            status=AIToolCallStatus.SUCCEEDED,
            output_summary_json={"status": "SUCCEEDED"},
        )
    )
    session.flush()
    return row


def count_demand_calculations(session) -> int:
    from app.models import DemandCalculation
    from sqlalchemy import func, select

    return int(session.scalar(select(func.count(DemandCalculation.id))) or 0)


def count_tool_calls(session, tool_name: str) -> int:
    from app.models import AIToolCall
    from sqlalchemy import func, select

    return int(
        session.scalar(select(func.count(AIToolCall.id)).where(AIToolCall.tool_name == tool_name))
        or 0
    )
