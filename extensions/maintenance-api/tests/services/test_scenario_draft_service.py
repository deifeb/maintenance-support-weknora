from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import ConflictError, NotFoundError
from app.models import AISessionSnapshot
from app.schemas.scenario_draft import ScenarioFieldState
from app.security.actor import ActorContext
from app.services.scenario_draft_service import ScenarioDraftService
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_manual_draft_creates_structured_session_and_snapshot(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    draft = ScenarioDraftService().create(
        session,
        actor_contributor,
        title="Fleet readiness",
        sensitivity_level="INTERNAL",
    )

    assert draft.version == 1
    assert draft.origin == "MANUAL"
    assert draft.draft.scenario_name == "Fleet readiness"
    assert draft.draft.current_step == 1
    assert "equipment_model_id" in draft.blocking_fields
    assert draft.completion["basics"] is False
    assert (
        session.scalar(
            select(func.count(AISessionSnapshot.id)).where(
                AISessionSnapshot.session_id == draft.session_id
            )
        )
        == 1
    )


def test_save_requires_latest_snapshot_version(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    service = ScenarioDraftService()
    created = service.create(
        session,
        actor_contributor,
        title="Fleet readiness",
        sensitivity_level="INTERNAL",
    )
    payload = created.draft.model_copy(deep=True)
    payload.fields["mission_code"] = ScenarioFieldState(
        value="MISSION-30D",
        source="USER_INPUT",
        risk="LOW",
        confirmed=True,
    )

    saved = service.save(
        session,
        actor_contributor,
        created.session_id,
        expected_version=1,
        draft=payload,
    )

    assert saved.version == 2
    assert saved.draft.fields["mission_code"].value == "MISSION-30D"

    with pytest.raises(ConflictError) as exc:
        service.save(
            session,
            actor_contributor,
            created.session_id,
            expected_version=1,
            draft=saved.draft,
        )

    assert exc.value.code == "SCENARIO_DRAFT_VERSION_CONFLICT"
    assert exc.value.details["actual_version"] == 2
    assert exc.value.details["retryable"] is False
    assert exc.value.request_id == actor_contributor.request_id


def test_validate_recomputes_blocking_fields_from_server_rules(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    service = ScenarioDraftService()
    created = service.create(
        session,
        actor_contributor,
        title="Fleet readiness",
        sensitivity_level="INTERNAL",
    )
    payload = created.draft.model_copy(deep=True)
    payload.fields["service_level"] = ScenarioFieldState(
        value="0.95",
        source="AI_INFERRED",
        confidence="0.91",
        risk="BLOCKING",
        confirmed=False,
        evidence_refs=["manual:readiness-policy"],
    )

    saved = service.save(
        session,
        actor_contributor,
        created.session_id,
        expected_version=created.version,
        draft=payload,
    )
    validated = service.validate(
        session,
        actor_contributor,
        created.session_id,
    )

    assert saved.blocking_fields == validated.blocking_fields
    assert "service_level" in validated.blocking_fields
    assert validated.draft.fields["service_level"].confirmed is False


def test_foreign_tenant_draft_is_not_visible(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    local_actor = actor_context(tenant_id="tenant-a")
    foreign_actor = actor_context(tenant_id="tenant-b")
    foreign_draft = ScenarioDraftService().create(
        session,
        foreign_actor,
        title="Foreign",
        sensitivity_level="INTERNAL",
    )

    with pytest.raises(NotFoundError):
        ScenarioDraftService().get(
            session,
            local_actor,
            foreign_draft.session_id,
        )
