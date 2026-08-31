from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    AIExecutionMode,
    AIExportFormat,
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
    AISeverity,
)
from app.models.mixins import TenantScopedMixin, TimestampMixin, VersionedMixin


class AIReportJob(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="SET NULL"), index=True
    )
    report_type: Mapped[AIReportType] = mapped_column(
        Enum(AIReportType, native_enum=False, length=32), nullable=False
    )
    status: Mapped[AIReportJobStatus] = mapped_column(
        Enum(AIReportJobStatus, native_enum=False, length=32),
        nullable=False,
        default=AIReportJobStatus.CREATED,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_ai_report_jobs_tenant_code",
            "tenant_id",
            "report_code",
            unique=True,
        ),
    )


class AIReportVersion(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_job_id: Mapped[int] = mapped_column(
        ForeignKey("ai_report_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_report_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    input_digest: Mapped[str | None] = mapped_column(String(64))
    generation_mode: Mapped[AIExecutionMode | None] = mapped_column(
        Enum(AIExecutionMode, native_enum=False, length=24)
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AIReportVersionStatus] = mapped_column(
        Enum(AIReportVersionStatus, native_enum=False, length=20),
        nullable=False,
        default=AIReportVersionStatus.DRAFT,
    )
    scenario_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="SET NULL")
    )
    calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculation_runs.id", ondelete="SET NULL")
    )
    review_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_review_runs.id", ondelete="SET NULL")
    )
    inventory_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_versions_json: Mapped[dict[str, str] | None] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    finalized_by: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        UniqueConstraint("report_job_id", "version_number", name="uq_ai_report_version"),
    )


class AIReportSection(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("ai_report_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_model_calls.id", ondelete="SET NULL")
    )
    __table_args__ = (
        UniqueConstraint("report_version_id", "section_code", name="uq_ai_report_section"),
    )


class AIReportCitation(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_citations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("ai_report_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    citation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_version: Mapped[str | None] = mapped_column(String(64))
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_reference: Mapped[str | None] = mapped_column(String(255))
    knowledge_node: Mapped[str | None] = mapped_column(String(255))
    database_record_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("report_version_id", "citation_id", name="uq_ai_report_citation"),
    )


class AIReportValidationFinding(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_validation_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("ai_report_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[AISeverity] = mapped_column(
        Enum(AISeverity, native_enum=False, length=20), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)


class AIReportExport(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_report_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("ai_report_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    export_format: Mapped[AIExportFormat] = mapped_column(
        Enum(AIExportFormat, native_enum=False, length=20), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000))
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
