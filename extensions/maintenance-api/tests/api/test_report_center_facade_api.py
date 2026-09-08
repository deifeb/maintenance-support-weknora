from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from app.models import AIReportExport
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _headers(
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
    *,
    tenant_id: str,
    user_id: str,
    role: MaintenanceRole,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
    )


def _create_ai_report(
    client: TestClient,
    headers: dict[str, str],
    *,
    title: str = "C2A existing authority report",
) -> int:
    response = client.post(
        "/api/v1/ai/reports",
        headers=headers,
        json={
            "title": title,
            "report_type": (
                "MANAGEMENT_DECISION"
            ),
        },
    )
    assert response.status_code == 200
    return int(
        response.json()["data"]["id"]
    )


def test_report_center_jobs_create_facade_accepts_contributor(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="c2a-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )

    response = client.post(
        "/api/v1/reports/jobs",
        headers=contributor,
        json={
            "title": "C2A top-level report",
            "report_type": (
                "MANAGEMENT_DECISION"
            ),
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["report_id"] > 0
    assert data["job_status"] == "CREATED"
    assert (
        data["latest_version"][
            "version_number"
        ]
        == 1
    )


def test_report_center_jobs_create_requires_contributor(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    viewer = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="c2a-viewer",
        role=MaintenanceRole.VIEWER,
    )

    response = client.post(
        "/api/v1/reports/jobs",
        headers=viewer,
        json={"title": "viewer create"},
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_report_center_jobs_create_rejects_tenant_override(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-a",
        user_id="c2a-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )

    response = client.post(
        "/api/v1/reports/jobs",
        headers=contributor,
        json={
            "title": "tenant override",
            "tenant_id": "tenant-c2a-b",
        },
    )

    assert response.status_code == 422


def test_report_center_jobs_create_rejects_unsupported_report_type(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="c2a-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )

    response = client.post(
        "/api/v1/reports/jobs",
        headers=contributor,
        json={
            "title": "unsupported type",
            "report_type": "ALLOCATION_PLAN",
        },
    )

    assert response.status_code == 422


def test_report_center_job_status_is_compact_and_tenant_scoped(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_ai_report(
        client,
        owner,
    )

    response = client.get(
        f"/api/v1/reports/jobs/{report_id}",
        headers=owner,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
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
    }.isdisjoint(data)

    foreign_response = client.get(
        f"/api/v1/reports/jobs/{report_id}",
        headers=foreign,
    )
    assert foreign_response.status_code == 404


def test_report_center_detail_facade_matches_public_ai_detail(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_ai_report(
        client,
        owner,
    )
    authoritative = client.get(
        f"/api/v1/ai/reports/{report_id}",
        headers=owner,
    )
    assert authoritative.status_code == 200

    response = client.get(
        f"/api/v1/reports/{report_id}",
        headers=owner,
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]
        == authoritative.json()["data"]
    )
    foreign_response = client.get(
        f"/api/v1/reports/{report_id}",
        headers=foreign,
    )
    assert foreign_response.status_code == 404


def test_report_center_versions_facade_is_tenant_scoped(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_ai_report(
        client,
        owner,
    )

    response = client.get(
        (
            f"/api/v1/reports/{report_id}"
            "/versions"
        ),
        headers=owner,
    )

    assert response.status_code == 200
    versions = response.json()["data"]
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["status"] == "DRAFT"

    foreign_response = client.get(
        (
            f"/api/v1/reports/{report_id}"
            "/versions"
        ),
        headers=foreign,
    )
    assert foreign_response.status_code == 404


def test_report_center_export_facade_preserves_authority_and_tenant_safety(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_ai_report(
        client,
        owner,
    )
    output_dir = tmp_path / "c2a-api-export"
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

    foreign_response = client.get(
        (
            f"/api/v1/reports/{report_id}"
            "/exports/json"
        ),
        headers=foreign,
    )
    assert foreign_response.status_code == 404
    assert not output_dir.exists()
    session.expire_all()
    assert session.scalar(
        select(func.count(AIReportExport.id))
    ) == before

    owner_response = client.get(
        (
            f"/api/v1/reports/{report_id}"
            "/exports/json"
        ),
        headers=owner,
    )

    assert owner_response.status_code == 200
    assert owner_response.content.startswith(
        b"{"
    )
    assert owner_response.headers[
        "content-type"
    ].startswith("application/json")
    assert "attachment;" in owner_response.headers[
        "content-disposition"
    ]
    assert ".json" in owner_response.headers[
        "content-disposition"
    ]
    session.expire_all()
    assert session.scalar(
        select(func.count(AIReportExport.id))
    ) == before + 1


def test_report_center_export_facade_rejects_invalid_format(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    owner = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_ai_report(
        client,
        owner,
    )

    response = client.get(
        (
            f"/api/v1/reports/{report_id}"
            "/exports/exe"
        ),
        headers=owner,
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "REPORT_EXPORT_FORMAT_INVALID"
    )


def test_c2a_keeps_committed_report_list_facade_green(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    viewer = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="c2a-viewer",
        role=MaintenanceRole.VIEWER,
    )

    response = client.get(
        "/api/v1/reports",
        headers=viewer,
    )

    assert response.status_code == 200
    assert set(response.json()["data"]) == {
        "items",
        "page",
        "page_size",
        "total",
        "pages",
    }


def test_c2a_keeps_existing_ai_report_authority_unchanged(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2a",
        user_id="c2a-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_ai_report(
        client,
        contributor,
    )

    response = client.get(
        f"/api/v1/ai/reports/{report_id}",
        headers=contributor,
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["report_id"]
        == report_id
    )
