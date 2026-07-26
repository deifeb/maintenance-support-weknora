from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    AIEvidenceItem,
    AIEvidencePackage,
)
from app.security.actor import ActorContext
from app.services.ai_evidence_service import (
    AIEvidenceService,
    DisabledEvidenceRetriever,
)
from maintenance_ai.enums import SensitivityLevel
from maintenance_ai.evidence import EvidenceQuery
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.ai.factories import create_ai_session


class CountingEvidenceRetriever:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query):
        self.calls += 1
        return await DisabledEvidenceRetriever().retrieve(
            query
        )


@pytest.mark.asyncio
async def test_disabled_evidence_retriever_returns_tenant_package(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    service = AIEvidenceService(
        retriever=DisabledEvidenceRetriever()
    )

    package = await service.retrieve_and_persist(
        session,
        actor,
        session_id=None,
        query=EvidenceQuery(
            query_text="test",
            sensitivity=SensitivityLevel.INTERNAL,
        ),
    )

    row = session.scalar(
        select(AIEvidencePackage).where(
            AIEvidencePackage.tenant_id
            == actor.tenant_id
        )
    )
    assert (
        package.missing_evidence
        == ("EVIDENCE_SERVICE_DISABLED",)
    )
    assert row is not None
    assert row.tenant_id == actor.tenant_id
    assert (
        session.scalar(
            select(AIEvidenceItem).where(
                AIEvidenceItem.tenant_id
                == actor.tenant_id
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_evidence_rejects_foreign_session(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    foreign_session = create_ai_session(
        session,
        tenant_id="tenant-b",
    )
    retriever = CountingEvidenceRetriever()
    service = AIEvidenceService(
        retriever=retriever
    )

    with pytest.raises(NotFoundError):
        await service.retrieve_and_persist(
            session,
            actor,
            session_id=foreign_session.id,
            query=EvidenceQuery(
                query_text="test",
                sensitivity=(
                    SensitivityLevel.INTERNAL
                ),
            ),
        )
    assert retriever.calls == 0
