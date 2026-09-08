from __future__ import annotations

from collections.abc import Callable

from app.security.actor import (
    ActorContext,
    MaintenanceRole,
)
from app.services.ai_confirmation_service import (
    ai_confirmation_service,
)
from app.services.ai_session_service import (
    ai_session_service,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _create_confirmation(
    session: Session,
    actor: ActorContext,
    *,
    operation_name: str,
):
    ai_session = ai_session_service.create(
        session,
        actor,
        title="confirmation test",
        sensitivity_level="INTERNAL",
    )
    confirmation, token = (
        ai_confirmation_service.create(
            session,
            actor,
            session_id=ai_session.id,
            operation_name=operation_name,
            confirmation_level="EXPLICIT",
            input_payload={
                "scenario_version_id": 1
            },
            risk_level="HIGH",
        )
    )
    session.commit()
    return ai_session, confirmation, token


def test_confirmation_approval_uses_token_and_digest(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
    monkeypatch,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="admin-token",
        role=MaintenanceRole.ADMIN,
    )
    _, confirmation, token = (
        _create_confirmation(
            session,
            actor,
            operation_name=(
                "start_demand_calculation"
            ),
        )
    )
    monkeypatch.setattr(
        (
            "app.api.v1.ai.confirmations."
            "submit_ai_session"
        ),
        lambda session_id, forwarded_actor: (
            object()
        ),
    )

    response = client.post(
        (
            "/api/v1/ai/confirmations/"
            f"{confirmation.id}/approve"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="admin-token",
            role=MaintenanceRole.ADMIN,
        ),
        json={
            "confirmation_token": token,
            "expected_input_digest": (
                confirmation.input_digest
            ),
            "comment": "确认执行",
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["status"]
        == "APPROVED"
    )
    session.refresh(confirmation)
    assert (
        confirmation.resolved_by
        == "admin-token"
    )


def test_admin_confirmation_approval_forwards_authenticated_actor(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
    monkeypatch,
) -> None:
    setup_actor = actor_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role=MaintenanceRole.ADMIN,
        request_id="setup-request",
    )
    ai_session, confirmation, token = (
        _create_confirmation(
            session,
            setup_actor,
            operation_name=(
                "start_demand_calculation"
            ),
        )
    )
    captured: dict[str, object] = {}

    def fake_submit(
        session_id: int,
        actor: ActorContext,
    ) -> object:
        captured["session_id"] = session_id
        captured["actor"] = actor
        return object()

    monkeypatch.setattr(
        (
            "app.api.v1.ai.confirmations."
            "submit_ai_session"
        ),
        fake_submit,
    )

    response = client.post(
        (
            "/api/v1/ai/confirmations/"
            f"{confirmation.id}/approve"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="admin-a",
            role=MaintenanceRole.ADMIN,
            request_id="approve-request",
        ),
        json={
            "confirmation_token": token,
            "expected_input_digest": (
                confirmation.input_digest
            ),
            "comment": "approved",
        },
    )

    assert response.status_code == 200
    assert (
        captured["session_id"]
        == ai_session.id
    )
    forwarded = captured["actor"]
    assert isinstance(
        forwarded,
        ActorContext,
    )
    assert forwarded.tenant_id == "tenant-a"
    assert forwarded.user_id == "admin-a"
    assert (
        forwarded.role
        is MaintenanceRole.ADMIN
    )
    assert (
        forwarded.request_id
        == "approve-request"
    )
    session.refresh(confirmation)
    assert (
        confirmation.resolved_by
        == "admin-a"
    )


def test_foreign_admin_cannot_resolve_confirmation(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    foreign_actor = actor_context(
        tenant_id="tenant-b",
        user_id="foreign-admin",
        role=MaintenanceRole.ADMIN,
    )
    _, confirmation, token = (
        _create_confirmation(
            session,
            foreign_actor,
            operation_name=(
                "foreign-operation"
            ),
        )
    )

    response = client.post(
        (
            "/api/v1/ai/confirmations/"
            f"{confirmation.id}/approve"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="local-admin",
            role=MaintenanceRole.ADMIN,
        ),
        json={
            "confirmation_token": token,
            "expected_input_digest": (
                confirmation.input_digest
            ),
        },
    )

    assert response.status_code == 404
