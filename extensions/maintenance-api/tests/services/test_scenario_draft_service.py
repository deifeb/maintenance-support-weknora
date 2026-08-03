from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    AISessionSnapshot,
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandParameterOverride,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
)
from app.schemas.scenario_draft import ScenarioFieldState
from app.security.actor import ActorContext
from app.services.scenario_draft_service import ScenarioDraftService
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.scenario_draft_factories import (
    complete_scenario_draft,
)


def _scenario_row_count(session: Session) -> int:
    models = (
        DemandScenarioTemplate,
        DemandScenarioVersion,
        DemandScenarioStage,
        DemandFleetGroup,
        DemandAgeGroup,
        DemandStageFleetUsage,
        DemandParameterOverride,
        DemandCommonShockRule,
    )
    return sum(
        int(
            session.scalar(
                select(func.count(model.id))
            )
            or 0
        )
        for model in models
    )


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


def test_materialize_creates_validated_draft_version(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    draft = complete_scenario_draft(
        session,
        actor_contributor,
    )

    result = ScenarioDraftService().materialize(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=draft.version,
        idempotency_key="scenario-materialize-1",
    )

    assert result.scenario_version.status.value == "DRAFT"
    assert result.validation.valid is True
    assert result.replayed is False
    assert result.scenario_version.id > 0


def test_materialize_rolls_back_all_rows_on_invalid_reference(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    draft = complete_scenario_draft(
        session,
        actor_contributor,
        code="SC-INVALID",
    )
    payload = draft.draft.model_copy(deep=True)
    fleet_groups = payload.fields["fleet_groups"].value
    assert isinstance(fleet_groups, list)
    fleet_groups[0]["configuration_version_id"] = 999999
    invalid = ScenarioDraftService().save(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=draft.version,
        draft=payload,
    )

    with pytest.raises(BusinessValidationError) as exc:
        ScenarioDraftService().materialize(
            session,
            actor_contributor,
            invalid.session_id,
            expected_version=invalid.version,
            idempotency_key="scenario-materialize-invalid",
        )

    assert exc.value.code == "SCENARIO_DRAFT_INVALID"
    assert _scenario_row_count(session) == 0


def test_materialize_replay_returns_same_version_before_version_check(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    draft = complete_scenario_draft(
        session,
        actor_contributor,
        code="SC-REPLAY",
    )
    service = ScenarioDraftService()

    first = service.materialize(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=draft.version,
        idempotency_key="stable-key",
    )
    second = service.materialize(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=draft.version,
        idempotency_key="stable-key",
    )

    assert (
        first.scenario_version.id
        == second.scenario_version.id
    )
    assert second.replayed is True
    assert _scenario_row_count(session) == 6


def test_materialize_rejects_reused_key_for_changed_draft(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    draft = complete_scenario_draft(
        session,
        actor_contributor,
        code="SC-REUSED",
    )
    service = ScenarioDraftService()
    service.materialize(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=draft.version,
        idempotency_key="reused-key",
    )
    latest = service.get(
        session,
        actor_contributor,
        draft.session_id,
    )
    changed_payload = latest.draft.model_copy(deep=True)
    changed_payload.scenario_name = "Changed name"
    changed = service.save(
        session,
        actor_contributor,
        draft.session_id,
        expected_version=latest.version,
        draft=changed_payload,
    )

    with pytest.raises(ConflictError) as exc:
        service.materialize(
            session,
            actor_contributor,
            draft.session_id,
            expected_version=changed.version,
            idempotency_key="reused-key",
        )

    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"
