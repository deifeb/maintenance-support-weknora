from __future__ import annotations

from collections.abc import Callable

from app.models import AIModelCall
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_confidential_session_cannot_override_to_remote_model(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="sensitive-user",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    created = client.post(
        "/api/v1/ai/sessions",
        headers=headers,
        json={
            "title": "敏感任务",
            "sensitivity_level": (
                "CONFIDENTIAL"
            ),
        },
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["id"]

    response = client.post(
        (
            "/api/v1/ai/sessions/"
            f"{session_id}/messages"
        ),
        headers=headers,
        json={
            "content": "分析任务",
            "model_override": (
                "remote-strong"
            ),
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "SENSITIVE_REMOTE_CALL_BLOCKED"
    )
    assert (
        session.scalar(
            select(
                func.count(AIModelCall.id)
            )
        )
        == 0
    )
