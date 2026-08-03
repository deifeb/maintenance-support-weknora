import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    AIReportExport,
    AIReportJob,
    AIReportSection,
    AIReportVersion,
)
from app.models.enums import (
    AIReportJobStatus,
    AIReportVersionStatus,
)
from app.repositories.ai_session_repository import (
    AISessionRepository,
)
from app.schemas.ai_report import (
    AIReportCreateRequest,
)
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import (
    REPORT_SECTION_DEFINITIONS,
    ai_report_service,
)
from sqlalchemy import func, select


def test_report_service_builds_fixed_skeleton_and_finalizes_valid_report(
    session,
    actor_admin,
) -> None:
    job = ai_report_service.create(
        session,
        actor_admin,
        AIReportCreateRequest(
            title="维修器材保障分析报告",
            report_type=(
                "MANAGEMENT_DECISION"
            ),
            metadata={
                "allowed_numbers": ["8"]
            },
            sections=[
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
            citations=[
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
        ),
    )

    version = ai_report_service.generate(
        session,
        actor_admin,
        job.id,
    )
    sections = (
        session.query(AIReportSection)
        .filter_by(
            report_version_id=version.id
        )
        .all()
    )
    assert (
        len(sections)
        == len(
            REPORT_SECTION_DEFINITIONS
        )
        == 17
    )
    assert {
        row.section_code
        for row in sections
    } == {
        code
        for code, _
        in REPORT_SECTION_DEFINITIONS
    }

    findings = ai_report_service.validate(
        session,
        actor_admin,
        job.id,
    )
    assert findings == []
    finalized = ai_report_service.finalize(
        session,
        actor_admin,
        job.id,
    )
    assert (
        finalized.status
        is AIReportVersionStatus.FINAL
    )
    assert (
        job.status
        is AIReportJobStatus.FINALIZED
    )
    persisted = session.get(
        AIReportVersion,
        finalized.id,
    )
    assert persisted is not None
    assert (
        persisted.finalized_by
        == actor_admin.user_id
    )

def test_report_service_rejects_foreign_linked_session_before_job_write(
    session,
    actor_context,
) -> None:
    owner = actor_context(
        tenant_id="tenant-report-owner",
        user_id="session-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-report-foreign",
        user_id="foreign-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    ai_session = AISessionRepository().create_session(
        session,
        owner.tenant_id,
        title="foreign report link",
        sensitivity_level="INTERNAL",
        created_by=owner.user_id,
    )
    session.commit()
    before = session.scalar(
        select(func.count(AIReportJob.id))
    )

    with pytest.raises(NotFoundError):
        ai_report_service.create(
            session,
            foreign,
            AIReportCreateRequest(
                title="Foreign linked report",
                session_id=ai_session.id,
            ),
        )

    session.rollback()
    after = session.scalar(
        select(func.count(AIReportJob.id))
    )
    assert after == before


def test_report_export_authorizes_before_settings_access(
    session,
    actor_context,
    monkeypatch,
) -> None:
    owner = actor_context(
        tenant_id="tenant-report-owner",
        user_id="report-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = actor_context(
        tenant_id="tenant-report-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )
    job = ai_report_service.create(
        session,
        owner,
        AIReportCreateRequest(
            title="Export authorization order",
        ),
    )
    settings_accessed = False

    def fail_settings_access():
        nonlocal settings_accessed
        settings_accessed = True
        raise AssertionError(
            "settings accessed before report ownership"
        )

    monkeypatch.setattr(
        (
            "app.services.ai_report_service."
            "get_settings"
        ),
        fail_settings_access,
    )

    with pytest.raises(NotFoundError):
        ai_report_service.export(
            session,
            foreign,
            job.id,
            "JSON",
        )

    assert settings_accessed is False
    assert (
        session.scalar(
            select(
                func.count(
                    AIReportExport.id
                )
            )
        )
        == 0
    )

def test_report_service_maps_create_job_ownership_miss_to_not_found(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = actor_context(
        tenant_id="tenant-report",
        user_id="report-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )

    def raise_ownership_miss(*args, **kwargs):
        del args, kwargs
        raise LookupError(
            "AISession 999 was not found"
        )

    monkeypatch.setattr(
        ai_report_service.repository,
        "create_job",
        raise_ownership_miss,
    )

    with pytest.raises(NotFoundError):
        ai_report_service.create(
            session,
            actor,
            AIReportCreateRequest(
                title="Repository ownership miss",
            ),
        )
