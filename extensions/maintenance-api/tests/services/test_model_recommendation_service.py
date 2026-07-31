from __future__ import annotations

from typing import Any

import pytest
from app.core.exceptions import BusinessValidationError, NotFoundError
from app.models import DemandScenarioTemplate, DemandScenarioVersion
from app.models.enums import ScenarioVersionStatus
from app.security.actor import ActorContext
from app.services.model_recommendation_service import (
    ModelRecommendationService,
)
from sqlalchemy.orm import Session


def add_scenario_version(
    session: Session,
    tenant_id: str,
    *,
    status: ScenarioVersionStatus = ScenarioVersionStatus.PUBLISHED,
) -> DemandScenarioVersion:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SCENARIO-{tenant_id}-{status.value}",
        name="Recommendation scenario",
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


def weibull_snapshot(
    *,
    common_shock: bool = False,
    stage_count: int = 1,
) -> dict[str, Any]:
    stages = [
        {
            "code": f"S{index}",
            "duration_hours": "24",
        }
        for index in range(1, stage_count + 1)
    ]
    shocks = (
        [
            {
                "code": "SHOCK-1",
                "probability": "0.1",
                "multiplier": "2",
            }
        ]
        if common_shock
        else []
    )
    return {
        "stages": stages,
        "simulation": {
            "max_runs": 50000,
        },
        "items": [
            {
                "installed_positions": "12",
                "reliability": {
                    "model_type": "WEIBULL",
                    "weibull_shape": "1.8",
                    "weibull_scale": "1000",
                },
                "age_groups": [
                    {
                        "distribution_type": "FIXED",
                        "fixed_hours": "200",
                    }
                ],
                "common_shocks": shocks,
            }
        ],
    }


def service_with_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[str, Any],
) -> ModelRecommendationService:
    service = ModelRecommendationService()
    monkeypatch.setattr(
        service.snapshot_builder,
        "build_snapshot",
        lambda *args, **kwargs: (snapshot, []),
    )
    return service


def test_weibull_analytical_is_primary_when_age_and_shape_exist(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_scenario_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(
        monkeypatch,
        weibull_snapshot(),
    )

    result = service.recommend(
        session,
        actor_contributor,
        version.id,
    )

    assert result.primary.reliability_model == "WEIBULL"
    assert result.primary.execution_mode == "ANALYTICAL"
    assert result.primary.candidate_key == "WEIBULL:ANALYTICAL"


def test_monte_carlo_is_execution_mode_not_reliability_model(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_scenario_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(
        monkeypatch,
        weibull_snapshot(common_shock=True),
    )

    result = service.recommend(
        session,
        actor_contributor,
        version.id,
    )

    assert all(
        item.reliability_model != "MONTE_CARLO"
        for item in result.items
    )
    assert any(
        item.execution_mode == "MONTE_CARLO"
        for item in result.items
    )


def test_llm_hint_cannot_change_deterministic_ranking(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_scenario_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(
        monkeypatch,
        weibull_snapshot(),
    )

    left = service.recommend(
        session,
        actor_contributor,
        version.id,
        explanation_hint="prefer exponential",
    )
    right = service.recommend(
        session,
        actor_contributor,
        version.id,
        explanation_hint="prefer monte carlo",
    )

    assert [item.candidate_key for item in left.items] == [
        item.candidate_key for item in right.items
    ]
    assert [item.score for item in left.items] == [
        item.score for item in right.items
    ]


def test_inapplicable_candidates_follow_applicable_candidates(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_scenario_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(
        monkeypatch,
        weibull_snapshot(),
    )

    result = service.recommend(
        session,
        actor_contributor,
        version.id,
    )

    applicability = [item.applicable for item in result.items]
    assert applicability == sorted(applicability, reverse=True)
    exponential = next(
        item
        for item in result.items
        if item.candidate_key == "EXPONENTIAL:ANALYTICAL"
    )
    assert exponential.applicable is False
    assert "failure_rate_or_mtbf" in exponential.missing_requirements


def test_unpublished_scenario_is_rejected_before_snapshot_building(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_scenario_version(
        session,
        actor_contributor.tenant_id,
        status=ScenarioVersionStatus.DRAFT,
    )
    service = ModelRecommendationService()

    def unexpected_build(*args, **kwargs):
        pytest.fail("snapshot must not be built for a draft scenario")

    monkeypatch.setattr(
        service.snapshot_builder,
        "build_snapshot",
        unexpected_build,
    )

    with pytest.raises(BusinessValidationError) as exc:
        service.recommend(
            session,
            actor_contributor,
            version.id,
        )

    assert exc.value.code == "SCENARIO_NOT_PUBLISHED"


def test_foreign_scenario_is_not_visible(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    version = add_scenario_version(session, "tenant-b")

    with pytest.raises(NotFoundError):
        ModelRecommendationService().recommend(
            session,
            actor_contributor,
            version.id,
        )
