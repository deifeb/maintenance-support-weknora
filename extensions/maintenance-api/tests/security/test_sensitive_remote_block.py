from app.models import AIModelCall
from sqlalchemy import func, select


def test_confidential_session_cannot_override_to_remote_model(client, session) -> None:
    created = client.post(
        "/api/v1/ai/sessions",
        json={"title": "敏感任务", "sensitivity_level": "CONFIDENTIAL"},
    )
    session_id = created.json()["data"]["id"]
    response = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        json={"content": "分析任务", "model_override": "remote-strong"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SENSITIVE_REMOTE_CALL_BLOCKED"
    assert session.scalar(select(func.count(AIModelCall.id))) == 0
