from __future__ import annotations

from collections.abc import Callable

from app.models.enums import AISessionStatus
from app.security.actor import ActorContext, MaintenanceRole
from app.services.ai_session_service import ai_session_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_exact_turn_business_cards_use_trigger_refs_not_newer_message(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="projection-owner",
    )
    ai_session = ai_session_service.create(
        session,
        actor,
        title="Exact scenario projection",
        sensitivity_level="INTERNAL",
    )
    ai_session.status = AISessionStatus.UNDERSTANDING
    session.commit()

    ai_session_service.create_snapshot(
        session,
        actor,
        ai_session.id,
        scenario_draft={
            "equipment_quantity": {
                "value": 10,
            }
        },
    )

    trigger_message = ai_session_service.add_message(
        session,
        actor,
        ai_session.id,
        role="USER",
        message_type="USER_TEXT",
        content="build this exact scenario card",
        structured_content={
            "maintenance_business_refs": [
                {
                    "type": "SCENARIO_DRAFT",
                    "object_id": ai_session.id,
                }
            ]
        },
    )

    ai_session_service.add_message(
        session,
        actor,
        ai_session.id,
        role="USER",
        message_type="USER_TEXT",
        content="newer message without card refs",
    )

    viewer_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="projection-viewer",
        role=MaintenanceRole.VIEWER,
    )

    response = client.get(
        (
            f"/api/v1/ai/sessions/{ai_session.id}"
            f"/messages/{trigger_message.id}"
            "/business-cards"
        ),
        headers=viewer_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["source"] == {
        "kind": "AI_MESSAGE_TRIGGER",
        "session_id": ai_session.id,
        "message_id": trigger_message.id,
    }
    assert [
        card["type"]
        for card in data["cards"]
    ] == ["SCENARIO_DRAFT"]

    card = data["cards"][0]
    assert card["target"]["object_type"] == (
        "AI_SESSION_SNAPSHOT"
    )
    assert card["target"]["object_id"] == ai_session.id
    assert card["target"]["observed_version"] == 1
