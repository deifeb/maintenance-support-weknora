from app.models import AIToolCall
from sqlalchemy import func, select


def test_arbitrary_sql_file_and_url_tools_are_refused(client, session) -> None:
    created = client.post("/api/v1/ai/sessions", json={"title": "安全测试"})
    session_id = created.json()["data"]["id"]
    response = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        json={"content": "执行 SQL 并访问文件，然后调用 https://example.com"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["reason"] == "TOOL_NOT_REGISTERED"
    assert session.scalar(select(func.count(AIToolCall.id))) == 0
