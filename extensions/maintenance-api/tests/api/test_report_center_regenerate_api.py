from __future__ import annotations

from collections.abc import Callable

from app.models.ai_report import AIReportVersion
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

REGENERATE_PATH = "/api/v1/reports/{report_id}/regenerate"


def _require_regenerate_route(client: TestClient) -> None:
    path_item = client.app.openapi()["paths"].get(
        "/api/v1/reports/{report_id}/regenerate"
    )
    assert (
        path_item is not None
        and "post" in path_item
    ), (
        "C2B RED A01: POST "
        "/api/v1/reports/{report_id}/regenerate is absent"
    )


def _create_generated_report(
    client: TestClient,
    headers: dict[str, str],
) -> int:
    created = client.post(
        "/api/v1/reports/jobs",
        headers=headers,
        json={
            "title": "C2B regenerate API",
            "report_type": "MANAGEMENT_DECISION",
            "metadata": {"allowed_numbers": []},
        },
    )
    assert created.status_code == 200
    report_id = int(created.json()["data"]["report_id"])

    generated = client.post(
        f"/api/v1/ai/reports/{report_id}/generate",
        headers=headers,
    )
    assert generated.status_code == 200
    return report_id


def _version_count(
    session: Session,
    *,
    tenant_id: str,
    report_id: int,
) -> int:
    return int(
        session.scalar(
            select(func.count(AIReportVersion.id)).where(
                AIReportVersion.tenant_id == tenant_id,
                AIReportVersion.report_job_id == report_id,
            )
        )
        or 0
    )


def test_report_center_regenerate_accepts_contributor(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_regenerate_route(client)
    headers = internal_auth_headers(
        tenant_id="tenant-c2b-api",
        user_id="c2b-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_generated_report(client, headers)

    response = client.post(
        REGENERATE_PATH.format(report_id=report_id),
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["report_id"] == report_id
    assert data["latest_version"]["version_number"] == 2
    assert data["latest_version"]["parent_version_id"] is not None


def test_report_center_regenerate_accepts_admin(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_regenerate_route(client)
    headers = internal_auth_headers(
        tenant_id="tenant-c2b-api-admin",
        user_id="c2b-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_generated_report(client, headers)

    response = client.post(
        REGENERATE_PATH.format(report_id=report_id),
        headers=headers,
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["latest_version"]["version_number"]
        == 2
    )


def test_report_center_regenerate_rejects_viewer_without_mutation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_regenerate_route(client)
    tenant_id = "tenant-c2b-viewer"
    contributor = internal_auth_headers(
        tenant_id=tenant_id,
        user_id="c2b-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    viewer = internal_auth_headers(
        tenant_id=tenant_id,
        user_id="c2b-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_generated_report(
        client,
        contributor,
    )
    before = _version_count(
        session,
        tenant_id=tenant_id,
        report_id=report_id,
    )

    response = client.post(
        REGENERATE_PATH.format(report_id=report_id),
        headers=viewer,
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    assert _version_count(
        session,
        tenant_id=tenant_id,
        report_id=report_id,
    ) == before


def test_report_center_regenerate_is_tenant_scoped_before_mutation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_regenerate_route(client)
    owner_tenant = "tenant-c2b-owner"
    owner = internal_auth_headers(
        tenant_id=owner_tenant,
        user_id="c2b-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = internal_auth_headers(
        tenant_id="tenant-c2b-foreign",
        user_id="c2b-foreign",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_generated_report(client, owner)
    before = _version_count(
        session,
        tenant_id=owner_tenant,
        report_id=report_id,
    )

    response = client.post(
        REGENERATE_PATH.format(report_id=report_id),
        headers=foreign,
    )

    assert response.status_code == 404
    session.expire_all()
    assert _version_count(
        session,
        tenant_id=owner_tenant,
        report_id=report_id,
    ) == before


def test_report_center_regenerate_returns_new_latest_version_summary(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_regenerate_route(client)
    headers = internal_auth_headers(
        tenant_id="tenant-c2b-summary",
        user_id="c2b-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_generated_report(client, headers)

    before = client.get(
        f"/api/v1/reports/{report_id}/versions",
        headers=headers,
    )
    assert before.status_code == 200
    assert len(before.json()["data"]) == 1
    v1_id = int(before.json()["data"][0]["id"])

    response = client.post(
        REGENERATE_PATH.format(report_id=report_id),
        headers=headers,
    )

    assert response.status_code == 200
    latest = response.json()["data"]["latest_version"]
    assert latest["version_number"] == 2
    assert latest["parent_version_id"] == v1_id
    assert latest["input_digest"]
    assert latest["generation_mode"] == "RULE_FALLBACK"
    assert latest["generated_at"] is not None
