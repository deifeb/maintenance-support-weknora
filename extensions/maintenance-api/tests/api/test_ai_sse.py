from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.ai.factories import (
    create_ai_session_with_events,
)


def test_sse_stream_resumes_after_last_event(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    ai_session = create_ai_session_with_events(
        session,
        tenant_id="tenant-a",
        count=3,
    )
    session.commit()
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="sse-viewer",
        role=MaintenanceRole.VIEWER,
        request_id="sse-request",
    )

    with client.stream(
        "GET",
        (
            "/api/v1/ai/sessions/"
            f"{ai_session.id}/stream"
            "?last_event_sequence=1"
            "&once=true"
        ),
        headers=headers,
    ) as response:
        body = "".join(
            response.iter_text()
        )

    assert response.status_code == 200
    assert "id: 2" in body
    assert "id: 3" in body
    assert "id: 1\n" not in body
    assert (
        response.headers["cache-control"]
        == "no-cache"
    )
    assert (
        response.headers["x-request-id"]
        == "sse-request"
    )


def test_foreign_tenant_sse_is_404_before_stream(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    ai_session = create_ai_session_with_events(
        session,
        tenant_id="tenant-a",
        count=1,
    )
    session.commit()
    headers = internal_auth_headers(
        tenant_id="tenant-b",
        user_id="foreign-sse-viewer",
        role=MaintenanceRole.VIEWER,
    )

    with client.stream(
        "GET",
        (
            "/api/v1/ai/sessions/"
            f"{ai_session.id}/stream"
            "?once=true"
        ),
        headers=headers,
    ) as response:
        assert response.status_code == 404
