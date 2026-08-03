from datetime import (
    datetime,
    timezone,
)

from app.models import (
    AIEvent,
    AIModelCall,
    AIReportJob,
    DemandCalculation,
)
from app.models.enums import (
    AIModelCallStatus,
    AIReportJobStatus,
    AIReportType,
    AISessionStatus,
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
)
from app.workers.ai_recovery import (
    recover_interrupted_ai_tasks,
)
from tests.ai.factories import (
    create_ai_session,
)


def test_recovery_marks_running_session_and_model_call_recoverable(
    session,
) -> None:
    row = create_ai_session(
        session,
        status=AISessionStatus.EXECUTING,
    )
    session.add(
        AIModelCall(
            tenant_id=row.tenant_id,
            session_id=row.id,
            request_id="interrupted-call",
            function_name=(
                "scenario_parsing"
            ),
            provider="OLLAMA",
            model="qwen",
            status=(
                AIModelCallStatus.PENDING
            ),
            prompt_name="scenario-parser",
            prompt_version="1.0",
            sensitivity_level="INTERNAL",
            input_digest="0" * 64,
        )
    )
    session.add(
        AIReportJob(
            tenant_id=row.tenant_id,
            report_code="AIR-INTERRUPTED",
            session_id=row.id,
            report_type=(
                AIReportType
                .MANAGEMENT_DECISION
            ),
            status=(
                AIReportJobStatus
                .GENERATING_SECTIONS
            ),
            title="中断报告",
        )
    )
    session.commit()

    count = recover_interrupted_ai_tasks(
        session
    )
    session.refresh(row)
    model_call = (
        session.query(AIModelCall)
        .filter_by(
            request_id=(
                "interrupted-call"
            )
        )
        .one()
    )
    report = (
        session.query(AIReportJob)
        .filter_by(
            report_code=(
                "AIR-INTERRUPTED"
            )
        )
        .one()
    )

    assert count == 3
    assert (
        row.status
        is AISessionStatus
        .PARTIALLY_COMPLETED
    )
    assert (
        model_call.status
        is AIModelCallStatus.FAILED
    )
    assert (
        model_call.error_code
        == "PROVIDER_CALL_INTERRUPTED"
    )
    assert (
        report.status
        is AIReportJobStatus
        .PARTIALLY_COMPLETED
    )
    assert [
        event.event_type
        for event
        in session.query(AIEvent).all()
    ] == [
        "RECOVERY_STARTED",
        "RECOVERY_COMPLETED",
    ]


def test_recovery_keeps_waiting_session_and_event_consistent(
    session,
) -> None:
    now = datetime.now(timezone.utc)
    calculation = DemandCalculation(
        tenant_id="tenant-a",
        calculation_code=(
            "CAL-RECOVERY-WAITING"
        ),
        calculation_name=(
            "Recovery waiting calculation"
        ),
        execution_type=(
            CalculationExecutionType
            .ASYNCHRONOUS
        ),
        requested_mode=(
            DemandExecutionMode.AUTO
        ),
        status=CalculationStatus.PENDING,
        input_snapshot_json={},
        input_snapshot_hash="1" * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(calculation)
    session.flush()
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=(
            AISessionStatus
            .WAITING_ASYNC_TASK
        ),
    )
    row.active_calculation_id = (
        calculation.id
    )
    session.commit()

    count = recover_interrupted_ai_tasks(
        session
    )
    session.refresh(row)
    events = (
        session.query(AIEvent)
        .filter_by(
            tenant_id=row.tenant_id,
            session_id=row.id,
        )
        .order_by(AIEvent.sequence)
        .all()
    )

    assert count == 0
    assert (
        row.status
        is AISessionStatus
        .WAITING_ASYNC_TASK
    )
    assert [
        event.event_type
        for event in events
    ] == [
        "RECOVERY_STARTED",
        "RECOVERY_COMPLETED",
    ]
    assert (
        events[-1].payload_json["status"]
        == AISessionStatus
        .WAITING_ASYNC_TASK
        .value
    )
    assert (
        events[-1].payload_json[
            "resume_requires_actor"
        ]
        is True
    )
