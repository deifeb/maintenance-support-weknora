from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AIEvidenceStatus
from app.models.mixins import TenantScopedMixin, TimestampMixin


class AIEvidencePackage(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_evidence_packages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="SET NULL"), index=True
    )
    query_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    conflicts_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    missing_evidence_json: Mapped[list[str] | None] = mapped_column(JSON)
    retrieval_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sensitivity_level: Mapped[str] = mapped_column(String(24), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class AIEvidenceItem(
    Base,
    TenantScopedMixin,
    TimestampMixin,
):
    __tablename__ = "ai_evidence_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("ai_evidence_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    structured_value_json: Mapped[Any | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(64))
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_document: Mapped[str | None] = mapped_column(String(500))
    source_page: Mapped[int | None] = mapped_column(Integer)
    chunk_reference: Mapped[str | None] = mapped_column(String(255))
    knowledge_node: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[AIEvidenceStatus] = mapped_column(
        Enum(AIEvidenceStatus, native_enum=False, length=20), nullable=False
    )
    sensitivity_level: Mapped[str] = mapped_column(String(24), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
