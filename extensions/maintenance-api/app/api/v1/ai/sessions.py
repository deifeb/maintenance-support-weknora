import json
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.responses import success_response
from app.db.session import SessionLocal, get_db_session
from app.models import AIConfirmationRequest, AISessionSnapshot
from app.models.enums import AIConfirmationStatus, AISessionStatus
from app.schemas.ai_session import AIMessageCreateRequest, AISessionCreateRequest
from app.services.ai_confirmation_service import ai_confirmation_service
from app.services.ai_event_service import ai_event_service
from app.services.ai_orchestration_service import ai_orchestration_service
from app.services.ai_session_service import ai_session_service

router = APIRouter()


def _session_data(row, *, snapshot=None, confirmation=None):
    data = {
        "id": row.id,
        "session_code": row.session_code,
        "title": row.title,
        "status": row.status.value,
        "current_intent": row.current_intent,
        "sensitivity_level": row.sensitivity_level,
        "execution_mode": row.execution_mode.value,
        "active_scenario_version_id": row.active_scenario_version_id,
        "active_calculation_id": row.active_calculation_id,
        "active_report_job_id": row.active_report_job_id,
        "last_event_sequence": row.last_event_sequence,
        "summary": row.summary,
    }
    if snapshot is not None:
        data["latest_snapshot"] = {
            "snapshot_version": snapshot.snapshot_version,
            "current_state": snapshot.current_state,
            "scenario_draft": snapshot.scenario_draft_json or {},
        }
    if confirmation is not None:
        data["pending_confirmation"] = {
            "id": confirmation.id,
            "operation_name": confirmation.operation_name,
            "confirmation_level": confirmation.confirmation_level.value,
            "input_digest": confirmation.input_digest,
            "expires_at": confirmation.expires_at,
        }
    return data


def _load_detail(session: Session, session_id: int):
    row = ai_session_service.get(session, session_id)
    snapshot = session.scalar(
        select(AISessionSnapshot)
        .where(AISessionSnapshot.session_id == session_id)
        .order_by(AISessionSnapshot.snapshot_version.desc())
    )
    confirmation = session.scalar(
        select(AIConfirmationRequest)
        .where(
            AIConfirmationRequest.session_id == session_id,
            AIConfirmationRequest.status == AIConfirmationStatus.PENDING,
        )
        .order_by(AIConfirmationRequest.id.desc())
    )
    return row, snapshot, confirmation


@router.post("/sessions")
def create_session(
    payload: AISessionCreateRequest,
    session: Session = Depends(get_db_session),
):
    row = ai_session_service.create(
        session,
        title=payload.title,
        sensitivity_level=payload.sensitivity_level,
        created_by="api-user",
        active_scenario_version_id=payload.active_scenario_version_id,
    )
    ai_session_service.append_event(
        session,
        row.id,
        "SESSION_STARTED",
        {"session_code": row.session_code},
    )
    session.refresh(row)
    return success_response(_session_data(row))


@router.get("/sessions/{session_id}")
def get_session(session_id: int, session: Session = Depends(get_db_session)):
    row, snapshot, confirmation = _load_detail(session, session_id)
    return success_response(_session_data(row, snapshot=snapshot, confirmation=confirmation))


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: int,
    payload: AIMessageCreateRequest,
    session: Session = Depends(get_db_session),
):
    result = await ai_orchestration_service.handle_message(
        session,
        session_id,
        payload.content,
        user_id="api-user",
        permissions={
            "CALCULATION_EXECUTE",
            "CALCULATION_CANCEL",
            "SCENARIO_DRAFT",
            "REPORT_CREATE",
            "REVIEW_EXECUTE",
        },
        model_override=payload.model_override,
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/sessions/{session_id}/events")
def list_events(
    session_id: int,
    after_sequence: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
):
    ai_session_service.get(session, session_id)
    events = ai_event_service.list(session, session_id, after_sequence=after_sequence)
    return success_response(
        [
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "payload": event.payload_json,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    )


@router.get("/sessions/{session_id}/stream")
def stream_events(
    session_id: int,
    last_event_sequence: int = Query(default=0, ge=0),
    once: bool = Query(default=False),
    session: Session = Depends(get_db_session),
):
    ai_session_service.get(session, session_id)
    settings = get_settings()

    def format_event(event) -> str:
        payload = json.dumps(
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "payload": event.payload_json,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"

    def generate():
        sequence = last_event_sequence
        idle_started = time.monotonic()
        while True:
            stream_session = SessionLocal()
            try:
                events = ai_event_service.list(
                    stream_session,
                    session_id,
                    after_sequence=sequence,
                )
            finally:
                stream_session.close()
            for event in events:
                sequence = event.sequence
                idle_started = time.monotonic()
                yield format_event(event)
            if once:
                break
            if time.monotonic() - idle_started >= settings.ai_sse_heartbeat_seconds:
                yield "event: heartbeat\ndata: {}\n\n"
                idle_started = time.monotonic()
            time.sleep(settings.ai_sse_poll_interval_seconds)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: int,
    session: Session = Depends(get_db_session),
):
    result = await ai_orchestration_service.execute_plan(
        session,
        session_id,
        user_id="api-user",
        permissions={
            "CALCULATION_EXECUTE",
            "CALCULATION_CANCEL",
            "SCENARIO_DRAFT",
            "REPORT_CREATE",
            "REVIEW_EXECUTE",
        },
    )
    return success_response(result.model_dump(mode="json"), message="session resumed")


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: int, session: Session = Depends(get_db_session)):
    row = ai_session_service.get(session, session_id)
    if row.active_calculation_id is not None or row.active_report_job_id is not None:
        confirmation, token = ai_confirmation_service.create(
            session,
            session_id=session_id,
            operation_name="cancel_active_ai_task",
            confirmation_level="SECONDARY",
            input_payload={
                "active_calculation_id": row.active_calculation_id,
                "active_report_job_id": row.active_report_job_id,
            },
            risk_level="HIGH",
        )
        row.status = AISessionStatus.CONFIRMATION_REQUIRED
        session.commit()
        return success_response(
            {
                "status": row.status.value,
                "confirmation_id": confirmation.id,
                "confirmation_token": token,
                "input_digest": confirmation.input_digest,
            }
        )
    row.status = AISessionStatus.CANCELLED
    session.commit()
    session.refresh(row)
    ai_session_service.append_event(session, session_id, "CANCELLED", {})
    return success_response(_session_data(row))
