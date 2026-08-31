from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.exporters.ai_report_docx import (
    export_report_docx,
)
from app.exporters.ai_report_json import (
    export_report_json,
)
from app.exporters.ai_report_markdown import (
    export_report_markdown,
)
from app.models import (
    AIReportJob,
    AIReportVersion,
)
from app.models.enums import (
    AIExecutionMode,
    AIReportJobStatus,
    AIReportVersionStatus,
)
from app.models.mixins import utc_now
from app.repositories.ai_report_repository import (
    AIReportRepository,
    ai_report_repository,
)
from app.schemas.ai_report import (
    AIReportCreateRequest,
)
from app.security.actor import ActorContext
from app.services.ai_report_validation_service import (
    ai_report_validation_service,
)
from app.services.report_version_provenance import (
    build_authoritative_source_snapshot,
    build_legacy_source_snapshot,
    public_source_versions,
    seed_metadata,
    source_snapshot_digest,
)

REPORT_SECTION_DEFINITIONS: tuple[
    tuple[str, str],
    ...,
] = (
    (
        "report_information",
        "报告基本信息",
    ),
    (
        "management_summary",
        "管理摘要",
    ),
    (
        "mission_and_configuration",
        "任务场景与装备构型",
    ),
    (
        "data_and_parameter_sources",
        "数据与参数来源",
    ),
    (
        "calculation_method",
        "需求计算方法",
    ),
    (
        "calculation_results",
        "需求计算结果",
    ),
    (
        "inventory_and_repair_analysis",
        "库存与修理资源分析",
    ),
    (
        "gap_and_support_risk",
        "需求缺口与保障风险",
    ),
    (
        "review_findings",
        "智能审查结果",
    ),
    (
        "model_comparison_and_uncertainty",
        "模型对比与不确定性",
    ),
    (
        "support_recommendations",
        "保障建议",
    ),
    (
        "decision_items",
        "需确认与决策事项",
    ),
    (
        "conclusion",
        "结论",
    ),
    (
        "appendix_demand_items",
        "附录A：器材需求明细",
    ),
    (
        "appendix_parameters",
        "附录B：计算参数与模型版本",
    ),
    (
        "appendix_citations",
        "附录C：证据和引用",
    ),
    (
        "appendix_audit",
        "附录D：审计与确认记录",
    ),
)

