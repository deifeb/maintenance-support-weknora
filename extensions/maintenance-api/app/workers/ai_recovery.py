from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIModelCall, AIReportJob, AISession, DemandCalculation
from app.models.enums import (
    AIModelCallStatus,
    AIReportJobStatus,
    AISessionStatus,
    CalculationStatus,
)
from app.repositories.ai_session_repository import ai_session_repository
from app.workers.ai_executor import ai_task_executor, submit_ai_session

_REPORT_INTERRUPTED_STATUSES = {
    AIReportJobStatus.BUILDING_SKELETON,
    AIReportJobStatus.GENERATING_SECTIONS,
    AIReportJobStatus.VALIDATING_NUMBERS,
    AIReportJobStatus.VALIDATING_CITATIONS,
}


def recover_interrupted_ai_tasks(session: Session) -> int:
    changed = 0
    resume_ids: list[int] = []
    sessions_with_events: list[int] = []

    running_sessions = list(
        session.scalars(
            select(AISession).where(
                AISession.status.in_(
                    [AISessionStatus.EXECUTING, AISessionStatus.WAITING_ASYNC_TASK]
                )
            )
        ).all()
    )
    for row in running_sessions:
        if ai_task_executor.is_active("session", row.id):
            continue
        ai_session_repository.append_event(
            session,
            row.id,
            "RECOVERY_STARTED",
            {"previous_status": row.status.value},
            visibility="SYSTEM",
        )
        sessions_with_events.append(row.id)

        if row.status is AISessionStatus.WAITING_ASYNC_TASK and row.active_calculation_id:
            calculation = session.get(DemandCalculation, row.active_calculation_id)
            if calculation is not None and calculation.status in {
                CalculationStatus.PENDING,
                CalculationStatus.RUNNING,
            }:
                continue
            if calculation is not None and calculation.status in {
                CalculationStatus.SUCCEEDED,
                CalculationStatus.PARTIAL_SUCCESS,
            }:
                row.status = AISessionStatus.PARTIALLY_COMPLETED
                resume_ids.append(row.id)
            else:
                row.status = AISessionStatus.PARTIALLY_COMPLETED
        else:
            row.status = AISessionStatus.PARTIALLY_COMPLETED
        changed += 1

    pending_calls = list(
        session.scalars(
            select(AIModelCall).where(AIModelCall.status == AIModelCallStatus.PENDING)
        ).all()
    )
    for row in pending_calls:
        row.status = AIModelCallStatus.FAILED
        row.error_code = "PROVIDER_CALL_INTERRUPTED"
        row.error_message = "The service stopped while the model call was pending"
        changed += 1

    interrupted_reports = list(
        session.scalars(
            select(AIReportJob).where(AIReportJob.status.in_(_REPORT_INTERRUPTED_STATUSES))
        ).all()
    )
    for row in interrupted_reports:
        if ai_task_executor.is_active("report", row.id):
            continue
        row.status = AIReportJobStatus.PARTIALLY_COMPLETED
        row.error_code = "REPORT_TASK_INTERRUPTED"
        row.error_message = "The service stopped while the report task was running"
        changed += 1

    for session_id in sessions_with_events:
        ai_session_repository.append_event(
            session,
            session_id,
            "RECOVERY_COMPLETED",
            {"status": AISessionStatus.PARTIALLY_COMPLETED.value},
            visibility="SYSTEM",
        )
    session.commit()

    for session_id in resume_ids:
        submit_ai_session(
            session_id,
            user_id="system-recovery",
            permissions={"AI_EXECUTE", "CALCULATION_READ"},
        )
    return changed
