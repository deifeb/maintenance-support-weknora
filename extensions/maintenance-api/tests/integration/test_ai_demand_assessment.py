from __future__ import annotations

from collections.abc import Callable

import pytest
from app.security.actor import ActorContext
from app.services.ai_orchestration_service import (
    ai_orchestration_service,
)
from sqlalchemy.orm import Session
from tests.ai.factories import create_ai_session


@pytest.mark.asyncio
async def test_scenario_preparation_emits_draft_snapshot(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="u1",
    )
    row = create_ai_session(
        session,
        tenant_id=actor.tenant_id,
    )
    result = (
        await ai_orchestration_service
        .handle_message(
            session,
            actor,
            row.id,
            "\u4e3a\u67d0\u578b\u88c5\u590710\u53f0\u5236\u5b9a30\u5929\u4efb\u52a1\u9700\u6c42\u573a\u666f",
            permissions=set(),
        )
    )

    assert result.scenario_draft is not None
    assert result.status.value in {
        "CLARIFICATION_REQUIRED",
        "PLANNED",
    }
