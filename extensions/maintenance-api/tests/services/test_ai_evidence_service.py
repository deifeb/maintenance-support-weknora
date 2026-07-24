import pytest
from app.models import AIEvidenceItem, AIEvidencePackage
from app.services.ai_evidence_service import AIEvidenceService, DisabledEvidenceRetriever
from maintenance_ai.enums import SensitivityLevel
from maintenance_ai.evidence import EvidenceQuery
from sqlalchemy import select


@pytest.mark.asyncio
async def test_disabled_evidence_retriever_returns_persisted_empty_package(session) -> None:
    service = AIEvidenceService(retriever=DisabledEvidenceRetriever())
    package = await service.retrieve_and_persist(
        session,
        session_id=None,
        query=EvidenceQuery(query_text="test", sensitivity=SensitivityLevel.INTERNAL),
    )
    assert package.missing_evidence == ("EVIDENCE_SERVICE_DISABLED",)
    assert session.scalar(select(AIEvidencePackage)) is not None
    assert session.scalar(select(AIEvidenceItem)) is None
