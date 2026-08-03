from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from app.models import (
    AIReportExport,
    AIReportJob,
)
from app.models.enums import (
    AIReportJobStatus,
    AIReportVersionStatus,
)
from app.repositories.ai_report_repository import (
    ai_report_repository,
)
from app.security.actor import (
    ActorContext,
    MaintenanceRole,
)
from app.services.ai_report_service import (
    ai_report_service,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_report_api_generates_validates_finalizes_and_exports(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="report-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="report-contributor-request",
    )
    admin_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="report-admin",
        role=MaintenanceRole.ADMIN,
        request_id="report-admin-request",
    )
    viewer_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="report-viewer",
        role=MaintenanceRole.VIEWER,
        request_id="report-viewer-request",
    )

    created = client.post(
        "/api/v1/ai/reports",
        headers=contributor_headers,
        json={
            "title": "维修器材保障分析报告",
            "report_type": (
                "MANAGEMENT_DECISION"
            ),
            "metadata": {
                "allowed_numbers": ["8"]
            },
            "sections": [
                {
                    "section_code": (
                        "management_summary"
                    ),
                    "title": "管理摘要",
                    "content": (
                        "本次共识别 8 项需求。"
                        "[E-001]"
                    ),
                    "source_type": (
                        "DETERMINISTIC"
                    ),
                }
            ],
            "citations": [
                {
                    "citation_id": "E-001",
                    "source_type": (
                        "CALCULATION_SNAPSHOT"
                    ),
                    "source_name": (
                        "需求计算快照"
                    ),
                }
            ],
        },
    )
    assert created.status_code == 200
    assert (
        created.json()["meta"]["tenant_id"]
        == "tenant-a"
    )
    report_id = created.json()["data"]["id"]

    generated = client.post(
        f"/api/v1/ai/reports/{report_id}/generate",
        headers=contributor_headers,
    )
    assert generated.status_code == 200
    assert (
        len(
            generated.json()[
                "data"
            ]["sections"]
        )
        == 17
    )

    validated = client.post(
        f"/api/v1/ai/reports/{report_id}/validate",
        headers=contributor_headers,
    )
    assert validated.status_code == 200
    assert (
        validated.json()["data"]["findings"]
        == []
    )

    finalized = client.post(
        f"/api/v1/ai/reports/{report_id}/finalize",
        headers=admin_headers,
    )
    assert finalized.status_code == 200
    assert (
        finalized.json()["data"]["status"]
        == "FINAL"
    )
    assert (
        finalized.json()[
            "data"
        ]["finalized_by"]
        == "report-admin"
    )

    versions = client.get(
        f"/api/v1/ai/reports/{report_id}/versions",
        headers=viewer_headers,
    )
    assert versions.status_code == 200
    assert len(versions.json()["data"]) == 1

    docx = client.get(
        f"/api/v1/ai/reports/{report_id}/exports/docx",
        headers=viewer_headers,
    )
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"
    assert (
        docx.headers["x-request-id"]
        == "report-viewer-request"
    )

def _task075d_report_payload(
    *,
    session_id: int | None = None,
) -> dict[str, object]:
    return {
        "title": "Task 7.5D report",
        "report_type": "MANAGEMENT_DECISION",
        "session_id": session_id,
        "metadata": {
            "allowed_numbers": ["8"]
        },
        "sections": [
            {
                "section_code": (
                    "management_summary"
                ),
                "title": "管理摘要",
                "content": (
                    "本次共识别 8 项需求。"
                    "[E-075D]"
                ),
                "source_type": (
                    "DETERMINISTIC"
                ),
            }
        ],
        "citations": [
            {
                "citation_id": "E-075D",
                "source_type": (
                    "CALCULATION_SNAPSHOT"
                ),
                "source_name": (
                    "Task 7.5D snapshot"
                ),
            }
        ],
    }


