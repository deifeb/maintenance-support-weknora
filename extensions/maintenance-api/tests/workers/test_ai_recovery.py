from app.models import AIModelCall, AIReportJob
from app.models.enums import (
    AIModelCallStatus,
    AIReportJobStatus,
    AIReportType,
    AISessionStatus,
)
from app.workers.ai_recovery import recover_interrupted_ai_tasks
from tests.ai.factories import create_ai_session


def test_recovery_marks_running_session_and_model_call_recoverable(session) -> None:
    row = create_ai_session(session, status=AISessionStatus.EXECUTING)
    session.add(
        AIModelCall(
            session_id=row.id,
            request_id="interrupted-call",
            function_name="scenario_parsing",
            provider="OLLAMA",
            model="qwen",
            status=AIModelCallStatus.PENDING,
            prompt_name="scenario-parser",
            prompt_version="1.0",
            sensitivity_level="INTERNAL",
            input_digest="0" * 64,
        )
    )
    session.add(
        AIReportJob(
            report_code="AIR-INTERRUPTED",
            session_id=row.id,
            report_type=AIReportType.MANAGEMENT_DECISION,
            status=AIReportJobStatus.GENERATING_SECTIONS,
            title="中断报告",
        )
    )
    session.commit()

    count = recover_interrupted_ai_tasks(session)
    session.refresh(row)
    model_call = session.query(AIModelCall).filter_by(request_id="interrupted-call").one()
    report = session.query(AIReportJob).filter_by(report_code="AIR-INTERRUPTED").one()

    assert count == 3
    assert row.status is AISessionStatus.PARTIALLY_COMPLETED
    assert model_call.status is AIModelCallStatus.FAILED
    assert model_call.error_code == "PROVIDER_CALL_INTERRUPTED"
    assert report.status is AIReportJobStatus.PARTIALLY_COMPLETED
    assert [
        event.event_type
        for event in session.query(__import__("app.models", fromlist=["AIEvent"]).AIEvent).all()
    ] == [
        "RECOVERY_STARTED",
        "RECOVERY_COMPLETED",
    ]
