from app.models import AISession
from app.models.enums import AIExecutionMode


def test_unavailable_llm_path_is_explicit_rule_fallback(client, session, monkeypatch) -> None:
    from app.services.ai_model_runtime import AIModelRuntime
    from app.services.ai_orchestration_service import ai_orchestration_service
    from tests.ai.factories import make_router

    monkeypatch.setattr(
        ai_orchestration_service,
        "runtime_factory",
        lambda: AIModelRuntime(
            router=make_router(function_name="scenario_parsing", fail_mode="unavailable")
        ),
    )
    created = client.post(
        "/api/v1/ai/sessions",
        json={"title": "规则降级", "sensitivity_level": "INTERNAL"},
    )
    session_id = created.json()["data"]["id"]
    response = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        json={"content": "示例装备1采用V1构型，10台执行30天任务，保障率95%"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["summary"] == {
        "execution_mode": "RULE_FALLBACK",
        "llm_generated": False,
    }
    row = session.get(AISession, session_id)
    session.refresh(row)
    assert row.execution_mode is AIExecutionMode.RULE_FALLBACK
    events = client.get(f"/api/v1/ai/sessions/{session_id}/events").json()["data"]
    assert any(event["event_type"] == "FALLBACK_TRIGGERED" for event in events)
