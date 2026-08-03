from __future__ import annotations

from collections.abc import Callable

from app.models import (
    AIConfirmationRequest,
    AISession,
)
from app.models.enums import (
    AIConfirmationLevel,
    AISessionStatus,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.ai.factories import create_ai_session


def _confirmation_count(
    session: Session,
    session_id: int,
) -> int:
    return int(
        session.scalar(
            select(
                func.count(
                    AIConfirmationRequest.id
                )
            ).where(
                AIConfirmationRequest.session_id
                == session_id
            )
        )
        or 0
    )


def test_create_and_read_ai_session(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="session-user",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    created = client.post(
        "/api/v1/ai/sessions",
        headers=headers,
        json={
            "title": "任务需求会话",
            "sensitivity_level": "INTERNAL",
        },
    )

    assert created.status_code == 200
    session_id = created.json()["data"]["id"]
    read = client.get(
        f"/api/v1/ai/sessions/{session_id}",
        headers=headers,
    )

    assert read.status_code == 200
    assert (
        read.json()["data"]["title"]
        == "任务需求会话"
    )


def test_contributor_active_cancel_requires_admin(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.EXECUTING,
    )
    row.active_report_job_id = 44
    session.commit()

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="contributor-a",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_denied_active_cancel_does_not_mutate_or_create_confirmation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.EXECUTING,
    )
    row.active_report_job_id = 45
    session.commit()
    before = _confirmation_count(
        session,
        row.id,
    )

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="contributor-b",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
    )

    session.expire_all()
    persisted = session.get(
        AISession,
        row.id,
    )
    after = _confirmation_count(
        session,
        row.id,
    )

    assert persisted is not None
    assert (
        persisted.status
        is AISessionStatus.EXECUTING
    )
    assert (
        persisted.active_report_job_id
        == 45
    )
    assert after == before
    assert response.status_code == 403


def test_admin_active_cancel_creates_secondary_confirmation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.EXECUTING,
    )
    row.active_report_job_id = 46
    session.commit()

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="admin-a",
            role=MaintenanceRole.ADMIN,
        ),
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["status"]
        == "CONFIRMATION_REQUIRED"
    )
    confirmation_id = response.json()[
        "data"
    ]["confirmation_id"]
    confirmation = session.get(
        AIConfirmationRequest,
        confirmation_id,
    )
    assert confirmation is not None
    assert (
        confirmation.tenant_id
        == "tenant-a"
    )
    assert (
        confirmation.confirmation_level
        is AIConfirmationLevel.SECONDARY
    )
    session.refresh(row)
    assert (
        row.status
        is AISessionStatus
        .CONFIRMATION_REQUIRED
    )


def test_contributor_can_cancel_session_without_active_task(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.CREATED,
    )
    session.commit()

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="contributor-c",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["status"]
        == "CANCELLED"
    )
