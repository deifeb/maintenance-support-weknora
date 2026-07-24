from app.services.ai_tool_adapters import compute_tool_idempotency_key


def test_tool_idempotency_key_is_canonical() -> None:
    first = compute_tool_idempotency_key(
        session_id=1,
        plan_step_id=2,
        tool_version="1.0",
        payload={"b": 2, "a": 1},
    )
    second = compute_tool_idempotency_key(
        session_id=1,
        plan_step_id=2,
        tool_version="1.0",
        payload={"a": 1, "b": 2},
    )
    assert first == second
    assert len(first) == 64
