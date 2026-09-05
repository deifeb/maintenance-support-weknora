from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.models.enums import AIReportSourceType
from app.repositories.ai_report_repository import ai_report_repository
from app.repositories.ai_session_repository import AISessionRepository
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service
from app.services.report_source_policy import ReportSourceRecord, build_source_records
from app.services.report_source_service import ResolvedReportSources
from sqlalchemy import event


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


def _second_record() -> ReportSourceRecord:
    return ReportSourceRecord(
        source_type=AIReportSourceType.SCENARIO_VERSION,
        source_id="2",
        source_version="1",
        source_lineage_id=None,
        source_digest="b" * 64,
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


def test_create_uses_pre_resolved_sources_without_another_business_read(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="author",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    evidence = {"id": 71, "version_number": 4, "status": "PUBLISHED"}
    record = ReportSourceRecord(
        source_type=AIReportSourceType.DEMAND_LIST,
        source_id="71",
        source_version="4",
        source_lineage_id="lineage-71",
        source_digest="c" * 64,
        evidence=evidence,
    )
    resolved = ResolvedReportSources(
        records=(record,),
        session_id=None,
        scenario_version_id=None,
        calculation_run_id=None,
        review_run_id=None,
    )

    def unexpected_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("resolved sources must not be read again")

    monkeypatch.setattr(
        ai_report_repository,
        "load_create_sources_owned",
        unexpected_read,
    )
    job = ai_report_service.create(
        session,
        actor,
        AIReportCreateRequest(title="Resolved source report"),
        resolved_sources=resolved,
    )
    version = ai_report_service.latest_version(session, actor, job.id)
    refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        version.id,
    )

    assert version.source_snapshot_json["sources"][0]["evidence"] == evidence
    assert [(ref.source_type, ref.source_id) for ref in refs] == [
        (AIReportSourceType.DEMAND_LIST, "71")
    ]


def test_create_converts_resolved_inventory_snapshot_timestamp(
    session,
    actor_context,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="author",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    record = ReportSourceRecord(
        source_type=AIReportSourceType.CALCULATION_RUN,
        source_id="81",
        source_version="2",
        source_lineage_id=None,
        source_digest="d" * 64,
        evidence={
            "id": 81,
            "attempt_number": 2,
            "inventory_snapshot_at": "2026-09-04T03:00:00+00:00",
        },
    )
    resolved = ResolvedReportSources(
        records=(record,),
        session_id=None,
        scenario_version_id=None,
        calculation_run_id=None,
        review_run_id=None,
    )

    job = ai_report_service.create(
        session,
        actor,
        AIReportCreateRequest(title="Resolved calculation timestamp"),
        resolved_sources=resolved,
    )
    version = ai_report_service.latest_version(session, actor, job.id)

    assert version.inventory_snapshot_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 9, 4, 3, 0, tzinfo=timezone.utc
    )


def test_create_does_not_requery_pre_resolved_legacy_links(
    session,
    actor_context,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="author",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    payload = _create_payload_with_owned_sources(session, actor)
    resolved = ResolvedReportSources(
        records=(
            ReportSourceRecord(
                source_type=AIReportSourceType.AI_SESSION,
                source_id=str(payload.session_id),
                source_version="1",
                source_lineage_id=None,
                source_digest="e" * 64,
                evidence={"id": payload.session_id, "version": 1},
            ),
        ),
        session_id=payload.session_id,
        scenario_version_id=None,
        calculation_run_id=None,
        review_run_id=None,
    )
    source_selects: list[str] = []

    def capture_source_selects(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        normalized = statement.casefold()
        if normalized.lstrip().startswith("select") and "ai_sessions" in normalized:
            source_selects.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture_source_selects)
    try:
        job = ai_report_service.create(
            session,
            actor,
            payload,
            resolved_sources=resolved,
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_source_selects)

    assert job.session_id == payload.session_id
    assert source_selects == []


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
        match="immutable",
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


def test_source_ref_batch_is_immutable_after_initial_insert(
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
        match="immutable",
    ):
        ai_report_repository.create_source_refs(
            session,
            actor.tenant_id,
            version.id,
            (_second_record(),),
        )
