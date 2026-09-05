from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import datetime
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
from app.services.report_source_policy import (
    ReportSourceRecord,
    build_source_records,
)
from app.services.report_source_service import ResolvedReportSources
from app.services.report_template_registry import get_template
from app.services.report_version_provenance import (
    build_authoritative_source_snapshot,
    build_legacy_source_snapshot,
    public_source_versions,
    seed_metadata,
    source_snapshot_digest,
)

_DEFAULT_SECTION_CONTENT = "本章节由确定性报告骨架生成，尚无补充内容。"
_PUBLIC_CITATION_FIELDS = (
    "citation_id",
    "source_type",
    "source_name",
    "document_version",
    "page_number",
    "chunk_reference",
    "knowledge_node",
)
_SENSITIVE_METADATA_KEY_PARTS = (
    "tenant",
    "internal",
    "credential",
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "jwt",
    "evidence",
    "path",
    "directory",
    "file_path",
)
_SENSITIVE_SECTION_STRING_PARTS = (
    "tenant",
    "jwt",
    "token",
    "credential",
    "secret",
    "password",
    "passwd",
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "database_record",
    "source_snapshot",
)
_COMPACT_JWT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?P<token>[A-Za-z0-9_-]+(?:={0,2})?\."
    r"[A-Za-z0-9_-]+(?:={0,2})?\."
    r"[A-Za-z0-9_-]+(?:={0,2})?)"
    r"(?![A-Za-z0-9_-])"
)
_OMITTED_METADATA_VALUE = object()


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sensitive_metadata_key(key: Any) -> bool:
    if not isinstance(key, str) or key.startswith("_"):
        return True
    normalized = key.lower()
    return any(
        part in normalized
        for part in _SENSITIVE_METADATA_KEY_PARTS
    )


def _is_path_like(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.startswith(("/", "\\\\", "file://"))
        or (
            len(normalized) >= 3
            and normalized[1] == ":"
            and normalized[2] in ("/", "\\")
        )
    )


def _public_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _public_string_value(value)
    if isinstance(value, list):
        return [
            projected
            for item in value
            if (
                projected := _public_metadata_value(item)
            )
            is not _OMITTED_METADATA_VALUE
        ]
    if isinstance(value, dict):
        return {
            key: projected
            for key, item in value.items()
            if not _is_sensitive_metadata_key(key)
            and (
                projected := _public_metadata_value(item)
            )
            is not _OMITTED_METADATA_VALUE
        }
    return _OMITTED_METADATA_VALUE


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: projected
        for key, value in metadata.items()
        if not _is_sensitive_metadata_key(key)
        and (
            projected := _public_metadata_value(value)
        )
        is not _OMITTED_METADATA_VALUE
    }


def _contains_compact_jwt(value: str) -> bool:
    for match in _COMPACT_JWT_PATTERN.finditer(value):
        header_segment = match.group("token").split(".", 1)[0]
        padding = "=" * (-len(header_segment) % 4)
        try:
            header = json.loads(
                base64.urlsafe_b64decode(
                    header_segment + padding
                )
            )
        except (UnicodeDecodeError, ValueError):
            continue
        if (
            isinstance(header, dict)
            and isinstance(header.get("alg"), str)
        ):
            return True
    return False


def _public_string_value(value: str) -> str | object:
    normalized = value.casefold()
    if (
        _is_path_like(value)
        or _contains_compact_jwt(value)
        or any(
            part in normalized
            for part in _SENSITIVE_SECTION_STRING_PARTS
        )
    ):
        return _OMITTED_METADATA_VALUE
    return value


def _public_section_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if not isinstance(value, str):
        return _OMITTED_METADATA_VALUE
    return _public_string_value(value)


