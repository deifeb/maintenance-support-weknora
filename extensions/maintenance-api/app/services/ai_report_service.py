from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError, NotFoundError
from app.exporters.ai_report_docx import export_report_docx
from app.exporters.ai_report_json import export_report_json
from app.exporters.ai_report_markdown import export_report_markdown
from app.models import AIReportJob, AIReportVersion
from app.models.enums import AIReportJobStatus, AIReportVersionStatus
from app.repositories.ai_report_repository import ai_report_repository
from app.schemas.ai_report import AIReportCreateRequest
from app.services.ai_report_validation_service import ai_report_validation_service

REPORT_SECTION_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("report_information", "报告基本信息"),
    ("management_summary", "管理摘要"),
    ("mission_and_configuration", "任务场景与装备构型"),
    ("data_and_parameter_sources", "数据与参数来源"),
    ("calculation_method", "需求计算方法"),
    ("calculation_results", "需求计算结果"),
    ("inventory_and_repair_analysis", "库存与修理资源分析"),
    ("gap_and_support_risk", "需求缺口与保障风险"),
    ("review_findings", "智能审查结果"),
    ("model_comparison_and_uncertainty", "模型对比与不确定性"),
    ("support_recommendations", "保障建议"),
    ("decision_items", "需确认与决策事项"),
    ("conclusion", "结论"),
    ("appendix_demand_items", "附录A：器材需求明细"),
    ("appendix_parameters", "附录B：计算参数与模型版本"),
    ("appendix_citations", "附录C：证据和引用"),
    ("appendix_audit", "附录D：审计与确认记录"),
)

