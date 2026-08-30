from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


def test_exact_turn_business_cards_returns_empty_for_not_applicable_turn(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="projection-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    viewer_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="projection-viewer",
        role=MaintenanceRole.VIEWER,
    )

    created = client.post(
        "/api/v1/ai/sessions",
        headers=contributor_headers,
        json={
            "title": "Exact turn projection",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    processed = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        headers=contributor_headers,
        json={"content": "sql"},
    )
    assert processed.status_code == 200
    trigger_message_id = (
        processed.json()["data"]["trigger_message_id"]
    )

    response = client.get(
        (
            f"/api/v1/ai/sessions/{session_id}"
            f"/messages/{trigger_message_id}"
            "/business-cards"
        ),
        headers=viewer_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["schema_version"] == "1.0"
    assert data["source"] == {
        "kind": "AI_MESSAGE_TRIGGER",
        "session_id": session_id,
        "message_id": trigger_message_id,
    }
    assert data["cards"] == []
