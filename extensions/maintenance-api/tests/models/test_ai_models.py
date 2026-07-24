import app.models  # noqa: F401
from app.db.base import Base
from app.models import AIEvent, AISession
from app.models.enums import AISessionStatus

EXPECTED_AI_TABLES = {
    "ai_sessions",
    "ai_messages",
    "ai_session_snapshots",
    "ai_execution_plans",
    "ai_plan_steps",
    "ai_tool_calls",
    "ai_confirmation_requests",
    "ai_events",
    "ai_model_calls",
    "ai_evidence_packages",
    "ai_evidence_items",
    "ai_review_runs",
    "ai_review_findings",
    "ai_report_jobs",
    "ai_report_versions",
    "ai_report_sections",
    "ai_report_citations",
    "ai_report_validation_findings",
    "ai_report_exports",
}


def test_all_ai_tables_are_registered():
    assert EXPECTED_AI_TABLES <= set(Base.metadata.tables)


def test_session_and_event_constraints(session):
    row = AISession(
        session_code="AI-001",
        title="测试会话",
        status=AISessionStatus.CREATED,
        sensitivity_level="INTERNAL",
        execution_mode="LLM",
        last_event_sequence=0,
    )
    session.add(row)
    session.commit()
    event = AIEvent(
        session_id=row.id,
        sequence=1,
        event_type="SESSION_STARTED",
        event_version="1.0",
        payload_json={"session_code": row.session_code},
        visibility="USER",
    )
    session.add(event)
    session.commit()
    assert event.id is not None
