from app.repositories.ai_execution_repository import AIExecutionRepository
from app.repositories.ai_session_repository import AISessionRepository


def test_event_sequence_and_idempotent_tool_lookup(session):
    srepo = AISessionRepository()
    row = srepo.create_session(
        session, title="事件测试", sensitivity_level="INTERNAL", created_by="tester"
    )
    one = srepo.append_event(session, row.id, "SESSION_STARTED", {"a": 1})
    two = srepo.append_event(session, row.id, "PLAN_CREATED", {"b": 2})
    assert (one.sequence, two.sequence, row.last_event_sequence) == (1, 2, 2)
    erepo = AIExecutionRepository()
    call = erepo.create_tool_call(
        session,
        session_id=row.id,
        tool_name="get_calculation_status",
        tool_version="1.0",
        idempotency_key="same-key",
        input_payload={"calculation_id": 1},
    )
    session.flush()
    assert erepo.get_tool_call_by_idempotency_key(session, "same-key").id == call.id
