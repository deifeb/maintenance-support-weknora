from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AIReportCitation,
    AIReportExport,
    AIReportJob,
    AIReportSection,
    AIReportValidationFinding,
    AIReportVersion,
)
from app.models.enums import (
    AIExportFormat,
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
    AISeverity,
)


class AIReportRepository:
    def create_job(
        self,
        session: Session,
        *,
        title: str,
        report_type: str,
        session_id: int | None = None,
    ) -> AIReportJob:
        row = AIReportJob(
            report_code=f"AIR-{uuid.uuid4().hex[:12].upper()}",
            session_id=session_id,
            report_type=AIReportType(report_type),
            status=AIReportJobStatus.CREATED,
            title=title,
        )
        session.add(row)
        session.flush()
        return row

    def get_job(self, session: Session, report_job_id: int) -> AIReportJob | None:
        return session.get(AIReportJob, report_job_id)

    def list_versions(self, session: Session, report_job_id: int) -> list[AIReportVersion]:
        return list(
            session.scalars(
                select(AIReportVersion)
                .where(AIReportVersion.report_job_id == report_job_id)
                .order_by(AIReportVersion.version_number)
            ).all()
        )

    def latest_version(self, session: Session, report_job_id: int) -> AIReportVersion | None:
        return session.scalar(
            select(AIReportVersion)
            .where(AIReportVersion.report_job_id == report_job_id)
            .order_by(AIReportVersion.version_number.desc())
            .limit(1)
        )

    def create_version(
        self,
        session: Session,
        *,
        report_job_id: int,
        template_version: str,
        content_digest: str,
        metadata: dict[str, Any] | None = None,
        **links: Any,
    ) -> AIReportVersion:
        version = (
            session.scalar(
                select(func.coalesce(func.max(AIReportVersion.version_number), 0)).where(
                    AIReportVersion.report_job_id == report_job_id
                )
            )
            or 0
        )
        row = AIReportVersion(
            report_job_id=report_job_id,
            version_number=int(version) + 1,
            status=AIReportVersionStatus.DRAFT,
            template_version=template_version,
            content_digest=content_digest,
            metadata_json=metadata,
            **links,
        )
        session.add(row)
        session.flush()
        return row

    def clear_version_content(self, session: Session, report_version_id: int) -> None:
        for model in (
            AIReportSection,
            AIReportCitation,
            AIReportValidationFinding,
            AIReportExport,
        ):
            session.execute(delete(model).where(model.report_version_id == report_version_id))
        session.flush()

    def clear_validation_findings(self, session: Session, report_version_id: int) -> None:
        session.execute(
            delete(AIReportValidationFinding).where(
                AIReportValidationFinding.report_version_id == report_version_id
            )
        )
        session.flush()

    def add_section(
        self,
        session: Session,
        *,
        report_version_id: int,
        section_code: str,
        title: str,
        order_index: int,
        content: str,
        source_type: str,
        llm_model_call_id: int | None = None,
    ) -> AIReportSection:
        row = AIReportSection(
            report_version_id=report_version_id,
            section_code=section_code,
            title=title,
            order_index=order_index,
            content=content,
            source_type=source_type,
            llm_model_call_id=llm_model_call_id,
        )
        session.add(row)
        session.flush()
        return row

    def list_sections(self, session: Session, report_version_id: int) -> list[AIReportSection]:
        return list(
            session.scalars(
                select(AIReportSection)
                .where(AIReportSection.report_version_id == report_version_id)
                .order_by(AIReportSection.order_index)
            ).all()
        )

    def add_citation(
        self,
        session: Session,
        *,
        report_version_id: int,
        citation_id: str,
        source_type: str,
        source_name: str,
        **kwargs: Any,
    ) -> AIReportCitation:
        row = AIReportCitation(
            report_version_id=report_version_id,
            citation_id=citation_id,
            source_type=source_type,
            source_name=source_name,
            **kwargs,
        )
        session.add(row)
        session.flush()
        return row

    def list_citations(self, session: Session, report_version_id: int) -> list[AIReportCitation]:
        return list(
            session.scalars(
                select(AIReportCitation)
                .where(AIReportCitation.report_version_id == report_version_id)
                .order_by(AIReportCitation.citation_id)
            ).all()
        )

    def add_validation_finding(
        self,
        session: Session,
        *,
        report_version_id: int,
        code: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
        resolved: bool = False,
    ) -> AIReportValidationFinding:
        row = AIReportValidationFinding(
            report_version_id=report_version_id,
            code=code,
            severity=AISeverity(severity),
            message=message,
            details_json=details,
            resolved=resolved,
        )
        session.add(row)
        session.flush()
        return row

    def list_validation_findings(
        self, session: Session, report_version_id: int
    ) -> list[AIReportValidationFinding]:
        return list(
            session.scalars(
                select(AIReportValidationFinding)
                .where(AIReportValidationFinding.report_version_id == report_version_id)
                .order_by(AIReportValidationFinding.id)
            ).all()
        )

    def add_export(
        self,
        session: Session,
        *,
        report_version_id: int,
        export_format: str,
        file_name: str,
        content_type: str,
        file_path: str | None,
        content_digest: str,
        size_bytes: int,
    ) -> AIReportExport:
        row = AIReportExport(
            report_version_id=report_version_id,
            export_format=AIExportFormat(export_format),
            file_name=file_name,
            content_type=content_type,
            file_path=file_path,
            content_digest=content_digest,
            size_bytes=size_bytes,
        )
        session.add(row)
        session.flush()
        return row


ai_report_repository = AIReportRepository()
