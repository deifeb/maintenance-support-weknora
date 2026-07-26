from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


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