def _public_table_cells(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [
        ""
        if (
            projected := _public_section_scalar(item)
        )
        is _OMITTED_METADATA_VALUE
        else projected
        for item in value
    ]


def _public_section_table(table: Any) -> dict[str, Any] | None:
    if not isinstance(table, dict):
        return None
    projected: dict[str, Any] = {}
    if "title" in table:
        title = _public_section_scalar(table["title"])
        if title is not _OMITTED_METADATA_VALUE:
            projected["title"] = title
    if "columns" in table:
        projected["columns"] = _public_table_cells(
            table["columns"]
        )
    if "rows" in table and isinstance(table["rows"], list):
        projected["rows"] = [
            _public_table_cells(row)
            for row in table["rows"]
            if isinstance(row, list)
        ]
    return projected or None


def _public_section_tables(
    section_tables: Any,
    section_code: str,
) -> list[dict[str, Any]]:
    if not isinstance(section_tables, dict):
        return []
    tables = section_tables.get(section_code)
    if not isinstance(tables, list):
        return []
    return [
        table
        for item in tables
        if (
            table := _public_section_table(item)
        )
        is not None
    ]


def _public_section_citations(
    section_citations: Any,
    section_code: str,
) -> list[str]:
    if not isinstance(section_citations, dict):
        return []
    citations = section_citations.get(section_code)
    if not isinstance(citations, list):
        return []
    return [
        citation
        for value in citations
        if isinstance(value, str)
        and isinstance(
            citation := _public_section_scalar(value),
            str,
        )
    ]


def _public_citation(citation: Any) -> dict[str, Any]:
    return {
        field: getattr(citation, field)
        for field in _PUBLIC_CITATION_FIELDS
    }


class AIReportService:
    def __init__(
        self,
        *,
        repository: (AIReportRepository | None) = None,
    ) -> None:
        self.repository = repository or ai_report_repository

    def create(
        self,
        session: Session,
        actor: ActorContext,
        payload: AIReportCreateRequest,
        resolved_sources: ResolvedReportSources | None = None,
    ) -> AIReportJob:
        template = get_template(payload.report_type)
        metadata = dict(payload.metadata)
        metadata["_draft_sections"] = [row.model_dump(mode="json") for row in payload.sections]
        metadata["_draft_citations"] = [row.model_dump(mode="json") for row in payload.citations]
        metadata.setdefault("allowed_numbers", [])
        sources_are_pre_resolved = resolved_sources is not None

        try:
            if resolved_sources is None:
                sources = self.repository.load_create_sources_owned(
                    session,
                    actor.tenant_id,
                    session_id=payload.session_id,
                    scenario_version_id=payload.scenario_version_id,
                    calculation_run_id=payload.calculation_run_id,
                    review_run_id=payload.review_run_id,
                )
                source_records = build_source_records(
                    ai_session=sources["session"],
                    scenario_version=sources["scenario_version"],
                    calculation_run=sources["calculation_run"],
                    calculation=sources["calculation"],
                    review_run=sources["review_run"],
                )
                session_id = payload.session_id
                scenario_version_id = payload.scenario_version_id
                calculation_run_id = payload.calculation_run_id
                review_run_id = payload.review_run_id
                calculation = sources["calculation"]
                inventory_snapshot_at = (
                    calculation.inventory_snapshot_at if calculation is not None else None
                )
            else:
                source_records = resolved_sources.records
                session_id = resolved_sources.session_id
                scenario_version_id = resolved_sources.scenario_version_id
                calculation_run_id = resolved_sources.calculation_run_id
                review_run_id = resolved_sources.review_run_id
                calculation_record = next(
                    (
                        record
                        for record in source_records
                        if record.source_type.value == "CALCULATION_RUN"
                    ),
                    None,
                )
                inventory_snapshot_at = (
                    calculation_record.evidence.get("inventory_snapshot_at")
                    if calculation_record is not None
                    else None
                )
                if isinstance(inventory_snapshot_at, str):
                    inventory_snapshot_at = datetime.fromisoformat(
                        inventory_snapshot_at
                    )
            job = self.repository.create_job(
                session,
                actor.tenant_id,
                title=payload.title,
                report_type=payload.report_type,
                session_id=(None if sources_are_pre_resolved else session_id),
            )
            if sources_are_pre_resolved:
                job.session_id = session_id
                session.flush()
            source_snapshot = build_authoritative_source_snapshot(
                report_type=payload.report_type,
                template_version=template.version,
                metadata=metadata,
                source_records=source_records,
            )
            version = self.repository.create_version(
                session,
                actor.tenant_id,
                report_job_id=job.id,
                template_version=template.version,
                content_digest=_digest(metadata),
                metadata=metadata,
                source_snapshot=source_snapshot,
                input_digest=source_snapshot_digest(source_snapshot),
                inventory_snapshot_at=inventory_snapshot_at,
                created_by=actor.user_id,
                scenario_version_id=(
                    None if sources_are_pre_resolved else scenario_version_id
                ),
                calculation_run_id=(
                    None if sources_are_pre_resolved else calculation_run_id
                ),
                review_run_id=(None if sources_are_pre_resolved else review_run_id),
            )
            if sources_are_pre_resolved:
                version.scenario_version_id = scenario_version_id
                version.calculation_run_id = calculation_run_id
                version.review_run_id = review_run_id
                session.flush()
            self.repository.create_source_refs(
                session,
                actor.tenant_id,
                version.id,
                source_records,
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

        for index, section in enumerate(
            get_template(
                job.report_type,
                version.template_version,
            ).sections,
            1,
        ):
            section_code = section.code
            default_title = section.title
            supplied = supplied_sections.get(
                section_code,
                {},
            )
            content = str(supplied.get("content") or _DEFAULT_SECTION_CONTENT)
            title = str(supplied.get("title") or default_title)
            source_type = str(supplied.get("source_type") or "DETERMINISTIC")
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
            citation_id = str(citation_data.pop("citation_id"))
            source_type = str(
                citation_data.pop(
                    "source_type",
                    "WEKNORA_DOCUMENT",
                )
            )
            source_name = str(citation_data.pop("source_name"))
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
        version.generation_mode = AIExecutionMode.RULE_FALLBACK
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

        job.error_code = None
        job.error_message = None

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

        if parent.source_snapshot_json is not None and parent.input_digest:
            source_snapshot = copy.deepcopy(parent.source_snapshot_json)
            input_digest = parent.input_digest
        else:
            source_snapshot = build_legacy_source_snapshot(
                job,
                parent,
            )
            input_digest = source_snapshot_digest(source_snapshot)

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
            prompt_versions=copy.deepcopy(parent.prompt_versions_json),
            created_by=actor.user_id,
            scenario_version_id=parent.scenario_version_id,
            calculation_run_id=parent.calculation_run_id,
            review_run_id=parent.review_run_id,
        )
        parent_refs = self.repository.list_source_refs(
            session,
            actor.tenant_id,
            parent.id,
        )
        self.repository.create_source_refs(
            session,
            actor.tenant_id,
            child.id,
            tuple(
                ReportSourceRecord(
                    source_type=row.source_type,
                    source_id=row.source_id,
                    source_version=row.source_version,
                    source_lineage_id=row.source_lineage_id,
                    source_digest=row.source_digest,
                    evidence=copy.deepcopy(
                        getattr(row, "evidence_json", {})
                    ),
                )
                for row in parent_refs
            ),
            ordinals=tuple(row.ordinal for row in parent_refs),
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
        valid_citations = {str(row["citation_id"]) for row in report["citations"]}

        self.repository.clear_validation_findings(
            session,
            actor.tenant_id,
            version.id,
        )
        drafts = ai_report_validation_service.validate_content(
            sections=report["sections"],
            allowed_numbers=allowed_numbers,
            valid_citation_ids=valid_citations,
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
        findings = self.repository.list_validation_findings(
            session,
            actor.tenant_id,
            version.id,
        )
        unresolved = [row for row in findings if not row.resolved]
        if version.status is not AIReportVersionStatus.REVIEWED or unresolved:
            raise BusinessValidationError(
                ("report must pass number and citation validation before finalization"),
                code=("REPORT_VALIDATION_REQUIRED"),
                details={"unresolved_findings": (len(unresolved))},
            )
        version.status = AIReportVersionStatus.FINAL
        version.finalized_by = actor.user_id
        job.status = AIReportJobStatus.FINALIZED
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
        public_metadata = _public_metadata(metadata)
        sections = [
            {
                "section_code": row.section_code,
                "title": row.title,
                "content": row.content,
                "source_type": row.source_type,
                "citations": _public_section_citations(
                    section_citations,
                    row.section_code,
                ),
                "tables": _public_section_tables(
                    section_tables,
                    row.section_code,
                ),
            }
            for row in self.repository.list_sections(
                session,
                actor.tenant_id,
                version.id,
            )
        ]
        citations = [
            _public_citation(row)
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
                version.generation_mode.value if version.generation_mode is not None else None
            ),
            "generated_at": (
                version.generated_at.isoformat() if version.generated_at is not None else None
            ),
            "source_versions": public_source_versions(version.source_snapshot_json),
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
        report["job_status"] = job.status.value
        report["progress_percent"] = job.progress_percent
        report["findings"] = [
            {
                "id": row.id,
                "code": row.code,
                "severity": (row.severity.value),
                "message": row.message,
                "details": row.details_json,
                "resolved": row.resolved,
            }
            for row in self.repository.list_validation_findings(
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
            content = export_report_docx(report)
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            extension = "docx"
        elif normalized == "JSON":
            content = export_report_json(report).encode("utf-8")
            content_type = "application/json; charset=utf-8"
            extension = "json"
        elif normalized in {
            "MARKDOWN",
            "MD",
        }:
            normalized = "MARKDOWN"
            content = export_report_markdown(report).encode("utf-8")
            content_type = "text/markdown; charset=utf-8"
            extension = "md"
        else:
            raise BusinessValidationError(
                ("unsupported report export format"),
                code=("REPORT_EXPORT_FORMAT_INVALID"),
                details={"format": export_format},
            )

        file_name = f"{job.report_code}-v{version.version_number}.{extension}"
        output_dir = Path(get_settings().ai_report_export_dir)
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        output_path = output_dir / file_name
        output_path.write_bytes(content)
        content_digest = hashlib.sha256(content).hexdigest()
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