_DEFAULT_SECTION_CONTENT = (
    "本章节由确定性报告骨架生成，"
    "尚无补充内容。"
)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AIReportService:
    def __init__(
        self,
        *,
        repository: (
            AIReportRepository | None
        ) = None,
    ) -> None:
        self.repository = (
            repository
            or ai_report_repository
        )

    def create(
        self,
        session: Session,
        actor: ActorContext,
        payload: AIReportCreateRequest,
    ) -> AIReportJob:
        metadata = dict(payload.metadata)
        metadata["_draft_sections"] = [
            row.model_dump(mode="json")
            for row in payload.sections
        ]
        metadata["_draft_citations"] = [
            row.model_dump(mode="json")
            for row in payload.citations
        ]
        metadata.setdefault("allowed_numbers", [])

        try:
            sources = self.repository.load_create_sources_owned(
                session,
                actor.tenant_id,
                session_id=payload.session_id,
                scenario_version_id=payload.scenario_version_id,
                calculation_run_id=payload.calculation_run_id,
                review_run_id=payload.review_run_id,
            )
            job = self.repository.create_job(
                session,
                actor.tenant_id,
                title=payload.title,
                report_type=payload.report_type,
                session_id=payload.session_id,
            )
            source_snapshot = build_authoritative_source_snapshot(
                report_type=payload.report_type,
                template_version="1.0",
                metadata=metadata,
                ai_session=sources["session"],
                scenario_version=sources["scenario_version"],
                calculation_run=sources["calculation_run"],
                calculation=sources["calculation"],
                review_run=sources["review_run"],
            )
            calculation = sources["calculation"]
            inventory_snapshot_at = (
                calculation.inventory_snapshot_at
                if calculation is not None
                else None
            )
            self.repository.create_version(
                session,
                actor.tenant_id,
                report_job_id=job.id,
                template_version="1.0",
                content_digest=_digest(metadata),
                metadata=metadata,
                source_snapshot=source_snapshot,
                input_digest=source_snapshot_digest(
                    source_snapshot
                ),
                inventory_snapshot_at=inventory_snapshot_at,
                created_by=actor.user_id,
                scenario_version_id=payload.scenario_version_id,
                calculation_run_id=payload.calculation_run_id,
                review_run_id=payload.review_run_id,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_report_source",
                "linked",
            ) from exc

        session.commit()
        session.refresh(job)
        return job

    def get_job(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> AIReportJob:
        row = self.repository.get_job(
            session,
            actor.tenant_id,
            report_job_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_report_job",
                report_job_id,
            )
        return row

    def latest_version(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> AIReportVersion:
        self.get_job(
            session,
            actor,
            report_job_id,
        )
        row = self.repository.latest_version(
            session,
            actor.tenant_id,
            report_job_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_report_version",
                report_job_id,
            )
        return row

    def _is_version_generated(
        self,
        session: Session,
        actor: ActorContext,
        version: AIReportVersion,
    ) -> bool:
        if version.generated_at is not None:
            return True
        return bool(
            self.repository.list_sections(
                session,
                actor.tenant_id,
                version.id,
            )
        )

    def _generate_version(
        self,
        session: Session,
        actor: ActorContext,
        job: AIReportJob,
        version: AIReportVersion,
    ) -> AIReportVersion:
        job.status = AIReportJobStatus.BUILDING_SKELETON
        job.progress_percent = 10

        metadata = dict(version.metadata_json or {})
        supplied_sections = {
            str(row["section_code"]): row
            for row in metadata.get(
                "_draft_sections",
                [],
            )
        }
        supplied_citations = list(
            metadata.get(
                "_draft_citations",
                [],
            )
        )
        section_tables: dict[
            str,
            list[dict[str, Any]],
        ] = {}
        section_citations: dict[
            str,
            list[str],
        ] = {}

        self.repository.clear_version_content(
            session,
            actor.tenant_id,
            version.id,
        )
        job.status = AIReportJobStatus.GENERATING_SECTIONS

        for index, (
            section_code,
            default_title,
        ) in enumerate(
            REPORT_SECTION_DEFINITIONS,
            1,
        ):
            supplied = supplied_sections.get(
                section_code,
                {},
            )
            content = str(
                supplied.get("content")
                or _DEFAULT_SECTION_CONTENT
            )
            title = str(
                supplied.get("title")
                or default_title
            )
            source_type = str(
                supplied.get("source_type")
                or "DETERMINISTIC"
            )
            self.repository.add_section(
                session,
                actor.tenant_id,
                report_version_id=version.id,
                section_code=section_code,
                title=title,
                order_index=index,
                content=content,
                source_type=source_type,
            )
            section_tables[section_code] = list(
                supplied.get(
                    "tables",
                    [],
                )
            )
            section_citations[section_code] = [
                str(value)
                for value in supplied.get(
                    "citations",
                    [],
                )
            ]

        for citation in supplied_citations:
            citation_data = dict(citation)
            citation_id = str(
                citation_data.pop("citation_id")
            )
            source_type = str(
                citation_data.pop(
                    "source_type",
                    "WEKNORA_DOCUMENT",
                )
            )
            source_name = str(
                citation_data.pop("source_name")
            )
            self.repository.add_citation(
                session,
                actor.tenant_id,
                report_version_id=version.id,
                citation_id=citation_id,
                source_type=source_type,
                source_name=source_name,
                **citation_data,
            )

        metadata["_section_tables"] = section_tables
        metadata["_section_citations"] = section_citations
        version.metadata_json = metadata

        # serialize() reads sections/citations through repository helpers
        # that intentionally use populate_existing=True for tenant-safe
        # ownership checks. Record generation provenance only after those
        # reads so unsaved values cannot be refreshed back to legacy NULL.
        report = self.serialize(
            session,
            actor,
            job,
            version,
        )
        version.content_digest = _digest(report)
        version.generation_mode = (
            AIExecutionMode.RULE_FALLBACK
        )
        version.generated_at = utc_now()
        job.status = AIReportJobStatus.VALIDATING_NUMBERS
        job.progress_percent = 75
        session.flush()
        return version

    def generate(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> AIReportVersion:
        job = self.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.latest_version(
            session,
            actor,
            report_job_id,
        )

        if version.status is AIReportVersionStatus.FINAL:
            raise BusinessValidationError(
                "final report version is immutable",
                code="REPORT_FINAL_VERSION_IMMUTABLE",
            )

        if self._is_version_generated(
            session,
            actor,
            version,
        ):
            raise BusinessValidationError(
                "report version has already been generated",
                code="REPORT_VERSION_ALREADY_GENERATED",
            )

        try:
            result = self._generate_version(
                session,
                actor,
                job,
                version,
            )
            session.commit()
            session.refresh(result)
            return result
        except Exception:
            session.rollback()
            raise

    def regenerate(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> AIReportVersion:
        job = self.repository.get_job_for_update(
            session,
            actor.tenant_id,
            report_job_id,
        )
        if job is None:
            raise NotFoundError(
                "ai_report_job",
                report_job_id,
            )

        parent = self.repository.latest_version(
            session,
            actor.tenant_id,
            report_job_id,
        )
        if parent is None:
            raise NotFoundError(
                "ai_report_version",
                report_job_id,
            )

        if not self._is_version_generated(
            session,
            actor,
            parent,
        ):
            raise BusinessValidationError(
                "latest report version is not ready for regeneration",
                code="REPORT_REGENERATE_SOURCE_NOT_READY",
            )

        metadata = seed_metadata(parent.metadata_json)

        if (
            parent.source_snapshot_json is not None
            and parent.input_digest
        ):
            source_snapshot = copy.deepcopy(
                parent.source_snapshot_json
            )
            input_digest = parent.input_digest
        else:
            source_snapshot = build_legacy_source_snapshot(
                job,
                parent,
            )
            input_digest = source_snapshot_digest(
                source_snapshot
            )

        job.status = AIReportJobStatus.CREATED
        job.progress_percent = 0
        job.error_code = None
        job.error_message = None

        # create_version() re-checks report-job ownership with
        # populate_existing=True. Flush the reset execution state first so
        # that ownership refresh cannot resurrect a prior failure payload.
        session.flush()

        child = self.repository.create_version(
            session,
            actor.tenant_id,
            report_job_id=job.id,
            parent_version_id=parent.id,
            template_version=parent.template_version,
            content_digest=_digest(metadata),
            metadata=metadata,
            source_snapshot=source_snapshot,
            input_digest=input_digest,
            inventory_snapshot_at=parent.inventory_snapshot_at,
            prompt_versions=copy.deepcopy(
                parent.prompt_versions_json
            ),
            created_by=actor.user_id,
            scenario_version_id=parent.scenario_version_id,
            calculation_run_id=parent.calculation_run_id,
            review_run_id=parent.review_run_id,
        )

        session.commit()
        session.refresh(child)

        try:
            result = self._generate_version(
                session,
                actor,
                job,
                child,
            )
            session.commit()
            session.refresh(result)
            return result
        except Exception:
            session.rollback()
            failed_job = self.repository.get_job(
                session,
                actor.tenant_id,
                report_job_id,
            )
            if failed_job is not None:
                failed_job.status = AIReportJobStatus.FAILED
                failed_job.error_code = "REPORT_GENERATION_FAILED"
                failed_job.error_message = "Report generation failed"
                session.commit()
            raise

    def validate(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ):
        job = self.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.latest_version(
            session,
            actor,
            report_job_id,
        )

        if version.status is AIReportVersionStatus.FINAL:
            raise BusinessValidationError(
                "final report version is immutable",
                code="REPORT_FINAL_VERSION_IMMUTABLE",
            )

        if not self._is_version_generated(
            session,
            actor,
            version,
        ):
            raise BusinessValidationError(
                "report generation is required before validation",
                code="REPORT_GENERATION_REQUIRED",
            )

        report = self.serialize(
            session,
            actor,
            job,
            version,
        )
        metadata = dict(version.metadata_json or {})
        allowed_numbers = {
            str(value)
            for value in metadata.get(
                "allowed_numbers",
                [],
            )
        }
        valid_citations = {
            str(row["citation_id"])
            for row in report["citations"]
        }

        self.repository.clear_validation_findings(
            session,
            actor.tenant_id,
            version.id,
        )
        drafts = (
            ai_report_validation_service
            .validate_content(
                sections=report["sections"],
                allowed_numbers=allowed_numbers,
                valid_citation_ids=valid_citations,
            )
        )
        persisted = [
            self.repository.add_validation_finding(
                session,
                actor.tenant_id,
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

    def finalize(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> AIReportVersion:
        job = self.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.latest_version(
            session,
            actor,
            report_job_id,
        )
        findings = (
            self.repository
            .list_validation_findings(
                session,
                actor.tenant_id,
                version.id,
            )
        )
        unresolved = [
            row
            for row in findings
            if not row.resolved
        ]
        if (
            version.status
            is not AIReportVersionStatus
            .REVIEWED
            or unresolved
        ):
            raise BusinessValidationError(
                (
                    "report must pass number "
                    "and citation validation "
                    "before finalization"
                ),
                code=(
                    "REPORT_VALIDATION_REQUIRED"
                ),
                details={
                    "unresolved_findings": (
                        len(unresolved)
                    )
                },
            )
        version.status = (
            AIReportVersionStatus.FINAL
        )
        version.finalized_by = actor.user_id
        job.status = (
            AIReportJobStatus.FINALIZED
        )
        session.commit()
        session.refresh(version)
        return version

    def list_versions(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> list[AIReportVersion]:
        self.get_job(
            session,
            actor,
            report_job_id,
        )
        return self.repository.list_versions(
            session,
            actor.tenant_id,
            report_job_id,
        )

    def serialize(
        self,
        session: Session,
        actor: ActorContext,
        job: AIReportJob,
        version: AIReportVersion,
    ) -> dict[str, Any]:
        metadata = dict(version.metadata_json or {})
        section_tables = metadata.get(
            "_section_tables",
            {},
        )
        section_citations = metadata.get(
            "_section_citations",
            {},
        )
        public_metadata = {
            key: value
            for key, value in metadata.items()
            if not key.startswith("_")
        }
        sections = [
            {
                "section_code": row.section_code,
                "title": row.title,
                "content": row.content,
                "source_type": row.source_type,
                "citations": list(
                    section_citations.get(
                        row.section_code,
                        [],
                    )
                ),
                "tables": list(
                    section_tables.get(
                        row.section_code,
                        [],
                    )
                ),
            }
            for row in self.repository.list_sections(
                session,
                actor.tenant_id,
                version.id,
            )
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
            for row in self.repository.list_citations(
                session,
                actor.tenant_id,
                version.id,
            )
        ]
        return {
            "report_id": job.id,
            "report_code": job.report_code,
            "report_type": job.report_type.value,
            "title": job.title,
            "status": version.status.value,
            "version_id": version.id,
            "version_number": version.version_number,
            "parent_version_id": version.parent_version_id,
            "template_version": version.template_version,
            "input_digest": version.input_digest,
            "generation_mode": (
                version.generation_mode.value
                if version.generation_mode is not None
                else None
            ),
            "generated_at": (
                version.generated_at.isoformat()
                if version.generated_at is not None
                else None
            ),
            "source_versions": public_source_versions(
                version.source_snapshot_json
            ),
            "metadata": public_metadata,
            "sections": sections,
            "citations": citations,
        }

    def read(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> dict[str, Any]:
        job = self.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.latest_version(
            session,
            actor,
            report_job_id,
        )
        report = self.serialize(
            session,
            actor,
            job,
            version,
        )
        report["job_status"] = (
            job.status.value
        )
        report["progress_percent"] = (
            job.progress_percent
        )
        report["findings"] = [
            {
                "id": row.id,
                "code": row.code,
                "severity": (
                    row.severity.value
                ),
                "message": row.message,
                "details": row.details_json,
                "resolved": row.resolved,
            }
            for row
            in self.repository
            .list_validation_findings(
                session,
                actor.tenant_id,
                version.id,
            )
        ]
        return report

    def export(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
        export_format: str,
    ) -> tuple[bytes, str, str]:
        job = self.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.latest_version(
            session,
            actor,
            report_job_id,
        )
        report = self.serialize(
            session,
            actor,
            job,
            version,
        )
        normalized = export_format.upper()
        if normalized == "DOCX":
            content = export_report_docx(
                report
            )
            content_type = (
                "application/vnd."
                "openxmlformats-officedocument."
                "wordprocessingml.document"
            )
            extension = "docx"
        elif normalized == "JSON":
            content = export_report_json(
                report
            ).encode("utf-8")
            content_type = (
                "application/json; "
                "charset=utf-8"
            )
            extension = "json"
        elif normalized in {
            "MARKDOWN",
            "MD",
        }:
            normalized = "MARKDOWN"
            content = export_report_markdown(
                report
            ).encode("utf-8")
            content_type = (
                "text/markdown; "
                "charset=utf-8"
            )
            extension = "md"
        else:
            raise BusinessValidationError(
                (
                    "unsupported report "
                    "export format"
                ),
                code=(
                    "REPORT_EXPORT_FORMAT_INVALID"
                ),
                details={
                    "format": export_format
                },
            )

        file_name = (
            f"{job.report_code}-"
            f"v{version.version_number}."
            f"{extension}"
        )
        output_dir = Path(
            get_settings()
            .ai_report_export_dir
        )
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        output_path = (
            output_dir / file_name
        )
        output_path.write_bytes(content)
        content_digest = hashlib.sha256(
            content
        ).hexdigest()
        self.repository.add_export(
            session,
            actor.tenant_id,
            report_version_id=version.id,
            export_format=normalized,
            file_name=file_name,
            content_type=content_type,
            file_path=str(output_path),
            content_digest=content_digest,
            size_bytes=len(content),
        )
        session.commit()
        return (
            content,
            content_type,
            file_name,
        )


ai_report_service = AIReportService()
