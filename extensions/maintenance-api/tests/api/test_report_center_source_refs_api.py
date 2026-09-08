from __future__ import annotations

from collections.abc import Callable

from app.models import AIReportJob, AIReportSourceRef, AIReportVersion
from app.models.enums import (
    AIReportJobStatus,
    AIReportSourceType,
    AIReportType,
    AIReportVersionStatus,
)
from app.repositories.ai_session_repository import AISessionRepository
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{tenant_id}-{role.value.lower()}",
        role=role,
    )


def _seed_report_version(
    session: Session,
    *,
    tenant_id: str,
    report_code: str,
    version_number: int,
    sources: list[tuple[AIReportSourceType, str, str]],
) -> AIReportJob:
    job = AIReportJob(
        tenant_id=tenant_id,
        report_code=report_code,
        report_type=AIReportType.MANAGEMENT_DECISION,
        status=AIReportJobStatus.CREATED,
        title=report_code,
        progress_percent=0,
    )
    session.add(job)
    session.flush()
    _seed_version(
        session,
        job=job,
        version_number=version_number,
        sources=sources,
    )
    return job


def _seed_version(
    session: Session,
    *,
    job: AIReportJob,
    version_number: int,
    sources: list[tuple[AIReportSourceType, str, str]],
) -> None:
    version = AIReportVersion(
        tenant_id=job.tenant_id,
        report_job_id=job.id,
        version_number=version_number,
        status=AIReportVersionStatus.DRAFT,
        template_version="1.0",
        content_digest=f"{job.id:064d}"[-64:],
    )
    session.add(version)
    session.flush()
    session.add_all(
        AIReportSourceRef(
            tenant_id=job.tenant_id,
            report_version_id=version.id,
            source_type=source_type,
            source_id=source_id,
            source_version=source_version,
            ordinal=ordinal,
        )
        for ordinal, (source_type, source_id, source_version) in enumerate(sources)
    )
    session.flush()


def test_legacy_create_contract_resolves_session_id(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    source = AISessionRepository().create_session(
        session,
        "tenant-a",
        title="legacy source",
        sensitivity_level="INTERNAL",
    )
    session.commit()

    response = client.post(
        "/api/v1/reports/jobs",
        headers=_headers(internal_auth_headers),
        json={
            "title": "legacy report",
            "report_type": "MANAGEMENT_DECISION",
            "session_id": source.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["report_id"] > 0


def test_foreign_source_is_not_found_before_writing_report_job(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    foreign_source = AISessionRepository().create_session(
        session,
        "tenant-b",
        title="foreign source",
        sensitivity_level="INTERNAL",
    )
    session.commit()
    before = session.scalar(select(func.count(AIReportJob.id)))

    response = client.post(
        "/api/v1/reports/jobs",
        headers=_headers(internal_auth_headers),
        json={
            "title": "foreign source report",
            "report_type": "MANAGEMENT_DECISION",
            "source_refs": [
                {
                    "type": "AI_SESSION",
                    "id": foreign_source.id,
                }
            ],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    session.expire_all()
    assert session.scalar(select(func.count(AIReportJob.id))) == before


def test_source_version_conflict_is_409(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    source = AISessionRepository().create_session(
        session,
        "tenant-a",
        title="versioned source",
        sensitivity_level="INTERNAL",
    )
    session.commit()

    response = client.post(
        "/api/v1/reports/jobs",
        headers=_headers(internal_auth_headers),
        json={
            "title": "stale source report",
            "report_type": "MANAGEMENT_DECISION",
            "source_refs": [
                {
                    "type": "AI_SESSION",
                    "id": source.id,
                    "version": "999",
                }
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_SOURCE_VERSION_CONFLICT"


def test_report_list_filters_only_the_latest_version_source_refs(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    matching = _seed_report_version(
        session,
        tenant_id="tenant-a",
        report_code="AIR-SOURCE-MATCH",
        version_number=1,
        sources=[
            (AIReportSourceType.DEMAND_LIST, "101", "current"),
            (AIReportSourceType.DEMAND_LIST, "101", "old"),
        ],
    )
    historical = _seed_report_version(
        session,
        tenant_id="tenant-a",
        report_code="AIR-SOURCE-HISTORICAL",
        version_number=1,
        sources=[(AIReportSourceType.DEMAND_LIST, "101", "current")],
    )
    _seed_version(
        session,
        job=historical,
        version_number=2,
        sources=[(AIReportSourceType.DEMAND_LIST, "202", "current")],
    )
    other_version = _seed_report_version(
        session,
        tenant_id="tenant-a",
        report_code="AIR-SOURCE-OTHER-VERSION",
        version_number=1,
        sources=[(AIReportSourceType.DEMAND_LIST, "101", "other")],
    )
    session.commit()

    response = client.get(
        "/api/v1/reports",
        headers=_headers(internal_auth_headers, role=MaintenanceRole.VIEWER),
        params={
            "source_type": "DEMAND_LIST",
            "source_id": 101,
            "sort_by": "report_code",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    assert [row["report_id"] for row in response.json()["data"]["items"]] == [
        matching.id,
        other_version.id,
    ]

    narrowed = client.get(
        "/api/v1/reports",
        headers=_headers(internal_auth_headers, role=MaintenanceRole.VIEWER),
        params={
            "source_type": "DEMAND_LIST",
            "source_id": 101,
            "source_version": "current",
        },
    )

    assert narrowed.status_code == 200
    assert [row["report_id"] for row in narrowed.json()["data"]["items"]] == [
        matching.id
    ]
