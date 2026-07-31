from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{role.value}-{tenant_id}",
        role=role,
    )


def test_contributor_creates_and_viewer_reads_manual_draft(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    contributor = _headers(internal_auth_headers)
    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=contributor,
        json={
            "title": "Fleet readiness",
            "sensitivity_level": "INTERNAL",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["data"]["origin"] == "MANUAL"
    assert body["data"]["version"] == 1
    assert body["meta"]["version"] == 1
    assert "tenant_id" not in body["data"]["draft"]

    read = client.get(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{body['data']['session_id']}"
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
        ),
    )

    assert read.status_code == 200
    assert read.json()["data"] == body["data"]


def test_viewer_cannot_create_draft(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    viewer = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
    )

    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=viewer,
        json={"title": "Denied"},
    )

    assert created.status_code == 403
    assert (
        created.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_viewer_cannot_save_draft(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    contributor = _headers(internal_auth_headers)
    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=contributor,
        json={"title": "Protected draft"},
    ).json()["data"]

    response = client.put(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}"
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
        ),
        json={
            "expected_version": created["version"],
            "draft": created["draft"],
        },
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_contributor_validates_with_server_evaluation(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = _headers(internal_auth_headers)
    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=headers,
        json={"title": "Validation draft"},
    ).json()["data"]

    response = client.post(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}/validate"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["data"]["blocking_fields"]
        == created["blocking_fields"]
    )
    assert body["meta"]["version"] == 1


def test_save_conflict_returns_stable_server_version(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = _headers(internal_auth_headers)
    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=headers,
        json={"title": "Conflict draft"},
    ).json()["data"]
    draft = created["draft"]
    draft["fields"]["mission_code"] = {
        "value": "MISSION-30D",
        "source": "USER_INPUT",
        "confidence": None,
        "risk": "LOW",
        "confirmed": True,
        "evidence_refs": [],
    }
    first = client.put(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}"
        ),
        headers=headers,
        json={
            "expected_version": 1,
            "draft": draft,
        },
    )
    assert first.status_code == 200

    conflict = client.put(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}"
        ),
        headers=headers,
        json={
            "expected_version": 1,
            "draft": draft,
        },
    )

    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "SCENARIO_DRAFT_VERSION_CONFLICT"
    assert error["request_id"]
    assert error["details"]["actual_version"] == 2
    assert error["details"]["retryable"] is False


def test_foreign_tenant_draft_returns_not_found(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    created = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=_headers(
            internal_auth_headers,
            tenant_id="tenant-b",
        ),
        json={"title": "Foreign draft"},
    ).json()["data"]

    response = client.get(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}"
        ),
        headers=_headers(internal_auth_headers),
    )

    assert response.status_code == 404
