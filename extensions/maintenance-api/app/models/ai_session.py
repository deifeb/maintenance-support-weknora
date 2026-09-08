from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
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
    AIMessageRole,
    AIMessageType,
    AIModelCallStatus,
    AISessionStatus,
)
from app.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    VersionedMixin,
    utc_now,
)


class AISession(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AISessionStatus] = mapped_column(
        Enum(AISessionStatus, native_enum=False, length=32),
        nullable=False,
        default=AISessionStatus.CREATED,
        index=True,
    )
    current_intent: Mapped[str | None] = mapped_column(String(64))
    execution_mode: Mapped[AIExecutionMode] = mapped_column(
        Enum(AIExecutionMode, native_enum=False, length=24),
        nullable=False,
        default=AIExecutionMode.LLM,
    )
    sensitivity_level: Mapped[str] = mapped_column(String(24), nullable=False, default="INTERNAL")
    active_scenario_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="SET NULL")
    )
    active_calculation_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculations.id", ondelete="SET NULL")
    )
    active_report_job_id: Mapped[int | None] = mapped_column(Integer)
    last_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(128))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_ai_sessions_tenant_code",
            "tenant_id",
            "session_code",
            unique=True,
        ),
        CheckConstraint("last_event_sequence >= 0", name="ck_ai_session_event_sequence"),
    )


class AIMessage(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[AIMessageRole] = mapped_column(
        Enum(AIMessageRole, native_enum=False, length=20), nullable=False
    )
    message_type: Mapped[AIMessageType] = mapped_column(
        Enum(AIMessageType, native_enum=False, length=32), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    model_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_model_calls.id", ondelete="SET NULL")
    )
    tool_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_tool_calls.id", ondelete="SET NULL")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_ai_message_sequence"),)


class AISessionSnapshot(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_session_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_state: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_draft_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    field_sources_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    execution_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    pending_confirmations_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    completed_step_ids_json: Mapped[list[str] | None] = mapped_column(JSON)
    evidence_package_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("session_id", "snapshot_version", name="uq_ai_snapshot_version"),
    )


class AIEvent(
    Base,
    TenantScopedMixin,
):
    __tablename__ = "ai_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_ai_event_sequence"),)


class AIModelCall(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_model_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[AIModelCallStatus] = mapped_column(
        Enum(AIModelCallStatus, native_enum=False, length=20),
        nullable=False,
        default=AIModelCallStatus.PENDING,
    )
    prompt_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(32))
    sensitivity_level: Mapped[str] = mapped_column(String(24), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    output_digest: Mapped[str | None] = mapped_column(String(64))
    raw_response_digest: Mapped[str | None] = mapped_column(String(64))
    finish_reason: Mapped[str | None] = mapped_column(String(64))
    structured_validation_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_used: Mapped[bool] = mapped_column(nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_ai_model_calls_tenant_request",
            "tenant_id",
            "request_id",
            unique=True,
        ),
    )
