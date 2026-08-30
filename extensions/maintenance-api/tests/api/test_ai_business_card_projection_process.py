from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


def test_process_persists_exact_turn_scenario_business_ref(
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
            "title": "Process projection integration",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    processed = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        headers=contributor_headers,
        json={
            "content": "10台装备执行30天任务，保障率95%",
        },
    )
    assert processed.status_code == 200
    trigger_message_id = (
        processed.json()["data"]["trigger_message_id"]
    )

    process_projection = (
        processed.json()["data"]["maintenance_projection"]
    )
    assert process_projection["schema_version"] == "1.0"
    assert process_projection["source"] == {
        "kind": "AI_MESSAGE_TRIGGER",
        "session_id": session_id,
        "message_id": trigger_message_id,
    }
    assert [
        card["type"]
        for card in process_projection["cards"]
    ] == ["SCENARIO_DRAFT"]

    projection = client.get(
        (
            f"/api/v1/ai/sessions/{session_id}"
            f"/messages/{trigger_message_id}"
            "/business-cards"
        ),
        headers=viewer_headers,
    )

    assert projection.status_code == 200
    cards = projection.json()["data"]["cards"]
    assert [card["type"] for card in cards] == [
        "SCENARIO_DRAFT"
    ]
    assert cards[0]["target"]["object_type"] == (
        "AI_SESSION_SNAPSHOT"
    )
    assert cards[0]["target"]["object_id"] == session_id
