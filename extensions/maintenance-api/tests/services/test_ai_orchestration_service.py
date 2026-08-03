from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models import AIMessage
from app.models.enums import AISessionStatus
from app.security.actor import ActorContext
from app.services.ai_orchestration_service import (
    ai_orchestration_service,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.ai.factories import (
    count_demand_calculations,
    count_tool_calls,
    create_ai_session,
    create_ready_ai_session,
    create_session_with_completed_query_step,
)


@pytest.mark.asyncio
async def test_formal_calculation_pauses_at_confirmation(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="u1",
    )
    ai_session = create_ready_ai_session(
        session,
        tenant_id=actor.tenant_id,
    )
    result = (
        await ai_orchestration_service
        .handle_message(
            session,
            actor,
            ai_session.id,
            "\u6309\u5f53\u524d\u573a\u666f\u6267\u884c\u6b63\u5f0f\u9700\u6c42\u8ba1\u7b97",
            permissions={
                "CALCULATION_EXECUTE"
            },
        )
    )
    session.commit()

    assert (
        result.status
        is AISessionStatus
        .CONFIRMATION_REQUIRED
    )
    assert (
        result.pending_confirmation_id
        is not None
    )
    assert count_demand_calculations(
        session
    ) == 0


@pytest.mark.asyncio
async def test_resume_does_not_repeat_completed_tool_step(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="u1",
    )
    ai_session = (
        create_session_with_completed_query_step(
            session,
            tenant_id=actor.tenant_id,
        )
    )

    first = (
        await ai_orchestration_service.resume(
            session,
            actor,
            ai_session.id,
        )
    )
    second = (
        await ai_orchestration_service.resume(
            session,
            actor,
            ai_session.id,
        )
    )

    assert (
        first.completed_step_ids
        == second.completed_step_ids
    )
    assert count_tool_calls(
        session,
        "get_calculation_status",
    ) == 1


@pytest.mark.asyncio
async def test_orchestration_rejects_foreign_session_before_message_write(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="u1",
    )
    foreign = create_ai_session(
        session,
        tenant_id="tenant-b",
    )
    before = int(
        session.scalar(
            select(
                func.count(AIMessage.id)
            ).where(
                AIMessage.session_id
                == foreign.id
            )
        )
        or 0
    )

    with pytest.raises(NotFoundError):
        await ai_orchestration_service.handle_message(
            session,
            actor,
            foreign.id,
            "hello",
            permissions=set(),
        )

    after = int(
        session.scalar(
            select(
                func.count(AIMessage.id)
            ).where(
                AIMessage.session_id
                == foreign.id
            )
        )
        or 0
    )
    assert after == before
