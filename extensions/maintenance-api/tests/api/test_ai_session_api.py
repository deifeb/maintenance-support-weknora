from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


def test_session_message_and_events_flow(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="session-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    viewer_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="session-viewer",
        role=MaintenanceRole.VIEWER,
    )

    created = client.post(
        "/api/v1/ai/sessions",
        headers=contributor_headers,
        json={
            "title": "需求分析",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    message = client.post(
        (
            "/api/v1/ai/sessions/"
            f"{session_id}/messages"
        ),
        headers=contributor_headers,
        json={
            "content": (
                "10台装备执行30天任务，"
                "保障率95%"
            )
        },
    )
    assert message.status_code == 200
    data = message.json()["data"]
    assert (
        data["scenario_draft"][
            "equipment_quantity"
        ]["value"]
        == 10
    )

    events = client.get(
        (
            "/api/v1/ai/sessions/"
            f"{session_id}/events"
        ),
        headers=viewer_headers,
    )
    assert events.status_code == 200
    assert (
        events.json()["data"][0]["sequence"]
        == 1
    )


def test_foreign_tenant_cannot_read_session_or_events(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    local_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="session-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_headers = internal_auth_headers(
        tenant_id="tenant-b",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    created = client.post(
        "/api/v1/ai/sessions",
        headers=local_headers,
        json={"title": "tenant boundary"},
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    read = client.get(
        f"/api/v1/ai/sessions/{session_id}",
        headers=foreign_headers,
    )
    events = client.get(
        (
            "/api/v1/ai/sessions/"
            f"{session_id}/events"
        ),
        headers=foreign_headers,
    )

    assert read.status_code == 404
    assert events.status_code == 404
