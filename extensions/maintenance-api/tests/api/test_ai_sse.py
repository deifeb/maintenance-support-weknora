from tests.ai.factories import create_ai_session_with_events


def test_sse_stream_resumes_after_last_event(client, session) -> None:
    ai_session = create_ai_session_with_events(session, count=3)
    session.commit()
    with client.stream(
        "GET",
        f"/api/v1/ai/sessions/{ai_session.id}/stream?last_event_sequence=1&once=true",
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "id: 2" in body
    assert "id: 3" in body
    assert "id: 1\n" not in body
    assert response.headers["cache-control"] == "no-cache"
