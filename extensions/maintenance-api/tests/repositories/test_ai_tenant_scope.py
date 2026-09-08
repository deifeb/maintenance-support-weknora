from __future__ import annotations

from inspect import signature

import app.repositories as repositories
import pytest
from app.models import (
    AIEvent,
    AIEvidenceItem,
    AIMessage,
    AIPlanStep,
    AIReportSection,
    AIReviewFinding,
    AISessionSnapshot,
)
from app.models.enums import (
    AIBlockingLevel,
    AIConfirmationLevel,
    AIMessageRole,
    AIMessageType,
    AIPlanStepStatus,
    AISeverity,
    AIToolCallStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

REPOSITORY_METHODS = (
    (
        repositories.AISessionRepository,
        (
            "create_session",
            "get",
            "add_message",
            "append_event",
            "list_events",
            "create_snapshot",
            "latest_snapshot",
            "list_recent_messages",
        ),
    ),
    (
        repositories.AIExecutionRepository,
        (
            "create_plan",
            "get_plan",
            "latest_plan",
            "add_step",
            "get_step",
            "list_steps",
            "list_completed_steps",
            "create_tool_call",
            "get_tool_call",
            "get_tool_call_by_idempotency_key",
            "list_completed_tool_calls",
            "create_confirmation",
            "get_confirmation",
            "list_pending_confirmations",
            "find_approved_confirmation",
            "create_model_call",
            "get_model_call",
        ),
    ),
    (
        repositories.AIReviewRepository,
        (
            "create_run",
            "get_run",
            "add_finding",
            "get_finding",
            "list_findings",
        ),
    ),
    (
        repositories.AIReportRepository,
        (
            "create_job",
            "get_job",
            "list_versions",
            "latest_version",
            "get_version",
            "create_version",
            "clear_version_content",
            "clear_validation_findings",
            "add_section",
            "list_sections",
            "add_citation",
            "list_citations",
            "add_validation_finding",
            "list_validation_findings",
            "add_export",
            "get_export",
        ),
    ),
)


def evidence_repository_class():
    repository_type = getattr(
        repositories,
        "AIEvidenceRepository",
        None,
    )
    assert repository_type is not None
    return repository_type


def test_ai_repository_methods_require_tenant_id() -> None:
    for repository_type, method_names in (
        REPOSITORY_METHODS
    ):
        for method_name in method_names:
            parameters = signature(
                getattr(
                    repository_type,
                    method_name,
                )
            ).parameters
            assert "tenant_id" in parameters, (
                repository_type.__name__,
                method_name,
                parameters,
            )

    evidence_type = evidence_repository_class()
    for method_name in (
        "create_package",
        "get_package",
        "add_item",
        "list_items",
        "list_recent_packages",
    ):
        assert "tenant_id" in signature(
            getattr(evidence_type, method_name)
        ).parameters


def make_session(
    repository,
    session: Session,
    tenant_id: str,
    title: str,
):
    return repository.create_session(
        session,
        tenant_id,
        title=title,
        sensitivity_level="INTERNAL",
        created_by="tester",
    )


def test_session_repository_filters_dirty_children(
    session: Session,
) -> None:
    repository = repositories.AISessionRepository()
    local = make_session(
        repository,
        session,
        "tenant-a",
        "Local",
    )
    foreign = make_session(
        repository,
        session,
        "tenant-b",
        "Foreign",
    )

    message = repository.add_message(
        session,
        "tenant-a",
        local.id,
        role="USER",
        message_type="USER_TEXT",
        content="local",
    )
    event = repository.append_event(
        session,
        "tenant-a",
        local.id,
        "LOCAL",
        {},
    )
    snapshot = repository.create_snapshot(
        session,
        "tenant-a",
        local.id,
        current_state="CREATED",
    )

    session.add_all(
        [
            AIMessage(
                tenant_id="tenant-b",
                session_id=local.id,
                role=AIMessageRole.USER,
                message_type=(
                    AIMessageType.USER_TEXT
                ),
                content="foreign",
                sequence=99,
            ),
            AIEvent(
                tenant_id="tenant-b",
                session_id=local.id,
                sequence=99,
                event_type="FOREIGN",
                event_version="1.0",
                payload_json={},
                visibility="USER",
            ),
            AISessionSnapshot(
                tenant_id="tenant-b",
                session_id=local.id,
                snapshot_version=99,
                current_state="CREATED",
            ),
        ]
    )
    session.flush()
    session.expire_all()

    assert repository.get(
        session,
        "tenant-a",
        foreign.id,
    ) is None
    assert [
        row.id
        for row in repository.list_recent_messages(
            session,
            "tenant-a",
            local.id,
            limit=20,
        )
    ] == [message.id]
    assert [
        row.id
        for row in repository.list_events(
            session,
            "tenant-a",
            local.id,
        )
    ] == [event.id]
    assert repository.latest_snapshot(
        session,
        "tenant-a",
        local.id,
    ).id == snapshot.id


def test_execution_repository_scopes_idempotency(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    execution = repositories.AIExecutionRepository()
    local = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    foreign = make_session(
        sessions,
        session,
        "tenant-b",
        "Foreign",
    )

    plan = execution.create_plan(
        session,
        "tenant-a",
        session_id=local.id,
        goal="goal",
        intent="GENERAL_QA",
    )
    step = execution.add_step(
        session,
        "tenant-a",
        plan_id=plan.id,
        step_index=1,
        step_code="local",
        action_type="CALL_TOOL",
        tool_name="echo",
        input_template={},
        depends_on=[],
        confirmation_level="NONE",
        risk_level="LOW",
    )
    step.status = AIPlanStepStatus.COMPLETED

    session.add(
        AIPlanStep(
            tenant_id="tenant-b",
            plan_id=plan.id,
            step_index=99,
            step_code="foreign",
            action_type="CALL_TOOL",
            tool_name="echo",
            input_template_json={},
            depends_on_json=[],
            confirmation_level=(
                AIConfirmationLevel.NONE
            ),
            risk_level="LOW",
        )
    )

    local_call = execution.create_tool_call(
        session,
        "tenant-a",
        session_id=local.id,
        plan_step_id=step.id,
        tool_name="echo",
        tool_version="1.0",
        input_payload={},
        idempotency_key="same-key",
    )
    foreign_call = execution.create_tool_call(
        session,
        "tenant-b",
        session_id=foreign.id,
        tool_name="echo",
        tool_version="1.0",
        input_payload={},
        idempotency_key="same-key",
    )
    local_call.status = AIToolCallStatus.SUCCEEDED
    foreign_call.status = AIToolCallStatus.SUCCEEDED

    confirmation = execution.create_confirmation(
        session,
        "tenant-a",
        session_id=local.id,
        operation_name="echo",
        confirmation_level="EXPLICIT",
        input_preview={},
        input_digest="a" * 64,
        confirmation_token_hash="b" * 64,
        risk_level="HIGH",
    )
    model_call = execution.create_model_call(
        session,
        "tenant-a",
        session_id=local.id,
        request_id="request-a",
        function_name="scenario_parsing",
        provider="RULE_FALLBACK",
        model="rule",
        prompt_name="scenario-parser",
        prompt_version="1.0",
        sensitivity_level="INTERNAL",
        input_digest="c" * 64,
    )
    session.flush()
    session.expire_all()

    assert [
        row.id
        for row in execution.list_steps(
            session,
            "tenant-a",
            plan.id,
        )
    ] == [step.id]
    assert (
        execution.get_tool_call_by_idempotency_key(
            session,
            "tenant-a",
            "same-key",
        ).id
        == local_call.id
    )
    assert (
        execution.get_tool_call_by_idempotency_key(
            session,
            "tenant-b",
            "same-key",
        ).id
        == foreign_call.id
    )
    assert [
        row.id
        for row in execution.list_completed_tool_calls(
            session,
            "tenant-a",
            local.id,
        )
    ] == [local_call.id]
    assert execution.get_confirmation(
        session,
        "tenant-b",
        confirmation.id,
    ) is None
    assert execution.get_model_call(
        session,
        "tenant-a",
        model_call.id,
    ).tenant_id == "tenant-a"


def finding_payload() -> dict:
    return {
        "rule_code": "RULE-1",
        "rule_version": "1.0",
        "category": "TEST",
        "severity": AISeverity.WARNING,
        "blocking_level": AIBlockingLevel.NONE,
        "finding_title": "Finding",
        "deterministic_message": "Message",
    }


def test_evidence_review_and_report_children_are_scoped(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    local_session = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    foreign_session = make_session(
        sessions,
        session,
        "tenant-b",
        "Foreign",
    )

    evidence = evidence_repository_class()()
    package = evidence.create_package(
        session,
        "tenant-a",
        session_id=local_session.id,
        query={"question": "q"},
        conflicts=[],
        missing_evidence=[],
        retrieval_metadata={},
        sensitivity_level="INTERNAL",
        content_digest="d" * 64,
    )
    local_item = evidence.add_item(
        session,
        "tenant-a",
        package_id=package.id,
        evidence_id="E-1",
        evidence_type="TEXT_EXCERPT",
        statement="Local",
        source_name="Test",
        status="VALID",
        sensitivity_level="INTERNAL",
        excerpt="Local",
    )
    session.add(
        AIEvidenceItem(
            tenant_id="tenant-b",
            package_id=package.id,
            evidence_id="E-FOREIGN",
            evidence_type="TEXT_EXCERPT",
            statement="Foreign",
            source_name="Test",
            status="VALID",
            sensitivity_level="INTERNAL",
            excerpt="Foreign",
        )
    )

    reviews = repositories.AIReviewRepository()
    review = reviews.create_run(
        session,
        "tenant-a",
        session_id=local_session.id,
        input_snapshot={},
    )
    local_finding = reviews.add_finding(
        session,
        "tenant-a",
        review.id,
        finding_payload(),
    )
    session.add(
        AIReviewFinding(
            tenant_id="tenant-b",
            review_run_id=review.id,
            **finding_payload(),
        )
    )

    reports = repositories.AIReportRepository()
    local_job = reports.create_job(
        session,
        "tenant-a",
        title="Local report",
        report_type="MANAGEMENT_DECISION",
        session_id=local_session.id,
    )
    foreign_job = reports.create_job(
        session,
        "tenant-b",
        title="Foreign report",
        report_type="MANAGEMENT_DECISION",
        session_id=foreign_session.id,
    )
    version = reports.create_version(
        session,
        "tenant-a",
        report_job_id=local_job.id,
        template_version="1.0",
        content_digest="e" * 64,
    )
    local_section = reports.add_section(
        session,
        "tenant-a",
        report_version_id=version.id,
        section_code="local",
        title="Local",
        order_index=1,
        content="Local",
        source_type="DETERMINISTIC",
    )
    foreign_section = AIReportSection(
        tenant_id="tenant-b",
        report_version_id=version.id,
        section_code="foreign",
        title="Foreign",
        order_index=99,
        content="Foreign",
        source_type="DETERMINISTIC",
    )
    session.add(foreign_section)
    session.flush()
    foreign_section_id = foreign_section.id
    session.expire_all()

    assert [
        row.id
        for row in evidence.list_items(
            session,
            "tenant-a",
            package.id,
        )
    ] == [local_item.id]
    assert [
        row.id
        for row in reviews.list_findings(
            session,
            "tenant-a",
            review.id,
        )
    ] == [local_finding.id]
    assert reports.get_job(
        session,
        "tenant-a",
        foreign_job.id,
    ) is None
    assert [
        row.id
        for row in reports.list_sections(
            session,
            "tenant-a",
            version.id,
        )
    ] == [local_section.id]

    reports.clear_version_content(
        session,
        "tenant-a",
        version.id,
    )
    session.expire_all()

    assert session.scalar(
        select(AIReportSection).where(
            AIReportSection.id == foreign_section_id
        )
    ) is not None



def test_report_section_rejects_foreign_model_call(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    execution = repositories.AIExecutionRepository()
    reports = repositories.AIReportRepository()

    local_session = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    foreign_session = make_session(
        sessions,
        session,
        "tenant-b",
        "Foreign",
    )
    foreign_call = execution.create_model_call(
        session,
        "tenant-b",
        session_id=foreign_session.id,
        request_id="foreign-report-call",
        function_name="report_generation",
        provider="RULE_FALLBACK",
        model="rule",
        prompt_name="report",
        prompt_version="1.0",
        sensitivity_level="INTERNAL",
        input_digest="f" * 64,
    )
    job = reports.create_job(
        session,
        "tenant-a",
        title="Local report",
        report_type="MANAGEMENT_DECISION",
        session_id=local_session.id,
    )
    version = reports.create_version(
        session,
        "tenant-a",
        report_job_id=job.id,
        template_version="1.0",
        content_digest="a" * 64,
    )

    with pytest.raises(LookupError):
        reports.add_section(
            session,
            "tenant-a",
            report_version_id=version.id,
            section_code="management_summary",
            title="Summary",
            order_index=1,
            content="Content",
            source_type="LLM",
            llm_model_call_id=foreign_call.id,
        )


def test_review_finding_rejects_foreign_model_call(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    execution = repositories.AIExecutionRepository()
    reviews = repositories.AIReviewRepository()

    local_session = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    foreign_session = make_session(
        sessions,
        session,
        "tenant-b",
        "Foreign",
    )
    foreign_call = execution.create_model_call(
        session,
        "tenant-b",
        session_id=foreign_session.id,
        request_id="foreign-review-call",
        function_name="review_explanation",
        provider="RULE_FALLBACK",
        model="rule",
        prompt_name="review",
        prompt_version="1.0",
        sensitivity_level="INTERNAL",
        input_digest="b" * 64,
    )
    review = reviews.create_run(
        session,
        "tenant-a",
        session_id=local_session.id,
        input_snapshot={},
    )
    payload = finding_payload()
    payload["llm_model_call_id"] = foreign_call.id

    with pytest.raises(LookupError):
        reviews.add_finding(
            session,
            "tenant-a",
            review.id,
            payload,
        )


def test_review_finding_ignores_untrusted_resolution_fields(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    reviews = repositories.AIReviewRepository()
    local_session = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    review = reviews.create_run(
        session,
        "tenant-a",
        session_id=local_session.id,
        input_snapshot={},
    )
    payload = finding_payload()
    payload.update(
        {
            "status": "RESOLVED",
            "resolved_by": "forged-user",
            "resolved_at": "2026-07-26T00:00:00Z",
            "resolution_comment": "forged",
        }
    )

    finding = reviews.add_finding(
        session,
        "tenant-a",
        review.id,
        payload,
    )

    assert finding.status.value == "OPEN"
    assert finding.resolved_by is None
    assert finding.resolved_at is None
    assert finding.resolution_comment is None


def test_report_version_ignores_untrusted_audit_fields(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    reports = repositories.AIReportRepository()
    local_session = make_session(
        sessions,
        session,
        "tenant-a",
        "Local",
    )
    job = reports.create_job(
        session,
        "tenant-a",
        title="Local report",
        report_type="MANAGEMENT_DECISION",
        session_id=local_session.id,
    )

    version = reports.create_version(
        session,
        "tenant-a",
        report_job_id=job.id,
        template_version="1.0",
        content_digest="c" * 64,
        created_by="forged-creator",
        reviewed_by="forged-reviewer",
        finalized_by="forged-finalizer",
    )

    assert version.created_by is None
    assert version.reviewed_by is None
    assert version.finalized_by is None

def test_repositories_reject_foreign_parent_ids(
    session: Session,
) -> None:
    sessions = repositories.AISessionRepository()
    execution = repositories.AIExecutionRepository()
    foreign = make_session(
        sessions,
        session,
        "tenant-b",
        "Foreign",
    )

    with pytest.raises(LookupError):
        execution.create_plan(
            session,
            "tenant-a",
            session_id=foreign.id,
            goal="goal",
            intent="GENERAL_QA",
        )
