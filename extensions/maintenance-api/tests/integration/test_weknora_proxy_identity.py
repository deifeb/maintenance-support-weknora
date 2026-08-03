from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import jwt
import pytest
from app.models import EquipmentModel
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _canonical_payload(
    **overrides: object,
) -> dict[str, object]:
    now = int(datetime.now(timezone.utc).timestamp())
    payload: dict[str, object] = {
        "sub": "proxy-user",
        "tenant_id": "tenant-a",
        "roles": ["contributor"],
        "aud": ["maintenance-api"],
        "iss": "weknora",
        "iat": now,
        "exp": now + 180,
        "jti": str(uuid.uuid4()),
        "request_id": "proxy-request",
    }
    payload.update(overrides)
    return payload


def _encoded_headers(
    payload: dict[str, object],
    *,
    algorithm: str = "HS256",
) -> dict[str, str]:
    token = jwt.encode(
        payload,
        os.environ["INTERNAL_JWT_SECRET"],
        algorithm=algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _error_code(response) -> str:
    body = response.json()
    if "detail" in body:
        return body["detail"]["code"]
    return body["error"]["code"]


def test_proxy_identity_ignores_spoofed_tenant_inputs(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="user-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-a",
    )
    headers["X-Tenant-ID"] = "tenant-b"
    headers["X-Request-ID"] = "spoofed-browser-request"

    response = client.post(
        (
            "/api/v1/master-data/equipment-models"
            "?tenant_id=tenant-b"
        ),
        headers=headers,
        json={
            "code": "EQ-PROXY",
            "name": "Proxy identity",
            "tenant_id": "tenant-b",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["meta"] == {
        "tenant_id": "tenant-a",
        "request_id": "request-a",
        "version": 1,
    }

    row = session.scalar(
        select(EquipmentModel).where(
            EquipmentModel.code == "EQ-PROXY"
        )
    )
    assert row is not None
    assert row.tenant_id == "tenant-a"


def test_missing_internal_token_is_rejected(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/master-data/equipment-models"
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert _error_code(response) == "INTERNAL_TOKEN_INVALID"


def test_viewer_can_read_but_cannot_create(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="viewer-a",
        role=MaintenanceRole.VIEWER,
        request_id="viewer-request",
    )

    listed = client.get(
        "/api/v1/master-data/equipment-models",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["meta"] == {
        "tenant_id": "tenant-a",
        "request_id": "viewer-request",
        "version": None,
    }

    created = client.post(
        "/api/v1/master-data/equipment-models",
        headers=headers,
        json={
            "code": "EQ-VIEWER-DENIED",
            "name": "Viewer denied",
        },
    )
    assert created.status_code == 403
    assert _error_code(created) == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_other_tenant_cannot_read_update_or_delete_row(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    created = client.post(
        "/api/v1/master-data/equipment-models",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="creator-a",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        json={
            "code": "EQ-TENANT-BOUNDARY",
            "name": "Tenant boundary",
        },
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["data"]["id"]

    read_response = client.get(
        (
            "/api/v1/master-data/equipment-models/"
            f"{identifier}"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-b",
            user_id="viewer-b",
            role=MaintenanceRole.VIEWER,
        ),
    )
    assert read_response.status_code == 404
    assert _error_code(read_response) == "RESOURCE_NOT_FOUND"

    update_response = client.put(
        (
            "/api/v1/master-data/equipment-models/"
            f"{identifier}"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-b",
            user_id="contributor-b",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        json={"name": "Cross-tenant update"},
    )
    assert update_response.status_code == 404
    assert _error_code(update_response) == (
        "RESOURCE_NOT_FOUND"
    )

    delete_response = client.delete(
        (
            "/api/v1/master-data/equipment-models/"
            f"{identifier}"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-b",
            user_id="admin-b",
            role=MaintenanceRole.ADMIN,
        ),
    )
    assert delete_response.status_code == 404
    assert _error_code(delete_response) == (
        "RESOURCE_NOT_FOUND"
    )

    owner_read = client.get(
        (
            "/api/v1/master-data/equipment-models/"
            f"{identifier}"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="viewer-a",
            role=MaintenanceRole.VIEWER,
        ),
    )
    assert owner_read.status_code == 200
    assert owner_read.json()["data"]["name"] == (
        "Tenant boundary"
    )


def test_unknown_role_token_is_rejected(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/master-data/equipment-models",
        headers=_encoded_headers(
            _canonical_payload(roles=["operator"])
        ),
    )

    assert response.status_code == 401
    assert _error_code(response) == "INTERNAL_TOKEN_INVALID"


def _untrusted_token_case(
    scenario: str,
) -> tuple[dict[str, object], str]:
    if scenario == "wrong-issuer":
        return {"iss": "other-issuer"}, "HS256"
    if scenario == "wrong-audience":
        return {"aud": ["other-audience"]}, "HS256"
    if scenario == "wrong-algorithm":
        return {}, "HS384"

    now = int(datetime.now(timezone.utc).timestamp())
    if scenario == "expired":
        return {
            "iat": now - 190,
            "exp": now - 10,
        }, "HS256"
    if scenario == "future-iat":
        return {
            "iat": now + 30,
            "exp": now + 210,
        }, "HS256"
    if scenario == "lifetime-too-long":
        return {
            "iat": now,
            "exp": now + 181,
        }, "HS256"

    raise AssertionError(f"unknown token scenario: {scenario}")


@pytest.mark.parametrize(
    "scenario",
    [
        "wrong-issuer",
        "wrong-audience",
        "wrong-algorithm",
        "expired",
        "future-iat",
        "lifetime-too-long",
    ],
)
def test_untrusted_proxy_tokens_are_rejected(
    client: TestClient,
    scenario: str,
) -> None:
    payload_overrides, algorithm = _untrusted_token_case(
        scenario
    )
    response = client.get(
        "/api/v1/master-data/equipment-models",
        headers=_encoded_headers(
            _canonical_payload(**payload_overrides),
            algorithm=algorithm,
        ),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert _error_code(response) == "INTERNAL_TOKEN_INVALID"
