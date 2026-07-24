from app.services.ai_context_service import ai_context_service
from tests.ai.factories import create_ai_session_with_messages


def test_context_uses_summary_recent_messages_and_structured_state(session) -> None:
    ai_session = create_ai_session_with_messages(session, count=20)
    context = ai_context_service.build_context(session, ai_session.id, recent_message_count=4)
    assert len(context.recent_messages) == 4
    assert context.session_summary
    assert context.scenario_draft["scenario_name"] == "测试场景"
    assert context.pending_confirmations == []