_DEFAULT_SECTION_CONTENT = "本章节由确定性报告骨架生成，尚无补充内容。"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AIReportService:
    def create(self, session: Session, payload: AIReportCreateRequest) -> AIReportJob:
        job = ai_report_repository.create_job(
            session,
            title=payload.title,
            report_type=payload.report_type,
            session_id=payload.session_id,
        )
        metadata = dict(payload.metadata)
        metadata["_draft_sections"] = [row.model_dump(mode="json") for row in payload.sections]
        metadata["_draft_citations"] = [row.model_dump(mode="json") for row in payload.citations]
        metadata.setdefault("allowed_numbers", [])
        ai_report_repository.create_version(
            session,
            report_job_id=job.id,
            template_version="1.0",
            content_digest=_digest(metadata),
            metadata=metadata,
            scenario_version_id=payload.scenario_version_id,
            calculation_run_id=payload.calculation_run_id,
            review_run_id=payload.review_run_id,
        )
        session.commit()
        session.refresh(job)
        return job

    def get_job(self, session: Session, report_job_id: int) -> AIReportJob:
        row = ai_report_repository.get_job(session, report_job_id)
        if row is None:
            raise NotFoundError("ai_report_job", report_job_id)
        return row

    def latest_version(self, session: Session, report_job_id: int) -> AIReportVersion:
        self.get_job(session, report_job_id)
        row = ai_report_repository.latest_version(session, report_job_id)
        if row is None:
            raise NotFoundError("ai_report_version", report_job_id)
        return row

    def generate(self, session: Session, report_job_id: int) -> AIReportVersion:
        job = self.get_job(session, report_job_id)
        version = self.latest_version(session, report_job_id)
        job.status = AIReportJobStatus.BUILDING_SKELETON
        job.progress_percent = 10
        session.commit()

        metadata = dict(version.metadata_json or {})
        supplied_sections = {
            str(row["section_code"]): row for row in metadata.get("_draft_sections", [])
        }
        supplied_citations = list(metadata.get("_draft_citations", []))
        section_tables: dict[str, list[dict[str, Any]]] = {}
        section_citations: dict[str, list[str]] = {}

        ai_report_repository.clear_version_content(session, version.id)
        job.status = AIReportJobStatus.GENERATING_SECTIONS
        for index, (section_code, default_title) in enumerate(REPORT_SECTION_DEFINITIONS, 1):
            supplied = supplied_sections.get(section_code, {})
            content = str(supplied.get("content") or _DEFAULT_SECTION_CONTENT)
            title = str(supplied.get("title") or default_title)
            source_type = str(supplied.get("source_type") or "DETERMINISTIC")
            ai_report_repository.add_section(
                session,
                report_version_id=version.id,
                section_code=section_code,
                title=title,
                order_index=index,
                content=content,
                source_type=source_type,
            )
            section_tables[section_code] = list(supplied.get("tables", []))
            section_citations[section_code] = [
                str(value) for value in supplied.get("citations", [])
            ]

        for citation in supplied_citations:
            citation_data = dict(citation)
            citation_id = str(citation_data.pop("citation_id"))
            source_type = str(citation_data.pop("source_type", "WEKNORA_DOCUMENT"))
            source_name = str(citation_data.pop("source_name"))
            ai_report_repository.add_citation(
                session,
                report_version_id=version.id,
                citation_id=citation_id,
                source_type=source_type,
                source_name=source_name,
                **citation_data,
            )

        metadata["_section_tables"] = section_tables
        metadata["_section_citations"] = section_citations
        version.metadata_json = metadata
        report = self.serialize(session, job, version)
        version.content_digest = _digest(report)
        job.status = AIReportJobStatus.VALIDATING_NUMBERS
        job.progress_percent = 75
        session.commit()
        session.refresh(version)
        return version

    def validate(self, session: Session, report_job_id: int):
        job = self.get_job(session, report_job_id)
        version = self.latest_version(session, report_job_id)
        report = self.serialize(session, job, version)
        metadata = dict(version.metadata_json or {})
        allowed_numbers = {str(value) for value in metadata.get("allowed_numbers", [])}
        valid_citations = {str(row["citation_id"]) for row in report["citations"]}

        ai_report_repository.clear_validation_findings(session, version.id)
        drafts = ai_report_validation_service.validate_content(
            sections=report["sections"],
            allowed_numbers=allowed_numbers,
            valid_citation_ids=valid_citations,
        )
        persisted = [
            ai_report_repository.add_validation_finding(
                session,
                report_version_id=version.id,
                code=row.code,
                severity=row.severity,
                message=row.message,
                details=row.details,
                resolved=row.resolved,
            )
            for row in drafts
        ]
        if persisted:
            version.status = AIReportVersionStatus.DRAFT
            job.status = AIReportJobStatus.PARTIALLY_COMPLETED
        else:
            version.status = AIReportVersionStatus.REVIEWED
            job.status = AIReportJobStatus.READY_FOR_REVIEW
        job.progress_percent = 100
        session.commit()
        return persisted

    def finalize(self, session: Session, report_job_id: int, *, actor: str) -> AIReportVersion:
        job = self.get_job(session, report_job_id)
        version = self.latest_version(session, report_job_id)
        findings = ai_report_repository.list_validation_findings(session, version.id)
        unresolved = [row for row in findings if not row.resolved]
        if version.status is not AIReportVersionStatus.REVIEWED or unresolved:
            raise BusinessValidationError(
                "report must pass number and citation validation before finalization",
                code="REPORT_VALIDATION_REQUIRED",
                details={"unresolved_findings": len(unresolved)},
            )
        version.status = AIReportVersionStatus.FINAL
        version.finalized_by = actor
        job.status = AIReportJobStatus.FINALIZED
        session.commit()
        session.refresh(version)
        return version

    def list_versions(self, session: Session, report_job_id: int) -> list[AIReportVersion]:
        self.get_job(session, report_job_id)
        return ai_report_repository.list_versions(session, report_job_id)

    def serialize(
        self,
        session: Session,
        job: AIReportJob,
        version: AIReportVersion,
    ) -> dict[str, Any]:
        metadata = dict(version.metadata_json or {})
        section_tables = metadata.get("_section_tables", {})
        section_citations = metadata.get("_section_citations", {})
        public_metadata = {key: value for key, value in metadata.items() if not key.startswith("_")}
        sections = [
            {
                "section_code": row.section_code,
                "title": row.title,
                "content": row.content,
                "source_type": row.source_type,
                "citations": list(section_citations.get(row.section_code, [])),
                "tables": list(section_tables.get(row.section_code, [])),
            }
            for row in ai_report_repository.list_sections(session, version.id)
        ]
        citations = [
            {
                "citation_id": row.citation_id,
                "source_type": row.source_type,
                "source_name": row.source_name,
                "document_version": row.document_version,
                "page_number": row.page_number,
                "chunk_reference": row.chunk_reference,
                "knowledge_node": row.knowledge_node,
                "database_record_json": row.database_record_json,
            }
            for row in ai_report_repository.list_citations(session, version.id)
        ]
        return {
            "report_id": job.id,
            "report_code": job.report_code,
            "report_type": job.report_type.value,
            "title": job.title,
            "status": version.status.value,
            "version_id": version.id,
            "version_number": version.version_number,
            "template_version": version.template_version,
            "metadata": public_metadata,
            "sections": sections,
            "citations": citations,
        }

    def read(self, session: Session, report_job_id: int) -> dict[str, Any]:
        job = self.get_job(session, report_job_id)
        version = self.latest_version(session, report_job_id)
        report = self.serialize(session, job, version)
        report["job_status"] = job.status.value
        report["progress_percent"] = job.progress_percent
        report["findings"] = [
            {
                "id": row.id,
                "code": row.code,
                "severity": row.severity.value,
                "message": row.message,
                "details": row.details_json,
                "resolved": row.resolved,
            }
            for row in ai_report_repository.list_validation_findings(session, version.id)
        ]
        return report

    def export(
        self, session: Session, report_job_id: int, export_format: str
    ) -> tuple[bytes, str, str]:
        job = self.get_job(session, report_job_id)
        version = self.latest_version(session, report_job_id)
        report = self.serialize(session, job, version)
        normalized = export_format.upper()
        if normalized == "DOCX":
            content = export_report_docx(report)
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            extension = "docx"
        elif normalized == "JSON":
            content = export_report_json(report).encode("utf-8")
            content_type = "application/json; charset=utf-8"
            extension = "json"
        elif normalized in {"MARKDOWN", "MD"}:
            normalized = "MARKDOWN"
            content = export_report_markdown(report).encode("utf-8")
            content_type = "text/markdown; charset=utf-8"
            extension = "md"
        else:
            raise BusinessValidationError(
                "unsupported report export format",
                code="REPORT_EXPORT_FORMAT_INVALID",
                details={"format": export_format},
            )

        file_name = f"{job.report_code}-v{version.version_number}.{extension}"
        output_dir = Path(get_settings().ai_report_export_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / file_name
        output_path.write_bytes(content)
        content_digest = hashlib.sha256(content).hexdigest()
        ai_report_repository.add_export(
            session,
            report_version_id=version.id,
            export_format=normalized,
            file_name=file_name,
            content_type=content_type,
            file_path=str(output_path),
            content_digest=content_digest,
            size_bytes=len(content),
        )
        session.commit()
        return content, content_type, file_name


ai_report_service = AIReportService()
