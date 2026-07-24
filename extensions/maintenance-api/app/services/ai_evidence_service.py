from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from maintenance_ai.enums import EvidenceStatus, EvidenceType, SensitivityLevel
from maintenance_ai.evidence import (
    EvidenceEntry,
    EvidencePackage,
    EvidencePackageBuilder,
    EvidenceQuery,
)
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError
from app.models import AIEvidenceItem, AIEvidencePackage
from app.models.enums import AIEvidenceStatus

_SENSITIVITY_ORDER = {
    SensitivityLevel.PUBLIC: 0,
    SensitivityLevel.INTERNAL: 1,
    SensitivityLevel.CONFIDENTIAL: 2,
    SensitivityLevel.RESTRICTED: 3,
}


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DisabledEvidenceRetriever:
    async def retrieve(self, query: EvidenceQuery) -> EvidencePackage:
        return EvidencePackage(
            entries=(),
            missing_evidence=("EVIDENCE_SERVICE_DISABLED",),
            retrieval_metadata={
                "query": query.question,
                "disabled": True,
                "filtered_count": 0,
            },
        )


class WeknoraEvidenceRetriever:
    def __init__(
        self,
        *,
        endpoint_url: str,
        api_key: str | None,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint_url.startswith(("http://", "https://")):
            raise ValueError("WEKNORA_EVIDENCE_URL must be an absolute HTTP URL")
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    def _request_payload(self, query: EvidenceQuery) -> dict[str, Any]:
        return {
            "query": query.question,
            "equipment_model_id": query.equipment_model_id,
            "configuration_version_id": query.configuration_version_id,
            "spare_part_ids": query.spare_part_ids,
            "purpose": query.purpose,
            "valid_at": query.valid_at.isoformat() if query.valid_at else None,
            "sensitivity": query.sensitivity.value,
            "max_items": query.max_evidence,
        }

    async def retrieve(self, query: EvidenceQuery) -> EvidencePackage:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = await self._client.post(
                self.endpoint_url,
                json=self._request_payload(query),
                headers=headers,
                timeout=self.timeout_seconds,
            )
            if response.status_code in {401, 403}:
                raise BusinessValidationError(
                    "evidence access denied",
                    code="EVIDENCE_ACCESS_DENIED",
                )
            response.raise_for_status()
            payload = response.json()
        except BusinessValidationError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise BusinessValidationError(
                "evidence service unavailable",
                details={"reason": type(exc).__name__},
                code="EVIDENCE_SERVICE_UNAVAILABLE",
            ) from exc
        except (ValueError, TypeError) as exc:
            raise BusinessValidationError(
                "invalid evidence response",
                details={"reason": str(exc)},
                code="EVIDENCE_RESPONSE_INVALID",
            ) from exc

        entries: list[EvidenceEntry] = []
        filtered_count = 0
        for raw in payload.get("items", []):
            try:
                sensitivity = SensitivityLevel(raw.get("sensitivity", "INTERNAL"))
                if _SENSITIVITY_ORDER[sensitivity] > _SENSITIVITY_ORDER[query.sensitivity]:
                    filtered_count += 1
                    continue
                entry = EvidenceEntry(
                    evidence_id=str(raw.get("id") or raw.get("evidence_id")),
                    evidence_type=raw.get("type", "TEXT_EXCERPT"),
                    statement=str(raw.get("statement", "")),
                    parameter_name=raw.get("parameter_name"),
                    structured_value=raw.get("value", raw.get("structured_value")),
                    unit=raw.get("unit"),
                    applicable_equipment=raw.get("applicable_equipment"),
                    applicable_configuration=raw.get("applicable_configuration"),
                    effective_from=raw.get("effective_from"),
                    effective_to=raw.get("effective_to"),
                    source_name=str(raw.get("source_name") or raw.get("document") or "WeKnora"),
                    source_document=raw.get("document"),
                    source_page=raw.get("page"),
                    knowledge_node=raw.get("knowledge_node"),
                    chunk_reference=raw.get("chunk_reference"),
                    retrieval_score=raw.get("score"),
                    rerank_score=raw.get("rerank_score"),
                    sensitivity_level=sensitivity,
                    status=EvidenceStatus(raw.get("status", "VALID")),
                    excerpt=(str(raw.get("excerpt"))[:4000] if raw.get("excerpt") else None),
                )
            except Exception as exc:
                raise BusinessValidationError(
                    "invalid evidence item",
                    details={"item_id": raw.get("id"), "reason": str(exc)},
                    code="EVIDENCE_RESPONSE_INVALID",
                ) from exc
            entries.append(entry)
        return EvidencePackageBuilder().build(
            entries,
            missing_evidence=tuple(payload.get("missing_evidence", [])),
            retrieval_metadata={
                "source": "WEKNORA",
                "returned_count": len(entries),
                "filtered_count": filtered_count,
                **dict(payload.get("metadata", {})),
            },
        )


class AIEvidenceService:
    def __init__(self, *, retriever) -> None:
        self.retriever = retriever

    async def retrieve_and_persist(
        self,
        session: Session,
        *,
        session_id: int | None,
        query: EvidenceQuery,
    ) -> EvidencePackage:
        package = await self.retriever.retrieve(query)
        highest = query.sensitivity
        for entry in package.entries:
            if _SENSITIVITY_ORDER[entry.sensitivity_level] > _SENSITIVITY_ORDER[highest]:
                highest = entry.sensitivity_level
        serialized = package.model_dump(mode="json")
        row = AIEvidencePackage(
            session_id=session_id,
            query_json=query.model_dump(mode="json"),
            conflicts_json=[item.model_dump(mode="json") for item in package.conflicts],
            missing_evidence_json=list(package.missing_evidence),
            retrieval_metadata_json={
                "schema_version": "1.0",
                **package.retrieval_metadata,
            },
            sensitivity_level=highest.value,
            content_digest=_digest(serialized),
        )
        session.add(row)
        session.flush()
        for entry in package.entries:
            session.add(
                AIEvidenceItem(
                    package_id=row.id,
                    evidence_id=entry.evidence_id,
                    evidence_type=(
                        entry.evidence_type.value
                        if isinstance(entry.evidence_type, EvidenceType)
                        else str(entry.evidence_type)
                    ),
                    statement=entry.statement[:4000],
                    structured_value_json=entry.structured_value,
                    unit=entry.unit,
                    source_name=entry.source_name,
                    source_document=entry.source_document,
                    source_page=entry.source_page,
                    chunk_reference=entry.chunk_reference,
                    knowledge_node=entry.knowledge_node,
                    status=AIEvidenceStatus(entry.status.value),
                    sensitivity_level=entry.sensitivity_level.value,
                    excerpt=(entry.excerpt or entry.statement)[:4000],
                )
            )
        session.commit()
        return package

    @staticmethod
    def to_prompt_data(package: EvidencePackage) -> dict[str, Any]:
        facts = []
        text_excerpts = []
        citations = []
        for entry in package.entries:
            citations.append(
                {
                    "citation_id": entry.evidence_id,
                    "source_name": entry.source_name,
                    "document": entry.source_document,
                    "page": entry.source_page,
                    "chunk_reference": entry.chunk_reference,
                }
            )
            item_type = (
                entry.evidence_type.value
                if isinstance(entry.evidence_type, EvidenceType)
                else str(entry.evidence_type)
            )
            if item_type == EvidenceType.TEXT_EXCERPT.value:
                text_excerpts.append(
                    {
                        "evidence_id": entry.evidence_id,
                        "content": entry.excerpt or entry.statement,
                        "untrusted_document_data": True,
                    }
                )
            else:
                facts.append(
                    {
                        "evidence_id": entry.evidence_id,
                        "statement": entry.statement,
                        "parameter_name": entry.parameter_name,
                        "value": entry.structured_value,
                        "unit": entry.unit,
                        "status": entry.status.value,
                    }
                )
        return {
            "system_instructions": [],
            "structured_facts": facts,
            "text_excerpts": text_excerpts,
            "citations": citations,
            "conflicts": [item.model_dump(mode="json") for item in package.conflicts],
            "missing_evidence": list(package.missing_evidence),
        }
