from app.models import AISession
from app.models.enums import AIExecutionMode
from sqlalchemy import select


def test_unavailable_llm_path_is_explicit_rule_fallback(
    authenticated_client,
    session,
    monkeypatch,
) -> None:
    from app.services.ai_model_runtime import AIModelRuntime
    from app.services.ai_orchestration_service import (
        ai_orchestration_service,
    )
    from tests.ai.factories import make_router

    monkeypatch.setattr(
        ai_orchestration_service,
        "runtime_factory",
        lambda: AIModelRuntime(
            router=make_router(
                function_name="scenario_parsing",
                fail_mode="unavailable",
            )
        ),
    )
    created = authenticated_client.post(
        "/api/v1/ai/sessions",
        json={
            "title": "规则降级",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]
    response = authenticated_client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        json={
            "content": (
                "示例装备1采用V1构型，10台执行30天任务，"
                "保障率95%"
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["summary"] == {
        "execution_mode": "RULE_FALLBACK",
        "llm_generated": False,
    }
    row = session.scalar(
        select(AISession).where(
            AISession.id == session_id,
            AISession.tenant_id == "tenant-a",
        )
    )
    assert row is not None
    session.refresh(row)
    assert (
        row.execution_mode
        is AIExecutionMode.RULE_FALLBACK
    )
    events = authenticated_client.get(
        f"/api/v1/ai/sessions/{session_id}/events"
    ).json()["data"]
    assert any(
        event["event_type"] == "FALLBACK_TRIGGERED"
        for event in events
    )
