from datetime import date
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from maintenance_ai.enums import EvidenceStatus, EvidenceType, SensitivityLevel


class EvidenceQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    question: str = Field(validation_alias=AliasChoices("question", "query_text"))
    equipment_model: str | None = None
    configuration_version: str | None = None
    equipment_model_id: int | None = None
    configuration_version_id: int | None = None
    spare_part_ids: list[int] = Field(default_factory=list)
    purpose: str = "GENERAL"
    valid_at: date | None = None
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    max_evidence: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias=AliasChoices("max_evidence", "max_items"),
    )

    @property
    def query_text(self) -> str:
        return self.question

    @property
    def max_items(self) -> int:
        return self.max_evidence


class EvidenceEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    evidence_type: EvidenceType | str
    statement: str
    parameter_name: str | None = None
    structured_value: Any = None
    unit: str | None = None
    applicable_equipment: str | None = None
    applicable_configuration: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_name: str
    source_document: str | None = None
    source_page: int | None = None
    chunk_reference: str | None = None
    knowledge_node: str | None = None
    retrieval_score: float | None = None
    rerank_score: float | None = None
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    sensitivity_level: SensitivityLevel = SensitivityLevel.INTERNAL
    excerpt: str | None = None


class EvidenceConflict(BaseModel):
    model_config = ConfigDict(frozen=True)
    parameter_name: str
    equipment: str | None = None
    values: tuple[Any, ...]
    evidence_ids: tuple[str, ...]
    blocking: bool = True


class EvidencePackage(BaseModel):
    entries: tuple[EvidenceEntry, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    retrieval_metadata: dict = Field(default_factory=dict)

    @property
    def items(self) -> tuple[EvidenceEntry, ...]:
        return self.entries


EvidenceItem = EvidenceEntry
