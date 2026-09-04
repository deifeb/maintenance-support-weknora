from types import SimpleNamespace

import pytest
from app.models.enums import AIReportSourceType
from app.repositories.ai_report_repository import ai_report_repository
from app.repositories.ai_session_repository import AISessionRepository
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service
from app.services.report_source_policy import ReportSourceRecord, build_source_records


def test_current_report_sources_become_stable_ordered_records() -> None:
    ai_session = SimpleNamespace(
        id=7,
        version=2,
        session_code="AI-007",
    )
    scenario = SimpleNamespace(
        id=8,
        version=3,
        version_code="SCN-003",
        formula_version="formula-1",
    )
    calculation = SimpleNamespace(input_snapshot_hash="a" * 64)
    run = SimpleNamespace(
        id=9,
        attempt_number=1,
        calculation_id=10,
        engine_version="engine-1",
    )
    review = SimpleNamespace(
        id=11,
        version=4,
        rule_set_version="rules-1",
        scenario_version_id=8,
        calculation_run_id=9,
    )

    records = build_source_records(
        ai_session=ai_session,
        scenario_version=scenario,
        calculation_run=run,
        calculation=calculation,
        review_run=review,
    )

    assert [record.source_type.value for record in records] == [
        "AI_SESSION",
        "SCENARIO_VERSION",
        "CALCULATION_RUN",
        "DEMAND_REVIEW",
    ]
    assert all(record.source_version for record in records)
    assert list(enumerate(records))[-1][0] == 3
    assert records[0].source_digest
    assert records[2].evidence["input_snapshot_hash"] == "a" * 64


def _record() -> ReportSourceRecord:
    return ReportSourceRecord(
        source_type=AIReportSourceType.AI_SESSION,
        source_id="1",
        source_version="1",
        source_lineage_id=None,
        source_digest="a" * 64,
        evidence={},
    )


def _create_version_for(session, actor):
    job = ai_report_repository.create_job(
        session,
        actor.tenant_id,
        title="Source reference report",
        report_type="MANAGEMENT_DECISION",
    )
    return ai_report_repository.create_version(
        session,
        actor.tenant_id,
        report_job_id=job.id,
        template_version="1.0",
        content_digest="b" * 64,
    )


def _create_payload_with_owned_sources(session, actor):
    ai_session = AISessionRepository().create_session(
        session,
        actor.tenant_id,
        title="Owned report source",
        sensitivity_level="INTERNAL",
        created_by=actor.user_id,
    )
    return AIReportCreateRequest(
        title="Source reference report",
        session_id=ai_session.id,
    )


def test_create_persists_source_refs_with_the_snapshot(
    session,
    actor_context,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="author",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    job = ai_report_service.create(
        session,
        actor,
        _create_payload_with_owned_sources(session, actor),
    )
    version = ai_report_service.latest_version(session, actor, job.id)

    refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        version.id,
    )

    assert [
        (ref.source_type.value, ref.source_id, ref.ordinal)
        for ref in refs
    ] == [("AI_SESSION", "1", 0)]
    assert version.source_snapshot_json["schema_version"] == "1.1"
    assert (
        version.source_snapshot_json["provenance_completeness"]
        == "AUTHORITATIVE"
    )


def test_source_ref_requires_tenant_scoped_version(
    session,
    actor_context,
) -> None:
    foreign = actor_context(
        tenant_id="tenant-b",
        user_id="foreign",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_version = _create_version_for(session, foreign)

    with pytest.raises(LookupError):
        ai_report_repository.create_source_refs(
            session,
            "tenant-a",
            foreign_version.id,
            (_record(),),
        )


def test_source_ref_unique_within_report_version(
    session,
    actor_context,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="author",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    version = _create_version_for(session, actor)
    ai_report_repository.create_source_refs(
        session,
        actor.tenant_id,
        version.id,
        (_record(),),
    )
    session.commit()

    with pytest.raises(
        ValueError,
        match="duplicate report source reference",
    ):
        ai_report_repository.create_source_refs(
            session,
            actor.tenant_id,
            version.id,
            (_record(),),
        )

    session.rollback()
    assert len(
        ai_report_repository.list_source_refs(
            session,
            actor.tenant_id,
            version.id,
        )
    ) == 1
