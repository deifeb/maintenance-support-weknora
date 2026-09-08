from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AIBlockingLevel, AIReviewFindingStatus, AIReviewRunStatus, AISeverity
from app.models.mixins import TenantScopedMixin, TimestampMixin, VersionedMixin


class AIReviewRun(
    Base,
    TenantScopedMixin,
    VersionedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_review_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="SET NULL"), index=True
    )
    calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_calculation_runs.id", ondelete="SET NULL")
    )
    scenario_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("demand_scenario_versions.id", ondelete="SET NULL")
    )
    status: Mapped[AIReviewRunStatus] = mapped_column(
        Enum(AIReviewRunStatus, native_enum=False, length=20),
        nullable=False,
        default=AIReviewRunStatus.CREATED,
    )
    rule_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AIReviewFinding(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_review_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_run_id: Mapped[int] = mapped_column(
        ForeignKey("ai_review_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[AISeverity] = mapped_column(
        Enum(AISeverity, native_enum=False, length=20), nullable=False
    )
    status: Mapped[AIReviewFindingStatus] = mapped_column(
        Enum(AIReviewFindingStatus, native_enum=False, length=24),
        nullable=False,
        default=AIReviewFindingStatus.OPEN,
    )
    blocking_level: Mapped[AIBlockingLevel] = mapped_column(
        Enum(AIBlockingLevel, native_enum=False, length=40), nullable=False
    )
    affected_entity_type: Mapped[str | None] = mapped_column(String(64))
    affected_entity_id: Mapped[int | None] = mapped_column(Integer)
    affected_spare_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="SET NULL")
    )
    finding_title: Mapped[str] = mapped_column(String(255), nullable=False)
    deterministic_message: Mapped[str] = mapped_column(Text, nullable=False)
    observed_value_json: Mapped[Any | None] = mapped_column(JSON)
    expected_range_json: Mapped[Any | None] = mapped_column(JSON)
    evidence_references_json: Mapped[list[str] | None] = mapped_column(JSON)
    suggested_actions_json: Mapped[list[str] | None] = mapped_column(JSON)
    llm_explanation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    llm_model_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_model_calls.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolution_comment: Mapped[str | None] = mapped_column(Text)
