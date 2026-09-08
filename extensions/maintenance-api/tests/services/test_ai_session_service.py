from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.security.actor import ActorContext
from app.services.ai_confirmation_service import (
    ai_confirmation_service,
)
from app.services.ai_event_service import (
    ai_event_service,
)
from app.services.ai_session_service import (
    ai_session_service,
)
from sqlalchemy.orm import Session


def add_scenario_version(
    session: Session,
    tenant_id: str,
    code: str,
) -> DemandScenarioVersion:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"T-{code}",
        name=f"Template {code}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=code,
        version_name=f"Version {code}",
    )
    session.add(version)
    session.flush()
    return version


def test_session_event_snapshot_and_confirmation_digest(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    scenario = add_scenario_version(
        session,
        actor.tenant_id,
        "V1",
    )

    row = ai_session_service.create(
        session,
        actor,
        title="Session",
        sensitivity_level="INTERNAL",
        active_scenario_version_id=scenario.id,
    )
    message = ai_session_service.add_message(
        session,
        actor,
        row.id,
        role="USER",
        message_type="USER_TEXT",
        content="Calculate demand",
    )
    event = ai_session_service.append_event(
        session,
        actor,
        row.id,
        "SESSION_STARTED",
        {},
    )
    snapshot = ai_session_service.create_snapshot(
        session,
        actor,
        row.id,
        scenario_draft={"a": 1},
    )
    confirmation, token = (
        ai_confirmation_service.create(
            session,
            actor,
            session_id=row.id,
            operation_name=(
                "start_demand_calculation"
            ),
            confirmation_level="EXPLICIT",
            input_payload={"scenario": 1},
            risk_level="HIGH",
        )
    )

    assert row.tenant_id == actor.tenant_id
    assert row.created_by == actor.user_id
    assert (
        row.active_scenario_version_id
        == scenario.id
    )
    assert message.tenant_id == actor.tenant_id
    assert event.sequence == 1
    assert snapshot.snapshot_version == 1
    assert (
        confirmation.confirmation_token_hash
        != token
    )

    approved = ai_confirmation_service.approve(
        session,
        actor,
        confirmation.id,
        token=token,
        expected_input_digest=(
            confirmation.input_digest
        ),
    )

    assert approved.status.value == "APPROVED"
    assert approved.resolved_by == actor.user_id
    assert [
        item.id
        for item in ai_event_service.list(
            session,
            actor,
            row.id,
        )
    ] == [event.id]


def test_ai_session_and_confirmation_reject_foreign_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    local_actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    foreign_actor = actor_context(
        tenant_id="tenant-b",
        user_id="bob",
    )
    foreign_session = ai_session_service.create(
        session,
        foreign_actor,
        title="Foreign",
        sensitivity_level="INTERNAL",
    )
    foreign_confirmation, token = (
        ai_confirmation_service.create(
            session,
            foreign_actor,
            session_id=foreign_session.id,
            operation_name="foreign-operation",
            confirmation_level="EXPLICIT",
            input_payload={"value": 1},
            risk_level="HIGH",
        )
    )
    foreign_scenario = add_scenario_version(
        session,
        foreign_actor.tenant_id,
        "FOREIGN",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        ai_session_service.get(
            session,
            local_actor,
            foreign_session.id,
        )

    with pytest.raises(NotFoundError):
        ai_session_service.add_message(
            session,
            local_actor,
            foreign_session.id,
            role="USER",
            message_type="USER_TEXT",
            content="forged",
        )

    with pytest.raises(NotFoundError):
        ai_event_service.list(
            session,
            local_actor,
            foreign_session.id,
        )

    with pytest.raises(NotFoundError):
        ai_confirmation_service.approve(
            session,
            local_actor,
            foreign_confirmation.id,
            token=token,
            expected_input_digest=(
                foreign_confirmation.input_digest
            ),
        )

    with pytest.raises(NotFoundError):
        ai_session_service.create(
            session,
            local_actor,
            title="Invalid scenario",
            sensitivity_level="INTERNAL",
            active_scenario_version_id=(
                foreign_scenario.id
            ),
        )


def test_get_message_returns_exact_message_not_latest(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    row = ai_session_service.create(
        session,
        actor,
        title="Exact message",
        sensitivity_level="INTERNAL",
    )
    first = ai_session_service.add_message(
        session,
        actor,
        row.id,
        role="USER",
        message_type="USER_TEXT",
        content="first",
    )
    second = ai_session_service.add_message(
        session,
        actor,
        row.id,
        role="USER",
        message_type="USER_TEXT",
        content="second",
    )

    exact = ai_session_service.get_message(
        session,
        actor,
        row.id,
        first.id,
    )

    assert exact.id == first.id
    assert exact.id != second.id
    assert exact.content == "first"


def test_get_message_rejects_session_message_mismatch(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    source_session = ai_session_service.create(
        session,
        actor,
        title="Source",
        sensitivity_level="INTERNAL",
    )
    other_session = ai_session_service.create(
        session,
        actor,
        title="Other",
        sensitivity_level="INTERNAL",
    )
    message = ai_session_service.add_message(
        session,
        actor,
        source_session.id,
        role="USER",
        message_type="USER_TEXT",
        content="source-message",
    )

    with pytest.raises(NotFoundError):
        ai_session_service.get_message(
            session,
            actor,
            other_session.id,
            message.id,
        )


def test_get_message_rejects_foreign_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    local_actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    foreign_actor = actor_context(
        tenant_id="tenant-b",
        user_id="bob",
    )
    foreign_session = ai_session_service.create(
        session,
        foreign_actor,
        title="Foreign",
        sensitivity_level="INTERNAL",
    )
    foreign_message = ai_session_service.add_message(
        session,
        foreign_actor,
        foreign_session.id,
        role="USER",
        message_type="USER_TEXT",
        content="foreign-message",
    )

    with pytest.raises(NotFoundError):
        ai_session_service.get_message(
            session,
            local_actor,
            foreign_session.id,
            foreign_message.id,
        )
