import pytest
from app.models.enums import AISessionStatus
from app.services.ai_orchestration_service import ai_orchestration_service
from tests.ai.factories import (
    count_demand_calculations,
    count_tool_calls,
    create_ready_ai_session,
    create_session_with_completed_query_step,
)


@pytest.mark.asyncio
async def test_formal_calculation_pauses_at_confirmation(session) -> None:
    ai_session = create_ready_ai_session(session)
    result = await ai_orchestration_service.handle_message(
        session,
        ai_session.id,
        "按当前场景执行正式需求计算",
        user_id="u1",
        permissions={"CALCULATION_EXECUTE"},
    )
    session.commit()
    assert result.status is AISessionStatus.CONFIRMATION_REQUIRED
    assert result.pending_confirmation_id is not None
    assert count_demand_calculations(session) == 0


@pytest.mark.asyncio
async def test_resume_does_not_repeat_completed_tool_step(session) -> None:
    ai_session = create_session_with_completed_query_step(session)
    first = await ai_orchestration_service.resume(
        session,
        ai_session.id,
        user_id="u1",
        permissions=set(),
    )
    second = await ai_orchestration_service.resume(
        session,
        ai_session.id,
        user_id="u1",
        permissions=set(),
    )
    assert first.completed_step_ids == second.completed_step_ids
    assert count_tool_calls(session, "get_calculation_status") == 1
