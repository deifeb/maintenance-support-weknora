from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIModelCall,
    AIReportJob,
    AISession,
)
from app.models.enums import (
    AIModelCallStatus,
    AIReportJobStatus,
    AISessionStatus,
    CalculationStatus,
)
from app.repositories import (
    DemandCalculationRepository,
)
from app.repositories.ai_session_repository import (
    ai_session_repository,
)
from app.workers.ai_executor import (
    ai_task_executor,
)

_REPORT_INTERRUPTED_STATUSES = {
    AIReportJobStatus.BUILDING_SKELETON,
    AIReportJobStatus.GENERATING_SECTIONS,
    AIReportJobStatus.VALIDATING_NUMBERS,
    AIReportJobStatus.VALIDATING_CITATIONS,
}


def recover_interrupted_ai_tasks(
    session: Session,
) -> int:
    changed = 0
    sessions_with_events: list[
        tuple[
            str,
            int,
            AISessionStatus,
        ]
    ] = []

    running_sessions = list(
        session.scalars(
            select(AISession).where(
                AISession.status.in_(
                    [
                        AISessionStatus
                        .EXECUTING,
                        AISessionStatus
                        .WAITING_ASYNC_TASK,
                    ]
                )
            )
        ).all()
    )
    calculation_repository = (
        DemandCalculationRepository()
    )
    for row in running_sessions:
        if ai_task_executor.is_active(
            "session",
            row.id,
        ):
            continue
        ai_session_repository.append_event(
            session,
            row.tenant_id,
            row.id,
            "RECOVERY_STARTED",
            {
                "previous_status": (
                    row.status.value
                )
            },
            visibility="SYSTEM",
        )
        final_status = (
            AISessionStatus
            .PARTIALLY_COMPLETED
        )
        if (
            row.status
            is AISessionStatus
            .WAITING_ASYNC_TASK
            and row.active_calculation_id
        ):
            calculation = (
                calculation_repository
                .get_by_id(
                    session,
                    row.tenant_id,
                    row
                    .active_calculation_id,
                )
            )
            if (
                calculation is not None
                and calculation.status
                in {
                    CalculationStatus.PENDING,
                    CalculationStatus.RUNNING,
                }
            ):
                final_status = (
                    AISessionStatus
                    .WAITING_ASYNC_TASK
                )

        if row.status is not final_status:
            row.status = final_status
            changed += 1

        sessions_with_events.append(
            (
                row.tenant_id,
                row.id,
                final_status,
            )
        )

    pending_calls = list(
        session.scalars(
            select(AIModelCall).where(
                AIModelCall.status
                == AIModelCallStatus.PENDING
            )
        ).all()
    )
    for row in pending_calls:
        row.status = (
            AIModelCallStatus.FAILED
        )
        row.error_code = (
            "PROVIDER_CALL_INTERRUPTED"
        )
        row.error_message = (
            "The service stopped while "
            "the model call was pending"
        )
        changed += 1

    interrupted_reports = list(
        session.scalars(
            select(AIReportJob).where(
                AIReportJob.status.in_(
                    _REPORT_INTERRUPTED_STATUSES
                )
            )
        ).all()
    )
    for row in interrupted_reports:
        if ai_task_executor.is_active(
            "report",
            row.id,
        ):
            continue
        row.status = (
            AIReportJobStatus
            .PARTIALLY_COMPLETED
        )
        row.error_code = (
            "REPORT_TASK_INTERRUPTED"
        )
        row.error_message = (
            "The service stopped while "
            "the report task was running"
        )
        changed += 1

    # Persist state transitions before append_event() performs an
    # ownership lookup with populate_existing=True. Without this flush,
    # the lookup can reload the previous database value and overwrite
    # the dirty AISession.status in the identity map.
    session.flush()

    for (
        tenant_id,
        session_id,
        final_status,
    ) in sessions_with_events:
        ai_session_repository.append_event(
            session,
            tenant_id,
            session_id,
            "RECOVERY_COMPLETED",
            {
                "status": final_status.value,
                "resume_requires_actor": True,
            },
            visibility="SYSTEM",
        )
    session.commit()
    return changed
