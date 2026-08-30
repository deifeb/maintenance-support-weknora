from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.session import engine
from app.models import AIReportJob, AIReportVersion
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from app.repositories.ai_session_repository import (
    AISessionRepository,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session


def _seed_report(
    session: Session,
    *,
    tenant_id: str,
    report_code: str,
    title: str,
    report_type: AIReportType = AIReportType.DEMAND_CALCULATION,
    job_status: AIReportJobStatus = AIReportJobStatus.CREATED,
    session_id: int | None = None,
    progress_percent: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
    created_at: datetime | None = None,
    versions: list[dict[str, Any]] | None = None,
) -> AIReportJob:
    job = AIReportJob(
        tenant_id=tenant_id,
        report_code=report_code,
        session_id=session_id,
        report_type=report_type,
        status=job_status,
        title=title,
        progress_percent=progress_percent,
        error_code=error_code,
        error_message=error_message,
    )
    if created_at is not None:
        job.created_at = created_at
        job.updated_at = created_at
    session.add(job)
    session.flush()

    for index, payload in enumerate(versions or (), start=1):
        version_created_at = payload.get(
            "created_at",
            created_at or datetime.now(timezone.utc),
        )
        version = AIReportVersion(
            tenant_id=tenant_id,
            report_job_id=job.id,
            version_number=int(
                payload.get("version_number", index)
            ),
            status=payload.get(
                "status",
                AIReportVersionStatus.DRAFT,
            ),
            scenario_version_id=payload.get(
                "scenario_version_id"
            ),
            calculation_run_id=payload.get(
                "calculation_run_id"
            ),
            review_run_id=payload.get("review_run_id"),
            inventory_snapshot_at=payload.get(
                "inventory_snapshot_at"
            ),
            template_version=str(
                payload.get("template_version", "1.0")
            ),
            prompt_versions_json=payload.get(
                "prompt_versions_json"
            ),
            content_digest=str(
                payload.get(
                    "content_digest",
                    f"{job.id:064d}"[-64:],
                )
            ),
            metadata_json=payload.get("metadata_json"),
            created_by=payload.get("created_by"),
            reviewed_by=payload.get("reviewed_by"),
            finalized_by=payload.get("finalized_by"),
        )
        version.created_at = version_created_at
        version.updated_at = version_created_at
        session.add(version)

    session.flush()
    return job


def _viewer_headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    tenant_id: str = "tenant-a",
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id="report-center-viewer",
        role=MaintenanceRole.VIEWER,
    )


def _get(
    client: TestClient,
    headers: dict[str, str],
    query: str = "",
):
    suffix = f"?{query}" if query else ""
    return client.get(
        f"/api/v1/reports{suffix}",
        headers=headers,
    )


