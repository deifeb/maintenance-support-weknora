from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Sequence, TypeVar

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AIModelCall,
    AIReportCitation,
    AIReportExport,
    AIReportJob,
    AIReportSection,
    AIReportSourceRef,
    AIReportValidationFinding,
    AIReportVersion,
    AIReviewRun,
    AISession,
    DemandCalculation,
    DemandCalculationRun,
    DemandScenarioVersion,
)
from app.models.enums import (
    AIExecutionMode,
    AIExportFormat,
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
    AISeverity,
)
from app.repositories.base import tenant_loader_criteria

if TYPE_CHECKING:
    from app.services.report_source_policy import ReportSourceRecord

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
    def load_create_sources_owned(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int | None = None,
        scenario_version_id: int | None = None,
        calculation_run_id: int | None = None,
        review_run_id: int | None = None,
    ) -> dict[str, Any | None]:
        ai_session = (
            _require_owned(
                session,
                tenant_id,
                AISession,
                session_id,
            )
            if session_id is not None
            else None
        )
        scenario_version = (
            _require_owned(
                session,
                tenant_id,
                DemandScenarioVersion,
                scenario_version_id,
            )
            if scenario_version_id is not None
            else None
        )
        calculation_run = (
            _require_owned(
                session,
                tenant_id,
                DemandCalculationRun,
                calculation_run_id,
            )
            if calculation_run_id is not None
            else None
        )
        calculation = None
        if calculation_run is not None:
            calculation = _require_owned(
                session,
                tenant_id,
                DemandCalculation,
                calculation_run.calculation_id,
            )

        review_run = (
            _require_owned(
                session,
                tenant_id,
                AIReviewRun,
                review_run_id,
            )
            if review_run_id is not None
            else None
        )
        if review_run is not None:
            if review_run.session_id is not None:
                _require_owned(
                    session,
                    tenant_id,
                    AISession,
                    review_run.session_id,
                )
            if review_run.scenario_version_id is not None:
                _require_owned(
                    session,
                    tenant_id,
                    DemandScenarioVersion,
                    review_run.scenario_version_id,
                )
            if review_run.calculation_run_id is not None:
                linked_run = _require_owned(
                    session,
                    tenant_id,
                    DemandCalculationRun,
                    review_run.calculation_run_id,
                )
                _require_owned(
                    session,
                    tenant_id,
                    DemandCalculation,
                    linked_run.calculation_id,
                )

        return {
            "session": ai_session,
            "scenario_version": scenario_version,
            "calculation_run": calculation_run,
            "calculation": calculation,
            "review_run": review_run,
        }

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
        self.load_create_sources_owned(
            session,
            tenant_id,
            session_id=session_id,
            scenario_version_id=scenario_version_id,
            calculation_run_id=calculation_run_id,
            review_run_id=review_run_id,
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

    def get_job_for_update(
        self,
        session: Session,
        tenant_id: str,
        report_job_id: int,
    ) -> AIReportJob | None:
        return session.scalar(
            select(AIReportJob)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AIReportJob.id == report_job_id,
                AIReportJob.tenant_id == tenant_id,
            )
            .with_for_update()
        )

    def list_report_center_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        report_type: AIReportType | None = None,
        job_status: AIReportJobStatus | None = None,
        version_status: AIReportVersionStatus | None = None,
        session_id: int | None = None,
        scenario_version_id: int | None = None,
        calculation_run_id: int | None = None,
        review_run_id: int | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[
        list[tuple[AIReportJob, AIReportVersion | None]],
        int,
    ]:
        latest_number = (
            select(
                AIReportVersion.report_job_id.label(
                    "report_job_id"
                ),
                func.max(
                    AIReportVersion.version_number
                ).label("latest_version_number"),
            )
            .where(AIReportVersion.tenant_id == tenant_id)
            .group_by(AIReportVersion.report_job_id)
            .subquery()
        )

        latest_join = and_(
            AIReportVersion.tenant_id == tenant_id,
            AIReportVersion.report_job_id
            == AIReportJob.id,
            AIReportVersion.version_number
            == latest_number.c.latest_version_number,
        )

        conditions = [AIReportJob.tenant_id == tenant_id]
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            conditions.append(
                or_(
                    AIReportJob.report_code.ilike(pattern),
                    AIReportJob.title.ilike(pattern),
                )
            )
        if report_type is not None:
            conditions.append(
                AIReportJob.report_type == report_type
            )
        if job_status is not None:
            conditions.append(AIReportJob.status == job_status)
        if session_id is not None:
            conditions.append(AIReportJob.session_id == session_id)
        if version_status is not None:
            conditions.append(
                AIReportVersion.status == version_status
            )
        if scenario_version_id is not None:
            conditions.append(
                AIReportVersion.scenario_version_id
                == scenario_version_id
            )
        if calculation_run_id is not None:
            conditions.append(
                AIReportVersion.calculation_run_id
                == calculation_run_id
            )
        if review_run_id is not None:
            conditions.append(
                AIReportVersion.review_run_id == review_run_id
            )

        sort_columns = {
            "created_at": AIReportJob.created_at,
            "report_code": AIReportJob.report_code,
            "title": AIReportJob.title,
            "report_type": AIReportJob.report_type,
            "job_status": AIReportJob.status,
        }
        if sort_by not in sort_columns:
            raise ValueError("unsupported sort_by")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("unsupported sort_order")

        sort_column = sort_columns[sort_by]
        direction = (
            sort_column.asc
            if sort_order == "asc"
            else sort_column.desc
        )
        tie_direction = (
            AIReportJob.id.asc()
            if sort_order == "asc"
            else AIReportJob.id.desc()
        )

        count_statement = (
            select(func.count(AIReportJob.id))
            .select_from(AIReportJob)
            .outerjoin(
                latest_number,
                latest_number.c.report_job_id
                == AIReportJob.id,
            )
            .outerjoin(AIReportVersion, latest_join)
            .where(*conditions)
        )
        total = int(session.scalar(count_statement) or 0)

        statement = (
            select(AIReportJob, AIReportVersion)
            .outerjoin(
                latest_number,
                latest_number.c.report_job_id
                == AIReportJob.id,
            )
            .outerjoin(AIReportVersion, latest_join)
            .where(*conditions)
            .order_by(direction(), tie_direction)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(populate_existing=True)
        )
        rows = session.execute(statement).all()
        return [
            (job, version)
            for job, version in rows
        ], total

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
        parent_version_id: int | None = None,
        source_snapshot: dict[str, Any] | None = None,
        input_digest: str | None = None,
        generation_mode: AIExecutionMode | str | None = None,
        generated_at: datetime | None = None,
        inventory_snapshot_at: datetime | None = None,
        prompt_versions: dict[str, str] | None = None,
        created_by: str | None = None,
        **links: Any,
    ) -> AIReportVersion:
        _require_owned(
            session,
            tenant_id,
            AIReportJob,
            report_job_id,
        )
        if parent_version_id is not None:
            parent = _require_owned(
                session,
                tenant_id,
                AIReportVersion,
                parent_version_id,
            )
            if parent.report_job_id != report_job_id:
                raise LookupError(
                    "report version parent belongs to another report job"
                )

        link_models = {
            "scenario_version_id": DemandScenarioVersion,
            "calculation_run_id": DemandCalculationRun,
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
                        func.max(AIReportVersion.version_number),
                        0,
                    )
                ).where(
                    AIReportVersion.tenant_id == tenant_id,
                    AIReportVersion.report_job_id == report_job_id,
                )
            )
            or 0
        )
        normalized_mode = (
            AIExecutionMode(generation_mode)
            if generation_mode is not None
            else None
        )
        row = AIReportVersion(
            tenant_id=tenant_id,
            report_job_id=report_job_id,
            parent_version_id=parent_version_id,
            source_snapshot_json=source_snapshot,
            input_digest=input_digest,
            generation_mode=normalized_mode,
            generated_at=generated_at,
            version_number=int(version) + 1,
            status=AIReportVersionStatus.DRAFT,
            inventory_snapshot_at=inventory_snapshot_at,
            template_version=template_version,
            prompt_versions_json=prompt_versions,
            content_digest=content_digest,
            metadata_json=metadata,
            created_by=created_by,
            **clean_links,
        )
        session.add(row)
        session.flush()
        return row

    def create_source_refs(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
        records: Sequence[ReportSourceRecord],
    ) -> list[AIReportSourceRef]:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        records = tuple(records)
        record_keys = {
            (
                record.source_type,
                record.source_id,
                record.source_version,
            )
            for record in records
        }
        existing_keys = set(
            session.execute(
                select(
                    AIReportSourceRef.source_type,
                    AIReportSourceRef.source_id,
                    AIReportSourceRef.source_version,
                ).where(
                    AIReportSourceRef.tenant_id == tenant_id,
                    AIReportSourceRef.report_version_id
                    == report_version_id,
                )
            ).tuples()
        )
        if (
            len(record_keys) != len(records)
            or record_keys.intersection(existing_keys)
        ):
            raise ValueError("duplicate report source reference")
        rows = [
            AIReportSourceRef(
                tenant_id=tenant_id,
                report_version_id=report_version_id,
                source_type=record.source_type,
                source_id=record.source_id,
                source_version=record.source_version,
                source_lineage_id=record.source_lineage_id,
                source_digest=record.source_digest,
                ordinal=ordinal,
            )
            for ordinal, record in enumerate(records)
        ]
        session.add_all(rows)
        session.flush()
        return rows

    def list_source_refs(
        self,
        session: Session,
        tenant_id: str,
        report_version_id: int,
    ) -> list[AIReportSourceRef]:
        _require_owned(
            session,
            tenant_id,
            AIReportVersion,
            report_version_id,
        )
        return list(
            session.scalars(
                select(AIReportSourceRef)
                .options(tenant_loader_criteria(tenant_id))
                .where(
                    AIReportSourceRef.tenant_id == tenant_id,
                    AIReportSourceRef.report_version_id
                    == report_version_id,
                )
                .order_by(AIReportSourceRef.ordinal)
            ).all()
        )

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
