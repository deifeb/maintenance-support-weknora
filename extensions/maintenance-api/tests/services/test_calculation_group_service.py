from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
)
from app.models import DemandScenarioTemplate, DemandScenarioVersion
from app.models.enums import (
    DemandExecutionMode,
    ReliabilityModelType,
    ScenarioVersionStatus,
)
from app.security.actor import ActorContext
from app.services.calculation_group_service import (
    CalculationGroupService,
)
from app.services.demand_calculation_service import (
    CandidateExecutionSpec,
)
from sqlalchemy.orm import Session


def add_version(
    session: Session,
    tenant_id: str,
    *,
    status: ScenarioVersionStatus = ScenarioVersionStatus.PUBLISHED,
) -> DemandScenarioVersion:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"GROUP-{tenant_id}-{status.value}",
        name="Calculation group scenario",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=status,
    )
    session.add(version)
    session.flush()
    return version


def compatible_snapshot() -> dict[str, Any]:
    return {
        "stages": [
            {
                "code": "S1",
                "duration_hours": "24",
            }
        ],
        "simulation": {"max_runs": 50000},
        "items": [
            {
                "installed_positions": "10",
                "reliability": {
                    "model_type": "WEIBULL",
                    "failure_rate": "0.001",
                    "weibull_shape": "1.8",
                    "weibull_scale": "1000",
                    "binomial_trials": 10,
                    "binomial_probability": "0.1",
                    "negative_binomial_r": "2",
                    "negative_binomial_p": "0.5",
                    "empirical_mean": "3",
                    "empirical_variance": "4",
                },
                "age_groups": [
                    {
                        "distribution_type": "FIXED",
                        "fixed_hours": "100",
                    }
                ],
                "common_shocks": [],
            }
        ],
    }


def service_with_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[str, Any] | None = None,
) -> CalculationGroupService:
    service = CalculationGroupService()
    trusted_snapshot = snapshot or compatible_snapshot()
    monkeypatch.setattr(
        service.calculation_service,
        "build_snapshot",
        lambda *args, **kwargs: (trusted_snapshot, []),
    )
    return service


def test_candidate_execution_spec_is_immutable() -> None:
    spec = CandidateExecutionSpec(
        candidate_key="WEIBULL:ANALYTICAL",
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        random_seed=20260723,
    )

    with pytest.raises(FrozenInstanceError):
        spec.random_seed = 1  # type: ignore[misc]


def test_group_creates_one_calculation_per_selected_candidate(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)

    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="group-create-1",
    )

    assert len(group.current_children) == 3
    assert len(
        {
            child.calculation_id
            for child in group.current_children
        }
    ) == 3
    assert all(
        child.attempt_number == 1
        for child in group.current_children
    )
    assert {
        child.calculation.requested_mode
        for child in group.current_children
    } == {
        DemandExecutionMode.ANALYTICAL,
        DemandExecutionMode.MONTE_CARLO,
    }
    assert group.last_event_sequence == 4


def test_candidate_submission_overrides_only_trusted_model_field(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)

    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="EXPONENTIAL:ANALYTICAL",
        selected_candidate_keys=[
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="trusted-candidate",
    )

    calculation = group.current_children[0].calculation
    snapshot = calculation.input_snapshot_json
    assert snapshot["candidate_key"] == (
        "EXPONENTIAL:ANALYTICAL"
    )
    assert snapshot["items"][0]["reliability"]["model_type"] == (
        "EXPONENTIAL"
    )
    assert snapshot["items"][0]["reliability"][
        "failure_rate"
    ] == "0.001"
    assert snapshot["random_seed"] == 20260723


def test_group_rejects_unpublished_scenario(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
        status=ScenarioVersionStatus.DRAFT,
    )

    with pytest.raises(ConflictError) as exc:
        CalculationGroupService().create(
            session,
            actor_contributor,
            scenario_version_id=version.id,
            primary_candidate_key="WEIBULL:ANALYTICAL",
            selected_candidate_keys=[
                "WEIBULL:ANALYTICAL",
            ],
            idempotency_key="unpublished",
        )

    assert exc.value.code == "SCENARIO_NOT_PUBLISHED"


def test_group_creation_is_idempotent_and_detects_key_reuse(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)
    request = {
        "scenario_version_id": version.id,
        "primary_candidate_key": "WEIBULL:ANALYTICAL",
        "selected_candidate_keys": [
            "WEIBULL:ANALYTICAL",
        ],
        "idempotency_key": "same-key",
    }

    first = service.create(
        session,
        actor_contributor,
        **request,
    )
    replay = service.create(
        session,
        actor_contributor,
        **request,
    )

    assert replay.id == first.id
    with pytest.raises(ConflictError) as exc:
        service.create(
            session,
            actor_contributor,
            **{
                **request,
                "selected_candidate_keys": [
                    "WEIBULL:ANALYTICAL",
                    "WEIBULL:MONTE_CARLO",
                ],
            },
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_group_rejects_inapplicable_candidate(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    snapshot = compatible_snapshot()
    snapshot["items"][0]["reliability"].pop("failure_rate")
    service = service_with_snapshot(monkeypatch, snapshot)

    with pytest.raises(BusinessValidationError) as exc:
        service.create(
            session,
            actor_contributor,
            scenario_version_id=version.id,
            primary_candidate_key="EXPONENTIAL:ANALYTICAL",
            selected_candidate_keys=[
                "EXPONENTIAL:ANALYTICAL",
            ],
            idempotency_key="inapplicable",
        )

    assert exc.value.code == "CANDIDATE_NOT_APPLICABLE"