def _create_task075d_report(
    client: TestClient,
    headers: dict[str, str],
) -> int:
    response = client.post(
        "/api/v1/ai/reports",
        headers=headers,
        json=_task075d_report_payload(),
    )
    assert response.status_code == 200
    return int(response.json()["data"]["id"])


def _prepare_task075d_reviewed_report(
    client: TestClient,
    headers: dict[str, str],
) -> int:
    report_id = _create_task075d_report(
        client,
        headers,
    )
    generated = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/generate"
        ),
        headers=headers,
    )
    assert generated.status_code == 200
    validated = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/validate"
        ),
        headers=headers,
    )
    assert validated.status_code == 200
    return report_id


def test_foreign_tenant_cannot_create_report_from_owned_session(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner_headers = internal_auth_headers(
        tenant_id="tenant-report-owner",
        user_id="session-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_headers = internal_auth_headers(
        tenant_id="tenant-report-foreign",
        user_id="foreign-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    created_session = client.post(
        "/api/v1/ai/sessions",
        headers=owner_headers,
        json={"title": "foreign report link"},
    )
    assert created_session.status_code == 200
    ai_session_id = int(
        created_session.json()["data"]["id"]
    )
    before = session.scalar(
        select(func.count(AIReportJob.id))
    )

    isolated_client = TestClient(
        client.app,
        raise_server_exceptions=False,
    )
    response = isolated_client.post(
        "/api/v1/ai/reports",
        headers=foreign_headers,
        json=_task075d_report_payload(
            session_id=ai_session_id,
        ),
    )

    assert response.status_code == 404
    session.expire_all()
    after = session.scalar(
        select(func.count(AIReportJob.id))
    )
    assert after == before


def test_foreign_tenant_cannot_read_report_or_versions(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner_headers = internal_auth_headers(
        tenant_id="tenant-report-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_headers = internal_auth_headers(
        tenant_id="tenant-report-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_task075d_report(
        client,
        owner_headers,
    )

    report = client.get(
        f"/api/v1/ai/reports/{report_id}",
        headers=foreign_headers,
    )
    versions = client.get(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/versions"
        ),
        headers=foreign_headers,
    )

    assert report.status_code == 404
    assert versions.status_code == 404


def test_foreign_tenant_cannot_generate_or_validate_without_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    tenant_id = "tenant-report-owner"
    owner_headers = internal_auth_headers(
        tenant_id=tenant_id,
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_headers = internal_auth_headers(
        tenant_id="tenant-report-foreign",
        user_id="foreign-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    owner_actor = actor_context(
        tenant_id=tenant_id,
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_task075d_report(
        client,
        owner_headers,
    )
    job = ai_report_service.get_job(
        session,
        owner_actor,
        report_id,
    )
    version = ai_report_service.latest_version(
        session,
        owner_actor,
        report_id,
    )
    original_job_status = job.status
    original_version_status = version.status

    generated = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/generate"
        ),
        headers=foreign_headers,
    )
    validated = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/validate"
        ),
        headers=foreign_headers,
    )

    assert generated.status_code == 404
    assert validated.status_code == 404
    session.expire_all()
    job = ai_report_service.get_job(
        session,
        owner_actor,
        report_id,
    )
    version = ai_report_service.latest_version(
        session,
        owner_actor,
        report_id,
    )
    assert job.status is original_job_status
    assert version.status is original_version_status
    assert (
        ai_report_repository.list_sections(
            session,
            tenant_id,
            version.id,
        )
        == []
    )
    assert (
        ai_report_repository
        .list_validation_findings(
            session,
            tenant_id,
            version.id,
        )
        == []
    )


