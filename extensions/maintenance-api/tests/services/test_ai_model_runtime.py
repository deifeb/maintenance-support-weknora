from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models import AIModelCall
from app.security.actor import ActorContext
from app.services.ai_model_runtime import (
    AIModelRuntime,
)
from maintenance_ai.providers import (
    StructuredCompletionRequest,
    TextMessage,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.ai.factories import (
    create_ai_session,
    make_router,
)


class Result(BaseModel):
    value: str


def request() -> StructuredCompletionRequest:
    return StructuredCompletionRequest(
        messages=(
            TextMessage(
                role="user",
                content="secret user content",
            ),
        ),
        function_name="scenario_parsing",
        prompt_name="scenario-parser",
        prompt_version="1.0",
        schema_version="1.0",
    )


@pytest.mark.asyncio
async def test_runtime_persists_tenant_model_call_without_raw_secret(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    runtime = AIModelRuntime(
        router=make_router(
            function_name="scenario_parsing",
            structured_payload={"value": "ok"},
        )
    )
    ai_session = create_ai_session(
        session,
        tenant_id=actor.tenant_id,
    )

    result = await runtime.complete_structured(
        session,
        actor,
        session_id=ai_session.id,
        request=request(),
        response_model=Result,
    )

    row = session.scalar(
        select(AIModelCall)
        .where(
            AIModelCall.tenant_id
            == actor.tenant_id
        )
        .order_by(AIModelCall.id.desc())
    )
    assert result.data["value"] == "ok"
    assert row is not None
    assert row.tenant_id == actor.tenant_id
    assert row.status.value == "SUCCEEDED"
    assert row.raw_response_digest
    assert (
        "secret user content"
        not in (row.error_message or "")
    )


@pytest.mark.asyncio
async def test_runtime_rejects_foreign_session_without_persisting_call(
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
    runtime = AIModelRuntime(
        router=make_router(
            function_name="scenario_parsing",
            structured_payload={"value": "ok"},
        )
    )
    before = int(
        session.scalar(
            select(func.count(AIModelCall.id))
        )
        or 0
    )

    with pytest.raises(NotFoundError):
        await runtime.complete_structured(
            session,
            actor,
            session_id=foreign_session.id,
            request=request(),
            response_model=Result,
        )

    after = int(
        session.scalar(
            select(func.count(AIModelCall.id))
        )
        or 0
    )
    assert after == before
