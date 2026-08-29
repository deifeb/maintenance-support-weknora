from __future__ import annotations

from collections.abc import Callable

from app.models import AIMessage
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{tenant_id}-{role.value.lower()}",
        role=role,
    )


def _create_session(
    client: TestClient,
    headers: dict[str, str],
    title: str,
) -> int:
    response = client.post(
        "/api/v1/ai/sessions",
        headers=headers,
        json={"title": title, "sensitivity_level": "INTERNAL"},
    )
    assert response.status_code == 200
    return int(response.json()["data"]["id"])


def _post_message(
    client: TestClient,
    headers: dict[str, str],
    session_id: int,
    content: str,
) -> dict:
    response = client.post(
        f"/api/v1/ai/sessions/{session_id}/messages",
        headers=headers,
        json={"content": content},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_process_response_surfaces_exact_persisted_trigger_and_projection(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    contributor = _headers(internal_auth_headers)
    session_id = _create_session(client, contributor, "projection source")

    data = _post_message(
        client,
        contributor,
        session_id,
        "10台装备执行30天任务，保障率95%",
    )

    trigger_message_id = int(data["trigger_message_id"])
    persisted = session.get(AIMessage, trigger_message_id)
    assert persisted is not None
    assert persisted.session_id == session_id
    assert persisted.tenant_id == "tenant-a"
    assert persisted.content == "10台装备执行30天任务，保障率95%"

    projection = data["maintenance_projection"]
    assert projection["schema_version"] == "1.0"
    assert projection["source"] == {
        "kind": "AI_MESSAGE_TRIGGER",
        "session_id": session_id,
        "message_id": trigger_message_id,
    }
    assert [card["type"] for card in projection["cards"]] == ["SCENARIO_DRAFT"]


def test_exact_turn_recovery_replays_first_snapshot_without_latest_fallback(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    contributor = _headers(internal_auth_headers)
    viewer = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
    )
    session_id = _create_session(client, contributor, "exact replay")

    first = _post_message(
        client,
        contributor,
        session_id,
        "10台装备执行30天任务，保障率95%",
    )
    second = _post_message(
        client,
        contributor,
        session_id,
        "任务周期调整为45天",
    )

    first_id = int(first["trigger_message_id"])
    second_id = int(second["trigger_message_id"])
    first_version = first["maintenance_projection"]["cards"][0]["target"][
        "observed_version"
    ]
    second_version = second["maintenance_projection"]["cards"][0]["target"][
        "observed_version"
    ]
    assert second_id != first_id
    assert second_version > first_version

    recovered = client.get(
        (
            f"/api/v1/ai/sessions/{session_id}/messages/"
            f"{first_id}/business-cards"
        ),
        headers=viewer,
    )
    assert recovered.status_code == 200
    payload = recovered.json()["data"]
    assert payload["source"]["message_id"] == first_id
    assert payload["cards"][0]["target"]["observed_version"] == first_version
    assert payload["cards"] == first["maintenance_projection"]["cards"]


def test_exact_turn_recovery_is_non_enumerating_for_tenant_or_session_mismatch(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    tenant_a = _headers(internal_auth_headers)
    viewer_a = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
    )
    viewer_b = _headers(
        internal_auth_headers,
        tenant_id="tenant-b",
        role=MaintenanceRole.VIEWER,
    )
    session_a = _create_session(client, tenant_a, "source session")
    session_other = _create_session(client, tenant_a, "other session")
    data = _post_message(
        client,
        tenant_a,
        session_a,
        "10台装备执行30天任务，保障率95%",
    )
    trigger_id = int(data["trigger_message_id"])

    foreign = client.get(
        (
            f"/api/v1/ai/sessions/{session_a}/messages/"
            f"{trigger_id}/business-cards"
        ),
        headers=viewer_b,
    )
    mismatch = client.get(
        (
            f"/api/v1/ai/sessions/{session_other}/messages/"
            f"{trigger_id}/business-cards"
        ),
        headers=viewer_a,
    )
    missing = client.get(
        (
            f"/api/v1/ai/sessions/{session_a}/messages/"
            "999999999/business-cards"
        ),
        headers=viewer_a,
    )

    assert foreign.status_code == 404
    assert mismatch.status_code == 404
    assert missing.status_code == 404
    assert foreign.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert mismatch.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_not_applicable_exact_turn_returns_empty_cards(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    contributor = _headers(internal_auth_headers)
    viewer = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
    )
    session_id = _create_session(client, contributor, "not applicable")
    data = _post_message(
        client,
        contributor,
        session_id,
        "请执行 SQL 查询",
    )

    trigger_id = int(data["trigger_message_id"])
    assert data["maintenance_projection"]["cards"] == []

    recovered = client.get(
        (
            f"/api/v1/ai/sessions/{session_id}/messages/"
            f"{trigger_id}/business-cards"
        ),
        headers=viewer,
    )
    assert recovered.status_code == 200
    assert recovered.json()["data"]["cards"] == []