def test_report_list_is_tenant_scoped_and_returns_compact_latest_summary(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    local = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-LOCAL-001",
        title="Local report",
        progress_percent=42,
        error_code="REPORT_PARTIAL",
        error_message="private internal detail",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
                "metadata_json": {
                    "private": "metadata-only-value"
                },
            }
        ],
    )
    foreign = _seed_report(
        session,
        tenant_id="tenant-b",
        report_code="AIR-FOREIGN-001",
        title="Foreign report",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
            }
        ],
    )
    session.commit()

    response = _get(
        client,
        _viewer_headers(internal_auth_headers),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    ids = [row["report_id"] for row in data["items"]]
    assert local.id in ids
    assert foreign.id not in ids

    item = next(
        row
        for row in data["items"]
        if row["report_id"] == local.id
    )
    assert item["report_code"] == "AIR-LOCAL-001"
    assert item["title"] == "Local report"
    assert item["report_type"] == "DEMAND_CALCULATION"
    assert item["job_status"] == "CREATED"
    assert item["progress_percent"] == 42
    assert item["error_code"] == "REPORT_PARTIAL"
    assert item["latest_version"]["version_number"] == 1
    assert item["latest_version"]["status"] == "FINAL"

    forbidden = {
        "sections",
        "citations",
        "findings",
        "validation_findings",
        "metadata",
        "metadata_json",
        "error_message",
        "file_path",
    }
    assert forbidden.isdisjoint(item)
    assert forbidden.isdisjoint(item["latest_version"])


def test_report_list_empty_query_returns_empty_page_data(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    response = _get(
        client,
        _viewer_headers(internal_auth_headers),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "pages": 0,
    }


def test_report_list_default_order_and_pagination_are_deterministic(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    base = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    jobs = []
    for index in range(5):
        created_at = base + timedelta(minutes=index)
        jobs.append(
            _seed_report(
                session,
                tenant_id="tenant-a",
                report_code=f"AIR-PAGE-{index}",
                title=f"Page report {index}",
                created_at=created_at,
                versions=[
                    {
                        "version_number": 1,
                        "status": AIReportVersionStatus.DRAFT,
                        "created_at": created_at,
                    }
                ],
            )
        )
    session.commit()

    headers = _viewer_headers(internal_auth_headers)
    page1 = _get(
        client,
        headers,
        "page=1&page_size=2",
    )
    page2 = _get(
        client,
        headers,
        "page=2&page_size=2",
    )

    assert page1.status_code == 200
    assert page2.status_code == 200
    data1 = page1.json()["data"]
    data2 = page2.json()["data"]
    assert data1["page"] == 1
    assert data1["page_size"] == 2
    assert data1["total"] == 5
    assert data1["pages"] == 3
    assert [
        row["report_id"] for row in data1["items"]
    ] == [jobs[4].id, jobs[3].id]
    assert [
        row["report_id"] for row in data2["items"]
    ] == [jobs[2].id, jobs[1].id]


def test_report_list_keyword_searches_code_and_title_only(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    code_match = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-CODE-NEEDLE",
        title="Ordinary title",
        error_message="not-the-private-needle",
        versions=[
            {
                "metadata_json": {
                    "private": "not-the-private-needle"
                }
            }
        ],
    )
    title_match = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-OTHER",
        title="Title needle report",
        versions=[{}],
    )
    _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-PRIVATE",
        title="No public match",
        error_message="private-metadata-only-value",
        versions=[
            {
                "metadata_json": {
                    "private": "private-metadata-only-value"
                }
            }
        ],
    )
    session.commit()

    headers = _viewer_headers(internal_auth_headers)

    by_code = _get(
        client,
        headers,
        "keyword=CODE-NEEDLE",
    )
    assert by_code.status_code == 200
    assert [
        row["report_id"]
        for row in by_code.json()["data"]["items"]
    ] == [code_match.id]

    by_title = _get(
        client,
        headers,
        "keyword=Title%20needle",
    )
    assert by_title.status_code == 200
    assert [
        row["report_id"]
        for row in by_title.json()["data"]["items"]
    ] == [title_match.id]

    private_only = _get(
        client,
        headers,
        "keyword=private-metadata-only-value",
    )
    assert private_only.status_code == 200
    assert private_only.json()["data"]["items"] == []


def test_report_list_report_type_and_job_status_filters_are_exact(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    demand = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-DEMAND",
        title="Demand",
        report_type=AIReportType.DEMAND_CALCULATION,
        job_status=AIReportJobStatus.CREATED,
        versions=[{}],
    )
    inventory_failed = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-INVENTORY",
        title="Inventory",
        report_type=AIReportType.INVENTORY_GAP,
        job_status=AIReportJobStatus.FAILED,
        versions=[{}],
    )
    _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-MGMT",
        title="Management",
        report_type=AIReportType.MANAGEMENT_DECISION,
        job_status=AIReportJobStatus.FINALIZED,
        versions=[{}],
    )
    session.commit()

    headers = _viewer_headers(internal_auth_headers)

    report_type = _get(
        client,
        headers,
        "report_type=DEMAND_CALCULATION",
    )
    assert report_type.status_code == 200
    assert [
        row["report_id"]
        for row in report_type.json()["data"]["items"]
    ] == [demand.id]

    job_status = _get(
        client,
        headers,
        "job_status=FAILED",
    )
    assert job_status.status_code == 200
    assert [
        row["report_id"]
        for row in job_status.json()["data"]["items"]
    ] == [inventory_failed.id]


