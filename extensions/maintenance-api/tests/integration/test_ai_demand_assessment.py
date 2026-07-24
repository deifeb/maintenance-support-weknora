import pytest
from app.services.ai_orchestration_service import ai_orchestration_service
from tests.ai.factories import create_ai_session


@pytest.mark.asyncio
async def test_scenario_preparation_emits_draft_snapshot(session) -> None:
    row = create_ai_session(session)
    result = await ai_orchestration_service.handle_message(
        session,
        row.id,
        "为某型装备10台制定30天任务需求场景",
        user_id="u1",
        permissions=set(),
    )
    assert result.scenario_draft is not None
    assert result.status.value in {"CLARIFICATION_REQUIRED", "PLANNED"}
