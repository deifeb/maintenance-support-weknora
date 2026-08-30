from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


def test_exact_turn_business_cards_rejects_session_message_mismatch(
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

    source = client.post(
        "/api/v1/ai/sessions",
        headers=contributor_headers,
        json={
            "title": "Projection source",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert source.status_code == 200
    source_session_id = source.json()["data"]["id"]

    other = client.post(
        "/api/v1/ai/sessions",
        headers=contributor_headers,
        json={
            "title": "Projection other",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert other.status_code == 200
    other_session_id = other.json()["data"]["id"]

    processed = client.post(
        f"/api/v1/ai/sessions/{source_session_id}/messages",
        headers=contributor_headers,
        json={"content": "sql"},
    )
    assert processed.status_code == 200
    trigger_message_id = (
        processed.json()["data"]["trigger_message_id"]
    )

    response = client.get(
        (
            f"/api/v1/ai/sessions/{other_session_id}"
            f"/messages/{trigger_message_id}"
            "/business-cards"
        ),
        headers=viewer_headers,
    )

    assert response.status_code == 404


def test_exact_turn_business_cards_rejects_foreign_tenant(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    local_contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="projection-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_viewer_headers = internal_auth_headers(
        tenant_id="tenant-b",
        user_id="foreign-projection-viewer",
        role=MaintenanceRole.VIEWER,
    )

    created = client.post(
        "/api/v1/ai/sessions",
        headers=local_contributor_headers,
        json={
            "title": "Foreign projection boundary",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    processed = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        headers=local_contributor_headers,
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
        headers=foreign_viewer_headers,
    )

    assert response.status_code == 404
