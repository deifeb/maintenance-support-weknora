from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AIModelCall,
    AIReportCitation,
    AIReportExport,
    AIReportJob,
    AIReportSection,
    AIReportValidationFinding,
    AIReportVersion,
    AIReviewRun,
    AISession,
    DemandCalculationRun,
    DemandScenarioVersion,
)
from app.models.enums import (
    AIExportFormat,
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
    AISeverity,
)
from app.repositories.base import tenant_loader_criteria

ModelT = TypeVar("ModelT")


def _owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT | None:
    return session.scalar(
        select(model)
        .options(tenant_loader_criteria(tenant_id))
        .execution_options(populate_existing=True)
        .where(
            model.id == identifier,
            model.tenant_id == tenant_id,
        )
    )


def _require_owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT:
    row = _owned(
        session,
        tenant_id,
        model,
        identifier,
    )
    if row is None:
        raise LookupError(
            f"{model.__name__} {identifier} not found"
        )
    return row


class AIReportRepository:
    def require_create_sources_owned(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int | None = None,
        scenario_version_id: int | None = None,
        calculation_run_id: int | None = None,
        review_run_id: int | None = None,
    ) -> None:
        linked_sources = (
            (AISession, session_id),
            (
                DemandScenarioVersion,
                scenario_version_id,
            ),
            (
                DemandCalculationRun,
                calculation_run_id,
            ),
            (AIReviewRun, review_run_id),
        )
        for model, identifier in linked_sources:
            if identifier is not None:
                _require_owned(
                    session,
                    tenant_id,
                    model,
                    identifier,
                )

    def create_job(
        self,
        session: Session,
        tenant_id: str,
        *,
        title: str,
        report_type: str,
        session_id: int | None = None,
    ) -> AIReportJob:
        if session_id is not None:
            _require_owned(
                session,
                tenant_id,
                AISession,
                session_id,
            )
        row = AIReportJob(
            tenant_id=tenant_id,
            report_code=(
                f"AIR-{uuid.uuid4().hex[:12].upper()}"
            ),
            session_id=session_id,
            report_type=AIReportType(report_type),
            status=AIReportJobStatus.CREATED,
            title=title,
        )
        session.add(row)
        session.flush()
        return row

    def get_job(
        self,
        session: Session,
        tenant_id: str,
        report_job_id: int,
    ) -> AIReportJob | None:
        return _owned(
            session,
            tenant_id,
            AIReportJob,
            report_job_id,
        )

    def list_versions(
        self,
        session: Session,
        tenant_id: str,
        report_job_id: int,
    ) -> list[AIReportVersion]:
        _require_owned(
            session,
            tenant_id,
            AIReportJob,
            report_job_id,
        )
        return list(
            session.scalars(
                select(AIReportVersion)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIReportVersion.tenant_id == tenant_id,
                    AIReportVersion.report_job_id
                    == report_job_id,
                )
                .order_by(
                    AIReportVersion.version_number
                )
            ).all()
        )

    def latest_version(
        self,
        session: Session,
        tenant_id: str,
        report_job_id: int,
    ) -> AIReportVersion | None:
        _require_owned(
            session,
            tenant_id,
            AIReportJob,
            report_job_id,
        )
        return session.scalar(
            select(AIReportVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AIReportVersion.tenant_id == tenant_id,
                AIReportVersion.report_job_id
                == report_job_id,
            )
            .order_by(
                AIReportVersion.version_number.desc()
            )
            .limit(1)
        )

    def get_version(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> AIReportVersion | None:
        return _owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )

    def create_version(
        self,
        session: Session,
        tenant_id: str,
        *,
        report_job_id: int,
        template_version: str,
        content_digest: str,
        metadata: dict[str, Any] | None = None,
        **links: Any,
    ) -> AIReportVersion:
        _require_owned(
            session,
            tenant_id,
            AIReportJob,
            report_job_id,
        )
        link_models = {
            "scenario_version_id": (
                DemandScenarioVersion
            ),
            "calculation_run_id": (
                DemandCalculationRun
            ),
            "review_run_id": AIReviewRun,
        }
        clean_links = {
            key: links[key]
            for key in link_models
            if key in links
        }
        for key, model in link_models.items():
            identifier = clean_links.get(key)
            if identifier is not None:
                _require_owned(
                    session,
                    tenant_id,
                    model,
                    int(identifier),
                )
        version = (
            session.scalar(
                select(
                    func.coalesce(
                        func.max(
                            AIReportVersion.version_number
                        ),
                        0,
                    )
                ).where(
                    AIReportVersion.tenant_id
                    == tenant_id,
                    AIReportVersion.report_job_id
                    == report_job_id,
                )
            )
            or 0
        )
        row = AIReportVersion(
            tenant_id=tenant_id,
            report_job_id=report_job_id,
            version_number=int(version) + 1,
            status=AIReportVersionStatus.DRAFT,
            template_version=template_version,
            content_digest=content_digest,
            metadata_json=metadata,
            **clean_links,
        )
        session.add(row)
        session.flush()
        return row

    def clear_version_content(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> None:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        for model in (
            AIReportSection,
            AIReportCitation,
            AIReportValidationFinding,
            AIReportExport,
        ):
            session.execute(
                delete(model).where(
                    model.tenant_id == tenant_id,
                    model.report_version_id
                    == report_version_id,
                )
            )
        session.flush()

    def clear_validation_findings(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> None:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        session.execute(
            delete(AIReportValidationFinding).where(
                AIReportValidationFinding.tenant_id
                == tenant_id,
                AIReportValidationFinding.report_version_id
                == report_version_id,
            )
        )
        session.flush()

    def add_section(
        self,
        session: Session,
        tenant_id: str,
        *,
        report_version_id: int,
        section_code: str,
        title: str,
        order_index: int,
        content: str,
        source_type: str,
        llm_model_call_id: int | None = None,
    ) -> AIReportSection:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        if llm_model_call_id is not None:
            _require_owned(
                session,
                tenant_id,
                AIModelCall,
                llm_model_call_id,
            )
        row = AIReportSection(
            tenant_id=tenant_id,
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

    def list_sections(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> list[AIReportSection]:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        return list(
            session.scalars(
                select(AIReportSection)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIReportSection.tenant_id == tenant_id,
                    AIReportSection.report_version_id
                    == report_version_id,
                )
                .order_by(AIReportSection.order_index)
            ).all()
        )

    def add_citation(
        self,
        session: Session,
        tenant_id: str,
        *,
        report_version_id: int,
        citation_id: str,
        source_type: str,
        source_name: str,
        **kwargs: Any,
    ) -> AIReportCitation:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        clean = {
            key: value
            for key, value in kwargs.items()
            if key not in {
                "tenant_id",
                "report_version_id",
            }
        }
        row = AIReportCitation(
            tenant_id=tenant_id,
            report_version_id=report_version_id,
            citation_id=citation_id,
            source_type=source_type,
            source_name=source_name,
            **clean,
        )
        session.add(row)
        session.flush()
        return row

    def list_citations(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> list[AIReportCitation]:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        return list(
            session.scalars(
                select(AIReportCitation)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIReportCitation.tenant_id == tenant_id,
                    AIReportCitation.report_version_id
                    == report_version_id,
                )
                .order_by(AIReportCitation.citation_id)
            ).all()
        )

    def add_validation_finding(
        self,
        session: Session,
        tenant_id: str,
        *,
        report_version_id: int,
        code: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
        resolved: bool = False,
    ) -> AIReportValidationFinding:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        row = AIReportValidationFinding(
            tenant_id=tenant_id,
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
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> list[AIReportValidationFinding]:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        return list(
            session.scalars(
                select(AIReportValidationFinding)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIReportValidationFinding.tenant_id
                    == tenant_id,
                    AIReportValidationFinding.report_version_id
                    == report_version_id,
                )
                .order_by(
                    AIReportValidationFinding.id
                )
            ).all()
        )

    def add_export(
        self,
        session: Session,
        tenant_id: str,
        *,
        report_version_id: int,
        export_format: str,
        file_name: str,
        content_type: str,
        file_path: str | None,
        content_digest: str,
        size_bytes: int,
    ) -> AIReportExport:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        row = AIReportExport(
            tenant_id=tenant_id,
            report_version_id=report_version_id,
            export_format=AIExportFormat(
                export_format
            ),
            file_name=file_name,
            content_type=content_type,
            file_path=file_path,
            content_digest=content_digest,
            size_bytes=size_bytes,
        )
        session.add(row)
        session.flush()
        return row

    def get_export(
        self,
        session: Session,
        tenant_id: str,
        export_id: int,
    ) -> AIReportExport | None:
        return _owned(
            session,
            tenant_id,
            AIReportExport,
            export_id,
        )


ai_report_repository = AIReportRepository()
