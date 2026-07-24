def test_create_and_read_ai_session(client) -> None:
    created = client.post(
        "/api/v1/ai/sessions",
        json={"title": "任务需求会话", "sensitivity_level": "INTERNAL"},
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]
    read = client.get(f"/api/v1/ai/sessions/{session_id}")
    assert read.status_code == 200
    assert read.json()["data"]["title"] == "任务需求会话"