def test_foreign_admin_cannot_finalize_reviewed_report_without_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    tenant_id = "tenant-report-owner"
    owner_headers = internal_auth_headers(
        tenant_id=tenant_id,
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_admin_headers = (
        internal_auth_headers(
            tenant_id="tenant-report-foreign",
            user_id="foreign-admin",
            role=MaintenanceRole.ADMIN,
        )
    )
    owner_actor = actor_context(
        tenant_id=tenant_id,
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = (
        _prepare_task075d_reviewed_report(
            client,
            owner_headers,
        )
    )

    response = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/finalize"
        ),
        headers=foreign_admin_headers,
    )

    assert response.status_code == 404
    session.expire_all()
    job = ai_report_service.get_job(
        session,
        owner_actor,
        report_id,
    )
    version = ai_report_service.latest_version(
        session,
        owner_actor,
        report_id,
    )
    assert (
        job.status
        is AIReportJobStatus.READY_FOR_REVIEW
    )
    assert (
        version.status
        is AIReportVersionStatus.REVIEWED
    )
    assert version.finalized_by is None


def test_contributor_cannot_finalize_reviewed_report_without_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[
        ...,
        ActorContext,
    ],
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    tenant_id = "tenant-report"
    contributor_headers = (
        internal_auth_headers(
            tenant_id=tenant_id,
            user_id="report-contributor",
            role=MaintenanceRole.CONTRIBUTOR,
        )
    )
    actor = actor_context(
        tenant_id=tenant_id,
        user_id="report-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = (
        _prepare_task075d_reviewed_report(
            client,
            contributor_headers,
        )
    )

    response = client.post(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/finalize"
        ),
        headers=contributor_headers,
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    job = ai_report_service.get_job(
        session,
        actor,
        report_id,
    )
    version = ai_report_service.latest_version(
        session,
        actor,
        report_id,
    )
    assert (
        job.status
        is AIReportJobStatus.READY_FOR_REVIEW
    )
    assert (
        version.status
        is AIReportVersionStatus.REVIEWED
    )
    assert version.finalized_by is None


def test_foreign_export_is_404_before_filesystem_and_database_effects(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner_headers = internal_auth_headers(
        tenant_id="tenant-report-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_headers = internal_auth_headers(
        tenant_id="tenant-report-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_task075d_report(
        client,
        owner_headers,
    )
    output_dir = (
        tmp_path
        / "foreign-report-export"
    )
    monkeypatch.setattr(
        (
            "app.services.ai_report_service."
            "get_settings"
        ),
        lambda: SimpleNamespace(
            ai_report_export_dir=str(
                output_dir
            )
        ),
    )
    before = session.scalar(
        select(func.count(AIReportExport.id))
    )

    response = client.get(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/exports/json"
        ),
        headers=foreign_headers,
    )

    assert response.status_code == 404
    assert not output_dir.exists()
    session.expire_all()
    after = session.scalar(
        select(func.count(AIReportExport.id))
    )
    assert after == before


def test_owner_export_persists_tenant_scoped_record(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    tenant_id = "tenant-report"
    contributor_headers = (
        internal_auth_headers(
            tenant_id=tenant_id,
            user_id="report-owner",
            role=MaintenanceRole.CONTRIBUTOR,
        )
    )
    viewer_headers = internal_auth_headers(
        tenant_id=tenant_id,
        user_id="report-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_task075d_report(
        client,
        contributor_headers,
    )
    output_dir = tmp_path / "owner-export"
    monkeypatch.setattr(
        (
            "app.services.ai_report_service."
            "get_settings"
        ),
        lambda: SimpleNamespace(
            ai_report_export_dir=str(
                output_dir
            )
        ),
    )

    response = client.get(
        (
            f"/api/v1/ai/reports/"
            f"{report_id}/exports/json"
        ),
        headers=viewer_headers,
    )

    assert response.status_code == 200
    assert output_dir.is_dir()
    files = list(output_dir.iterdir())
    assert len(files) == 1
    export_row = session.scalar(
        select(AIReportExport)
        .where(
            AIReportExport.tenant_id
            == tenant_id
        )
        .order_by(
            AIReportExport.id.desc()
        )
        .limit(1)
    )
    assert export_row is not None
    assert (
        Path(export_row.file_path)
        == files[0]
    )
    assert export_row.size_bytes == len(
        response.content
    )
