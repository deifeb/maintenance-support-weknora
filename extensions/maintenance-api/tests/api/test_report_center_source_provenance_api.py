from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

from app.models import AIReportJob, AIReportVersion
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _viewer_headers(
    internal_auth_headers: Callable[..., dict[str, str]],
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id="tenant-safe-provenance",
        user_id="safe-provenance-viewer",
        role=MaintenanceRole.VIEWER,
    )


def test_report_detail_exposes_only_public_source_projection(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    job = AIReportJob(
        tenant_id="tenant-safe-provenance",
        report_code="AIR-SAFE-PROVENANCE",
        report_type=AIReportType.MANAGEMENT_DECISION,
        status=AIReportJobStatus.CREATED,
        title="Safe provenance",
        progress_percent=0,
    )
    session.add(job)
    session.flush()
    session.add(
        AIReportVersion(
            tenant_id=job.tenant_id,
            report_job_id=job.id,
            version_number=1,
            status=AIReportVersionStatus.DRAFT,
            template_version="1.0",
            content_digest="a" * 64,
            source_snapshot_json={
                "schema_version": "1.1",
                "capture_mode": "AUTHORITATIVE_CREATE",
                "provenance_completeness": "AUTHORITATIVE",
                "tenant_id": "tenant-id-must-not-leak",
                "provider_token": "provider-token-must-not-leak",
                "sources": [
                    {
                        "type": "AI_SESSION",
                        "id": "42",
                        "version": "7",
                        "lineage_id": "session-42",
                        "digest": "b" * 64,
                        "evidence": {
                            "credential": "credential-must-not-leak"
                        },
                    }
                ],
            },
        )
    )
    session.commit()

    response = client.get(
        f"/api/v1/reports/{job.id}",
        headers=_viewer_headers(internal_auth_headers),
    )

    assert response.status_code == 200
    body = response.text
    for unsafe in (
        "source_snapshot_json",
        "tenant-id-must-not-leak",
        "provider-token-must-not-leak",
        "credential-must-not-leak",
    ):
        assert unsafe not in body
    assert response.json()["data"]["source_versions"] == {
        "capture_mode": "AUTHORITATIVE_CREATE",
        "provenance_completeness": "AUTHORITATIVE",
        "sources": [
            {
                "type": "AI_SESSION",
                "id": "42",
                "version": "7",
                "lineage_id": "session-42",
                "digest": "b" * 64,
            }
        ],
    }


def test_report_export_filenames_remain_versioned(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
    tmp_path,
) -> None:
    job = AIReportJob(
        tenant_id="tenant-safe-provenance",
        report_code="AIR-SAFE-FILENAME",
        report_type=AIReportType.MANAGEMENT_DECISION,
        status=AIReportJobStatus.CREATED,
        title="Safe export filename",
        progress_percent=0,
    )
    session.add(job)
    session.flush()
    session.add(
        AIReportVersion(
            tenant_id=job.tenant_id,
            report_job_id=job.id,
            version_number=3,
            status=AIReportVersionStatus.DRAFT,
            template_version="1.0",
            content_digest="c" * 64,
        )
    )
    session.commit()
    monkeypatch.setattr(
        "app.services.ai_report_service.get_settings",
        lambda: SimpleNamespace(ai_report_export_dir=str(tmp_path)),
    )

    for export_format, extension in (
        ("json", "json"),
        ("markdown", "md"),
        ("docx", "docx"),
    ):
        response = client.get(
            f"/api/v1/reports/{job.id}/exports/{export_format}",
            headers=_viewer_headers(internal_auth_headers),
        )

        assert response.status_code == 200
        assert response.headers["content-disposition"] == (
            f'attachment; filename="AIR-SAFE-FILENAME-v3.{extension}"'
        )
        assert (tmp_path / f"AIR-SAFE-FILENAME-v3.{extension}").is_file()
