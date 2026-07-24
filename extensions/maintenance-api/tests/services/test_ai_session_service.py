from app.services.ai_confirmation_service import ai_confirmation_service
from app.services.ai_session_service import ai_session_service


def test_session_event_snapshot_and_confirmation_digest(session):
    row = ai_session_service.create(
        session, title="会话", sensitivity_level="INTERNAL", created_by="tester"
    )
    ai_session_service.add_message(
        session, row.id, role="USER", message_type="USER_TEXT", content="计算需求"
    )
    event = ai_session_service.append_event(session, row.id, "SESSION_STARTED", {})
    snap = ai_session_service.create_snapshot(session, row.id, scenario_draft={"a": 1})
    confirmation, token = ai_confirmation_service.create(
        session,
        session_id=row.id,
        operation_name="start_demand_calculation",
        confirmation_level="EXPLICIT",
        input_payload={"scenario": 1},
        risk_level="HIGH",
    )
    assert event.sequence == 1 and snap.snapshot_version == 1
    assert confirmation.confirmation_token_hash != token
    approved = ai_confirmation_service.approve(
        session, confirmation.id, token=token, expected_input_digest=confirmation.input_digest
    )
    assert approved.status.value == "APPROVED"
