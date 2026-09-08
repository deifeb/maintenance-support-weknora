from app.repositories.ai_execution_repository import (
    AIExecutionRepository,
)
from app.repositories.ai_session_repository import (
    AISessionRepository,
)


def test_event_sequence_and_idempotent_tool_lookup(
    session,
):
    srepo = AISessionRepository()
    row = srepo.create_session(
        session,
        "tenant-a",
        title="Event test",
        sensitivity_level="INTERNAL",
        created_by="tester",
    )
    one = srepo.append_event(
        session,
        "tenant-a",
        row.id,
        "SESSION_STARTED",
        {"a": 1},
    )
    two = srepo.append_event(
        session,
        "tenant-a",
        row.id,
        "PLAN_CREATED",
        {"b": 2},
    )
    assert (
        one.sequence,
        two.sequence,
        row.last_event_sequence,
    ) == (1, 2, 2)

    erepo = AIExecutionRepository()
    call = erepo.create_tool_call(
        session,
        "tenant-a",
        session_id=row.id,
        tool_name="get_calculation_status",
        tool_version="1.0",
        idempotency_key="same-key",
        input_payload={"calculation_id": 1},
    )
    session.flush()

    loaded = (
        erepo.get_tool_call_by_idempotency_key(
            session,
            "tenant-a",
            "same-key",
        )
    )
    assert loaded is not None
    assert loaded.id == call.id
