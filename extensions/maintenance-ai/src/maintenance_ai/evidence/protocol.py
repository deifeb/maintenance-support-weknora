from typing import Protocol, runtime_checkable

from maintenance_ai.evidence.models import EvidencePackage, EvidenceQuery


@runtime_checkable
class EvidenceRetriever(Protocol):
    async def retrieve(self, query: EvidenceQuery) -> EvidencePackage: ...
