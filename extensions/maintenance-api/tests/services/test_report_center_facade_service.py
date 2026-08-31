from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.exceptions import NotFoundError
from app.models import AIReportExport, AIReportJob
from app.repositories.ai_session_repository import AISessionRepository
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service
from pydantic import ValidationError
from sqlalchemy import func, select


def _facade():
    module = importlib.import_module(
        "app.services.report_center_service"
    )
    return module.ReportCenterQueryService()


def _create_request_type():
    schema = importlib.import_module(
        "app.schemas.report_center"
    )
    assert hasattr(
        schema,
        "ReportJobCreateRequest",
    ), "C2A RED: ReportJobCreateRequest is absent"
    return schema.ReportJobCreateRequest


def _assert_method(service, name: str):
    assert hasattr(service, name), (
        f"C2A RED: ReportCenterQueryService."
        f"{name} is absent"
    )
    return getattr(service, name)


def _create_authoritative_job(
    session,
    actor,
    *,
    title: str = "C2A authoritative report",
):
    return ai_report_service.create(
        session,
        actor,
        AIReportCreateRequest(
            title=title,
            report_type="MANAGEMENT_DECISION",
        ),
    )


def test_report_job_create_request_is_fail_closed():
    request_type = _create_request_type()

    with pytest.raises(ValidationError):
        request_type(
            title="tenant override",
            tenant_id="tenant-b",
        )

    with pytest.raises(ValidationError):
        request_type(
            title="unsupported type",
            report_type="ALLOCATION_PLAN",
        )


def test_report_center_facade_service_create_job_uses_existing_authority(
    session,
    actor_context,
) -> None:
    service = _facade()
    create_job = _assert_method(
        service,
        "create_job",
    )
    request_type = _create_request_type()
    actor = actor_context(
        tenant_id="tenant-c2a",
        user_id="c2a-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    before = session.scalar(
        select(func.count(AIReportJob.id))
    )

    result = create_job(
        session,
        actor,
        request_type(
            title="C2A facade report",
            report_type="MANAGEMENT_DECISION",
        ),
    )

    assert result.report_id > 0
    assert result.report_code
    assert result.report_type.value == (
        "MANAGEMENT_DECISION"
    )
    assert result.job_status.value == "CREATED"
    assert result.latest_version.version_number == 1
    assert result.latest_version.status.value == "DRAFT"
    session.expire_all()
    after = session.scalar(
        select(func.count(AIReportJob.id))
    )
    assert after == before + 1


def test_report_center_facade_create_job_preserves_source_tenant_isolation(
    session,
    actor_context,
) -> None:
    service = _facade()
    create_job = _assert_method(
        service,
        "create_job",
    )
    request_type = _create_request_type()
    owner = actor_context(
        tenant_id="tenant-c2a-owner",
        user_id="session-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    ai_session = AISessionRepository().create_session(
        session,
        owner.tenant_id,
        title="C2A owned session",
        sensitivity_level="INTERNAL",
        created_by=owner.user_id,
    )
    session.commit()
    before = session.scalar(
        select(func.count(AIReportJob.id))
    )

    with pytest.raises(NotFoundError):
        create_job(
            session,
            foreign,
            request_type(
                title="foreign linked report",
                session_id=ai_session.id,
            ),
        )

    session.rollback()
    after = session.scalar(
        select(func.count(AIReportJob.id))
    )
    assert after == before


def test_report_center_facade_job_status_is_compact_and_tenant_scoped(
    session,
    actor_context,
) -> None:
    service = _facade()
    job_status = _assert_method(
        service,
        "job_status",
    )
    owner = actor_context(
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    job = _create_authoritative_job(
        session,
        owner,
    )

    result = job_status(
        session,
        owner,
        job.id,
    )
    payload = result.model_dump(mode="json")

    assert set(payload) == {
        "report_id",
        "report_code",
        "report_type",
        "job_status",
        "title",
        "progress_percent",
        "error_code",
        "latest_version",
    }
    assert {
        "error_message",
        "metadata",
        "metadata_json",
        "sections",
        "citations",
        "file_path",
        "exports",
    }.isdisjoint(payload)
    assert payload["report_id"] == job.id

    with pytest.raises(NotFoundError):
        job_status(
            session,
            foreign,
            job.id,
        )


def test_report_center_facade_detail_delegates_to_authoritative_read(
    session,
    actor_context,
) -> None:
    service = _facade()
    detail = _assert_method(
        service,
        "detail",
    )
    owner = actor_context(
        tenant_id="tenant-c2a",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    job = _create_authoritative_job(
        session,
        owner,
    )
    expected = ai_report_service.read(
        session,
        owner,
        job.id,
    )

    actual = detail(
        session,
        owner,
        job.id,
    )

    assert actual == expected
    with pytest.raises(NotFoundError):
        detail(
            session,
            foreign,
            job.id,
        )


def test_report_center_facade_versions_preserve_authoritative_order(
    session,
    actor_context,
) -> None:
    service = _facade()
    versions = _assert_method(
        service,
        "versions",
    )
    owner = actor_context(
        tenant_id="tenant-c2a",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    job = _create_authoritative_job(
        session,
        owner,
    )
    authoritative = ai_report_service.list_versions(
        session,
        owner,
        job.id,
    )

    result = versions(
        session,
        owner,
        job.id,
    )

    assert [
        row.id
        for row in result
    ] == [
        row.id
        for row in authoritative
    ]
    assert [
        row.version_number
        for row in result
    ] == [
        row.version_number
        for row in authoritative
    ]


def test_report_center_facade_export_delegates_and_authorizes_first(
    session,
    actor_context,
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _facade()
    export = _assert_method(
        service,
        "export",
    )
    owner = actor_context(
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    job = _create_authoritative_job(
        session,
        owner,
    )
    output_dir = tmp_path / "c2a-service-export"
    monkeypatch.setattr(
        (
            "app.services.ai_report_service."
            "get_settings"
        ),
        lambda: SimpleNamespace(
            ai_report_export_dir=str(output_dir)
        ),
    )
    before = session.scalar(
        select(func.count(AIReportExport.id))
    )

    content, content_type, file_name = export(
        session,
        owner,
        job.id,
        "JSON",
    )

    assert content.startswith(b"{")
    assert content_type.startswith(
        "application/json"
    )
    assert file_name.endswith(".json")
    assert (
        output_dir / file_name
    ).is_file()
    session.expire_all()
    after_owner = session.scalar(
        select(func.count(AIReportExport.id))
    )
    assert after_owner == before + 1
    files_before_foreign = sorted(
        path.name
        for path in output_dir.iterdir()
    )

    with pytest.raises(NotFoundError):
        export(
            session,
            foreign,
            job.id,
            "JSON",
        )

    session.rollback()
    session.expire_all()
    after_foreign = session.scalar(
        select(func.count(AIReportExport.id))
    )
    assert after_foreign == after_owner
    assert sorted(
        path.name
        for path in output_dir.iterdir()
    ) == files_before_foreign


def test_report_center_facade_exposes_only_regenerate_command():
    service = _facade()

    assert hasattr(service, "regenerate"), (
        "C2B RED A04: ReportCenterQueryService.regenerate "
        "is absent"
    )
    for name in (
        "generate",
        "validate",
        "finalize",
    ):
        assert not hasattr(service, name)
