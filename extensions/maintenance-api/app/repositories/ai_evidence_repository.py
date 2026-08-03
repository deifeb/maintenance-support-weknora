from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIEvidenceItem,
    AIEvidencePackage,
    AISession,
)
from app.models.enums import AIEvidenceStatus
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


class AIEvidenceRepository:
    def create_package(
        self,
        session: Session,
        tenant_id: str,
        *,
        session_id: int | None,
        query: dict[str, Any],
        conflicts: list[dict[str, Any]],
        missing_evidence: list[str],
        retrieval_metadata: dict[str, Any],
        sensitivity_level: str,
        content_digest: str,
    ) -> AIEvidencePackage:
        if session_id is not None:
            _require_owned(
                session,
                tenant_id,
                AISession,
                session_id,
            )
        row = AIEvidencePackage(
            tenant_id=tenant_id,
            session_id=session_id,
            query_json=query,
            conflicts_json=conflicts,
            missing_evidence_json=missing_evidence,
            retrieval_metadata_json=retrieval_metadata,
            sensitivity_level=sensitivity_level,
            content_digest=content_digest,
        )
        session.add(row)
        session.flush()
        return row

    def get_package(
        self,
        session: Session,
        tenant_id: str,
        package_id: int,
    ) -> AIEvidencePackage | None:
        return _owned(
            session,
            tenant_id,
            AIEvidencePackage,
            package_id,
        )

    def add_item(
        self,
        session: Session,
        tenant_id: str,
        *,
        package_id: int,
        evidence_id: str,
        evidence_type: str,
        statement: str,
        source_name: str,
        status: str,
        sensitivity_level: str,
        excerpt: str,
        structured_value: Any | None = None,
        unit: str | None = None,
        source_document: str | None = None,
        source_page: int | None = None,
        chunk_reference: str | None = None,
        knowledge_node: str | None = None,
    ) -> AIEvidenceItem:
        _require_owned(
            session,
            tenant_id,
            AIEvidencePackage,
            package_id,
        )
        row = AIEvidenceItem(
            tenant_id=tenant_id,
            package_id=package_id,
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            statement=statement,
            structured_value_json=structured_value,
            unit=unit,
            source_name=source_name,
            source_document=source_document,
            source_page=source_page,
            chunk_reference=chunk_reference,
            knowledge_node=knowledge_node,
            status=AIEvidenceStatus(status),
            sensitivity_level=sensitivity_level,
            excerpt=excerpt,
        )
        session.add(row)
        session.flush()
        return row

    def list_items(
        self,
        session: Session,
        tenant_id: str,
        package_id: int,
    ) -> list[AIEvidenceItem]:
        _require_owned(
            session,
            tenant_id,
            AIEvidencePackage,
            package_id,
        )
        return list(
            session.scalars(
                select(AIEvidenceItem)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIEvidenceItem.tenant_id == tenant_id,
                    AIEvidenceItem.package_id == package_id,
                )
                .order_by(AIEvidenceItem.id)
            ).all()
        )

    def list_recent_packages(
        self,
        session: Session,
        tenant_id: str,
        session_id: int,
        *,
        limit: int = 10,
    ) -> list[AIEvidencePackage]:
        _require_owned(
            session,
            tenant_id,
            AISession,
            session_id,
        )
        return list(
            session.scalars(
                select(AIEvidencePackage)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIEvidencePackage.tenant_id
                    == tenant_id,
                    AIEvidencePackage.session_id
                    == session_id,
                )
                .order_by(AIEvidencePackage.id.desc())
                .limit(limit)
            ).all()
        )


ai_evidence_repository = AIEvidenceRepository()
