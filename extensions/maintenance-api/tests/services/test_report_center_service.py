from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime, timezone
from typing import Any

from app.models import AIReportJob, AIReportVersion
from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)


def _load_report_center():
    service_spec = importlib.util.find_spec(
        "app.services.report_center_service"
    )
    schema_spec = importlib.util.find_spec(
        "app.schemas.report_center"
    )
    assert service_spec is not None, (
        "05-5C1 RED: app.services.report_center_service "
        "does not exist yet"
    )
    assert schema_spec is not None, (
        "05-5C1 RED: app.schemas.report_center "
        "does not exist yet"
    )

    service_module = importlib.import_module(
        "app.services.report_center_service"
    )
    schema_module = importlib.import_module(
        "app.schemas.report_center"
    )
    return (
        service_module.ReportCenterQueryService(),
        schema_module.ReportListQuery,
    )


def _seed_report(
    session,
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
        row = AIReportVersion(
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
        row.created_at = version_created_at
        row.updated_at = version_created_at
        session.add(row)

    session.flush()
    return job


def test_report_center_service_returns_empty_page(
    session,
    actor_viewer,
) -> None:
    service, Query = _load_report_center()

    result = service.list(
        session,
        actor_viewer,
        Query(),
    )

    assert result.model_dump(mode="json") == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "pages": 0,
    }


def test_report_center_service_is_tenant_scoped_and_compact(
    session,
    actor_viewer,
) -> None:
    service, Query = _load_report_center()
    local = _seed_report(
        session,
        tenant_id=actor_viewer.tenant_id,
        report_code="AIR-LOCAL",
        title="Local report",
        progress_percent=55,
        error_code="REPORT_PARTIAL",
        error_message="private internal stack text",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
                "metadata_json": {
                    "private": "metadata-only-secret"
                },
            }
        ],
    )
    _seed_report(
        session,
        tenant_id="tenant-foreign",
        report_code="AIR-FOREIGN",
        title="Foreign report",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
            }
        ],
    )
    session.commit()

    result = service.list(
        session,
        actor_viewer,
        Query(),
    )

    assert result.total == 1
    assert len(result.items) == 1
    item = result.items[0].model_dump(mode="json")
    assert item["report_id"] == local.id
    assert item["report_code"] == "AIR-LOCAL"
    assert item["job_status"] == AIReportJobStatus.CREATED.value
    assert item["progress_percent"] == 55
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


def test_report_center_service_filters_on_latest_version_status(
    session,
    actor_viewer,
) -> None:
    service, Query = _load_report_center()
    older_final_latest_draft = _seed_report(
        session,
        tenant_id=actor_viewer.tenant_id,
        report_code="AIR-OLDER-FINAL",
        title="Older final latest draft",
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
        tenant_id=actor_viewer.tenant_id,
        report_code="AIR-LATEST-FINAL",
        title="Latest final",
        versions=[
            {
                "version_number": 1,
                "status": AIReportVersionStatus.FINAL,
            }
        ],
    )
    session.commit()

    result = service.list(
        session,
        actor_viewer,
        Query(
            version_status=AIReportVersionStatus.FINAL,
        ),
    )

    ids = [row.report_id for row in result.items]
    assert latest_final.id in ids
    assert older_final_latest_draft.id not in ids
