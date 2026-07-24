def test_ai_routes_are_registered(client) -> None:
    paths = set(client.app.openapi()["paths"])
    expected = {
        "/api/v1/ai/sessions",
        "/api/v1/ai/sessions/{session_id}",
        "/api/v1/ai/sessions/{session_id}/messages",
        "/api/v1/ai/sessions/{session_id}/events",
        "/api/v1/ai/sessions/{session_id}/stream",
        "/api/v1/ai/sessions/{session_id}/resume",
        "/api/v1/ai/sessions/{session_id}/cancel",
        "/api/v1/ai/confirmations/{confirmation_id}/approve",
        "/api/v1/ai/confirmations/{confirmation_id}/reject",
        "/api/v1/ai/model-routes",
        "/api/v1/ai/model-routes/preview",
        "/api/v1/ai/providers/health",
    }
    assert expected <= paths
