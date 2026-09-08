from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models.enums import AISessionStatus
from app.security.actor import ActorContext
from app.services.ai_plan_service import (
    ai_plan_service,
)
from sqlalchemy.orm import Session
from tests.ai.factories import create_ai_session


def test_plan_service_persists_validated_plan(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    row = create_ai_session(
        session,
        tenant_id=actor.tenant_id,
    )
    plan = ai_plan_service.create_and_validate(
        session,
        actor,
        row.id,
        "\u6309\u5f53\u524d\u573a\u666f\u6267\u884c\u6b63\u5f0f\u9700\u6c42\u8ba1\u7b97",
    )
    session.refresh(row)

    assert plan.tenant_id == actor.tenant_id
    assert plan.validation_status == "VALID"
    assert row.status is AISessionStatus.PLANNED


def test_plan_service_rejects_foreign_session(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    foreign = create_ai_session(
        session,
        tenant_id="tenant-b",
    )

    with pytest.raises(NotFoundError):
        ai_plan_service.create_and_validate(
            session,
            actor,
            foreign.id,
            "formal calculation",
        )
