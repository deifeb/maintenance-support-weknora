from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    AIConfirmationLevel,
    AIConfirmationStatus,
    AIPlanStatus,
    AIPlanStepStatus,
    AIToolCallStatus,
)
from app.models.mixins import TimestampMixin


class AIExecutionPlan(Base, TimestampMixin):
    __tablename__ = "ai_execution_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    planner_provider: Mapped[str | None] = mapped_column(String(32))
    planner_model: Mapped[str | None] = mapped_column(String(128))
    validation_status: Mapped[str | None] = mapped_column(String(32))
    validation_errors_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    status: Mapped[AIPlanStatus] = mapped_column(
        Enum(AIPlanStatus, native_enum=False, length=24),
        nullable=False,
        default=AIPlanStatus.CREATED,
    )


class AIPlanStep(Base, TimestampMixin):
    __tablename__ = "ai_plan_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("ai_execution_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128))
    input_template_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    depends_on_json: Mapped[list[str] | None] = mapped_column(JSON)
    confirmation_level: Mapped[AIConfirmationLevel] = mapped_column(
        Enum(AIConfirmationLevel, native_enum=False, length=20),
        nullable=False,
        default=AIConfirmationLevel.NONE,
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")
    status: Mapped[AIPlanStepStatus] = mapped_column(
        Enum(AIPlanStepStatus, native_enum=False, length=32),
        nullable=False,
        default=AIPlanStepStatus.PENDING,
    )
    result_reference_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("plan_id", "step_code", name="uq_ai_plan_step_code"),)


class AIToolCall(Base, TimestampMixin):
    __tablename__ = "ai_tool_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_plan_steps.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_level: Mapped[str | None] = mapped_column(String(64))
    confirmation_id: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[AIToolCallStatus] = mapped_column(
        Enum(AIToolCallStatus, native_enum=False, length=20),
        nullable=False,
        default=AIToolCallStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_reference_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class AIConfirmationRequest(Base, TimestampMixin):
    __tablename__ = "ai_confirmation_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_plan_steps.id", ondelete="SET NULL")
    )
    operation_name: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmation_level: Mapped[AIConfirmationLevel] = mapped_column(
        Enum(AIConfirmationLevel, native_enum=False, length=20), nullable=False
    )
    status: Mapped[AIConfirmationStatus] = mapped_column(
        Enum(AIConfirmationStatus, native_enum=False, length=20),
        nullable=False,
        default=AIConfirmationStatus.PENDING,
    )
    input_preview_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    data_externalization: Mapped[bool] = mapped_column(nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
