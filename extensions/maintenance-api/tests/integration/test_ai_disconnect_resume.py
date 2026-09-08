from tests.ai.factories import create_ai_session_with_events


def test_sse_disconnect_and_resume_returns_only_missing_events(
    authenticated_client,
    session,
) -> None:
    ai_session = create_ai_session_with_events(
        session,
        count=2,
        tenant_id="tenant-a",
    )
    session.commit()

    with authenticated_client.stream(
        "GET",
        (
            f"/api/v1/ai/sessions/{ai_session.id}/stream"
            "?last_event_sequence=0&once=true"
        ),
    ) as first:
        first_body = "".join(first.iter_text())
    assert "id: 1" in first_body
    assert "id: 2" in first_body

    authenticated_client.post(
        f"/api/v1/ai/sessions/{ai_session.id}/messages",
        json={
            "content": (
                "示例装备1采用V1构型，10台执行30天任务，"
                "保障率95%"
            )
        },
    )
    with authenticated_client.stream(
        "GET",
        (
            f"/api/v1/ai/sessions/{ai_session.id}/stream"
            "?last_event_sequence=2&once=true"
        ),
    ) as resumed:
        resumed_body = "".join(resumed.iter_text())
    assert "id: 1\n" not in resumed_body
    assert "id: 2\n" not in resumed_body
    assert "event: FALLBACK_TRIGGERED" in resumed_body
    assert "event: SCENARIO_DRAFT_UPDATED" in resumed_body
