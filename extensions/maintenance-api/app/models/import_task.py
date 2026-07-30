from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
)


class ImportTaskStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PREVIEWING = "PREVIEWING"
    PREVIEW_VALID = "PREVIEW_VALID"
    PREVIEW_INVALID = "PREVIEW_INVALID"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class MasterDataImportTask(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "master_data_import_tasks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_by_request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    template_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    status: Mapped[ImportTaskStatus] = mapped_column(
        Enum(
            ImportTaskStatus,
            native_enum=False,
            length=24,
        ),
        nullable=False,
        default=ImportTaskStatus.UPLOADED,
    )
    mapping_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    sheet_summary_json: Mapped[
        dict[str, int] | None
    ] = mapped_column(JSON)
    preview_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    errors_json: Mapped[
        list[dict[str, Any]] | None
    ] = mapped_column(JSON)
    warnings_json: Mapped[
        list[dict[str, Any]] | None
    ] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100)
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    error_workbook_path: Mapped[str | None] = mapped_column(
        String(500)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        Index(
            "ix_master_data_import_tasks_tenant_user_status",
            "tenant_id",
            "created_by_user_id",
            "status",
        ),
    )


ImportTask = MasterDataImportTask
