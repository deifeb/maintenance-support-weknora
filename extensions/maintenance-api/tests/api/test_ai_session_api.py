def test_session_message_and_events_flow(client):
    created = client.post(
        "/api/v1/ai/sessions", json={"title": "需求分析", "sensitivity_level": "INTERNAL"}
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]
    message = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        json={"content": "10台装备执行30天任务，保障率95%"},
    )
    assert message.status_code == 200
    data = message.json()["data"]
    assert data["scenario_draft"]["equipment_quantity"]["value"] == 10
    events = client.get(f"/api/v1/ai/sessions/{session_id}/events").json()["data"]
    assert events[0]["sequence"] == 1
