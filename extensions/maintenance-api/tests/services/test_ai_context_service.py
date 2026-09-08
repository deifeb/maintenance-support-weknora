from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.security.actor import ActorContext
from app.services.ai_context_service import (
    ai_context_service,
)
from sqlalchemy.orm import Session
from tests.ai.factories import (
    create_ai_session_with_messages,
)


def test_context_uses_summary_recent_messages_and_structured_state(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    ai_session = create_ai_session_with_messages(
        session,
        count=20,
        tenant_id=actor.tenant_id,
    )

    context = ai_context_service.build_context(
        session,
        actor,
        ai_session.id,
        recent_message_count=4,
    )

    assert len(context.recent_messages) == 4
    assert context.session_summary
    assert (
        context.scenario_draft["scenario_name"]
        == "测试场景"
    )
    assert context.pending_confirmations == []


def test_context_rejects_foreign_session(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    foreign = create_ai_session_with_messages(
        session,
        count=2,
        tenant_id="tenant-b",
    )

    with pytest.raises(NotFoundError):
        ai_context_service.build_context(
            session,
            actor,
            foreign.id,
        )
