from app.models import AIReportSection, AIReportVersion
from app.models.enums import AIReportJobStatus, AIReportVersionStatus
from app.schemas.ai_report import AIReportCreateRequest
from app.services.ai_report_service import REPORT_SECTION_DEFINITIONS, ai_report_service


def test_report_service_builds_fixed_skeleton_and_finalizes_valid_report(session) -> None:
    job = ai_report_service.create(
        session,
        AIReportCreateRequest(
            title="维修器材保障分析报告",
            report_type="MANAGEMENT_DECISION",
            metadata={"allowed_numbers": ["8"]},
            sections=[
                {
                    "section_code": "management_summary",
                    "title": "管理摘要",
                    "content": "本次共识别 8 项需求。[E-001]",
                    "source_type": "DETERMINISTIC",
                }
            ],
            citations=[
                {
                    "citation_id": "E-001",
                    "source_type": "CALCULATION_SNAPSHOT",
                    "source_name": "需求计算快照",
                }
            ],
        ),
    )

    version = ai_report_service.generate(session, job.id)
    sections = session.query(AIReportSection).filter_by(report_version_id=version.id).all()
    assert len(sections) == len(REPORT_SECTION_DEFINITIONS) == 17
    assert {row.section_code for row in sections} == {
        code for code, _ in REPORT_SECTION_DEFINITIONS
    }

    findings = ai_report_service.validate(session, job.id)
    assert findings == []
    finalized = ai_report_service.finalize(session, job.id, actor="tester")
    assert finalized.status is AIReportVersionStatus.FINAL
    assert job.status is AIReportJobStatus.FINALIZED
    assert session.get(AIReportVersion, finalized.id).finalized_by == "tester"
