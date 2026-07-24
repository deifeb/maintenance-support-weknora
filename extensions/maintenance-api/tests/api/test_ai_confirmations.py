from app.services.ai_confirmation_service import ai_confirmation_service
from tests.ai.factories import create_ai_session


def test_confirmation_approval_uses_token_and_digest(client, session) -> None:
    ai_session = create_ai_session(session)
    confirmation, token = ai_confirmation_service.create(
        session,
        session_id=ai_session.id,
        operation_name="start_demand_calculation",
        confirmation_level="EXPLICIT",
        input_payload={"scenario_version_id": 1},
        risk_level="HIGH",
    )
    response = client.post(
        f"/api/v1/ai/confirmations/{confirmation.id}/approve",
        json={
            "confirmation_token": token,
            "expected_input_digest": confirmation.input_digest,
            "comment": "确认执行",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPROVED"