def test_report_list_version_status_means_latest_version_status(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    older_final_latest_draft = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-OLD-FINAL",
        title="Old final",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
            },
            {
                "version_number": 2,
                "status": AIReportVersionStatus.DRAFT,
            },
        ],
    )
    latest_final = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-NEW-FINAL",
        title="New final",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
            }
        ],
    )
    session.commit()

    response = _get(
        client,
        _viewer_headers(internal_auth_headers),
        "version_status=FINAL",
    )

    assert response.status_code == 200
    ids = [
        row["report_id"]
        for row in response.json()["data"]["items"]
    ]
    assert latest_final.id in ids
    assert older_final_latest_draft.id not in ids


def test_report_list_session_and_source_filters_are_exact(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    ai_session = AISessionRepository().create_session(
        session,
        "tenant-a",
        title="Report source session",
        sensitivity_level="INTERNAL",
        created_by="report-center-test",
    )
    linked = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-SESSION-LINKED",
        title="Session linked",
        session_id=ai_session.id,
        versions=[{}],
    )
    _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-UNLINKED",
        title="Unlinked",
        versions=[{}],
    )
    session.commit()

    headers = _viewer_headers(internal_auth_headers)

    by_session = _get(
        client,
        headers,
        f"session_id={ai_session.id}",
    )
    assert by_session.status_code == 200
    assert [
        row["report_id"]
        for row in by_session.json()["data"]["items"]
    ] == [linked.id]

    for query_name in (
        "scenario_version_id",
        "calculation_run_id",
        "review_run_id",
    ):
        response = _get(
            client,
            headers,
            f"{query_name}=999999",
        )
        assert response.status_code == 200
        assert response.json()["data"]["items"] == [], (
            f"{query_name} must filter persisted source "
            "columns rather than being ignored"
        )


def test_report_list_rejects_unbounded_or_unsupported_query_values(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = _viewer_headers(internal_auth_headers)

    for query in (
        "page=0",
        "page_size=0",
        "page_size=201",
        "sort_by=metadata_json",
        "sort_order=sideways",
        "report_type=MODEL_COMPARISON",
        "job_status=UNKNOWN_STATUS",
        "version_status=UNKNOWN_STATUS",
    ):
        response = _get(client, headers, query)
        assert response.status_code == 422, query


def test_report_list_supports_allowlisted_sort_only(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    alpha = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-Z",
        title="Alpha",
        versions=[{}],
    )
    beta = _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-A",
        title="Beta",
        versions=[{}],
    )
    session.commit()

    response = _get(
        client,
        _viewer_headers(internal_auth_headers),
        "sort_by=report_code&sort_order=asc",
    )

    assert response.status_code == 200
    assert [
        row["report_id"]
        for row in response.json()["data"]["items"]
    ] == [beta.id, alpha.id]


def test_report_list_latest_version_loading_is_not_per_row_n_plus_one(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    headers = _viewer_headers(internal_auth_headers)

    def count_version_selects() -> int:
        statements: list[str] = []

        def before_cursor_execute(
            _conn,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ):
            normalized = statement.lower()
            if (
                normalized.lstrip().startswith("select")
                and "ai_report_versions" in normalized
            ):
                statements.append(normalized)

        event.listen(
            engine,
            "before_cursor_execute",
            before_cursor_execute,
        )
        try:
            response = _get(client, headers)
        finally:
            event.remove(
                engine,
                "before_cursor_execute",
                before_cursor_execute,
            )
        assert response.status_code == 200
        return len(statements)

    _seed_report(
        session,
        tenant_id="tenant-a",
        report_code="AIR-N1-0",
        title="N1 zero",
        versions=[{}],
    )
    session.commit()
    one_row_count = count_version_selects()

    for index in range(1, 6):
        _seed_report(
            session,
            tenant_id="tenant-a",
            report_code=f"AIR-N1-{index}",
            title=f"N1 {index}",
            versions=[{}],
        )
    session.commit()
    six_row_count = count_version_selects()

    assert six_row_count <= one_row_count + 1, (
        "latest-version SELECT count must remain constant "
        "with row count; per-row latest_version() calls "
        "are forbidden"
    )
