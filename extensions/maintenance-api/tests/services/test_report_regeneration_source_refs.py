from __future__ import annotations

import pytest
from app.repositories.ai_report_repository import ai_report_repository
from app.repositories.ai_session_repository import AISessionRepository
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service


def _actor(actor_context):
    return actor_context(
        tenant_id="tenant-c2d-c",
        user_id="c2d-c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )


def _generated_report_with_session_source(session, actor):
    source = AISessionRepository().create_session(
        session,
        actor.tenant_id,
        title="C2D-C persisted source",
        sensitivity_level="INTERNAL",
        created_by=actor.user_id,
    )
    report = ai_report_service.create(
        session,
        actor,
        AIReportCreateRequest(
            title="C2D-C regeneration source refs",
            report_type="MANAGEMENT_DECISION",
            session_id=source.id,
        ),
    )
    ai_report_service.generate(session, actor, report.id)
    return report, source


def test_regenerate_copies_exact_source_refs_without_querying_latest(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = _actor(actor_context)
    report, _ = _generated_report_with_session_source(session, actor)
    parent = ai_report_service.latest_version(session, actor, report.id)
    parent_refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        parent.id,
    )
    parent_refs[0].ordinal = 11
    session.commit()

    monkeypatch.setattr(
        "app.services.report_source_service.ReportSourceService.resolve_for_create",
        lambda *args, **kwargs: pytest.fail(
            "regeneration queried current source"
        ),
    )

    child = ai_report_service.regenerate(session, actor, report.id)
    child_refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        child.id,
    )

    assert [ref.report_version_id for ref in child_refs] == [child.id]
    assert [
        (
            ref.source_type,
            ref.source_id,
            ref.source_version,
            ref.source_lineage_id,
            ref.source_digest,
            ref.ordinal,
        )
        for ref in child_refs
    ] == [
        (
            ref.source_type,
            ref.source_id,
            ref.source_version,
            ref.source_lineage_id,
            ref.source_digest,
            ref.ordinal,
        )
        for ref in parent_refs
    ]


def test_regeneration_ignores_source_change_after_v1(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    report, source = _generated_report_with_session_source(session, actor)
    parent = ai_report_service.latest_version(session, actor, report.id)
    parent_refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        parent.id,
    )
    source.version += 1
    session.commit()

    child = ai_report_service.regenerate(session, actor, report.id)
    child_refs = ai_report_repository.list_source_refs(
        session,
        actor.tenant_id,
        child.id,
    )

    assert child.input_digest == parent.input_digest
    assert child.source_snapshot_json == parent.source_snapshot_json
    assert child.template_version == parent.template_version
    assert [
        (ref.source_type, ref.source_id, ref.source_version, ref.ordinal)
        for ref in child_refs
    ] == [
        (ref.source_type, ref.source_id, ref.source_version, ref.ordinal)
        for ref in parent_refs
    ]
