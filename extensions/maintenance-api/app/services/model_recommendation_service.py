from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.models.enums import (
    DemandExecutionMode,
    ReliabilityModelType,
    ScenarioVersionStatus,
)
from app.repositories.demand_scenario_repository import (
    DemandScenarioVersionRepository,
)
from app.schemas.demand_calculation import CalculationPreviewRequest
from app.schemas.model_recommendation import (
    CandidateRecommendation,
    ModelRecommendationSet,
)
from app.security.actor import ActorContext
from app.services.demand_calculation_service import calculation_service

RULE_VERSION = "MODEL-RECOMMENDATION-1"
RELIABILITY_ORDER = tuple(ReliabilityModelType)
EXECUTION_ORDER = (
    DemandExecutionMode.ANALYTICAL,
    DemandExecutionMode.MONTE_CARLO,
)


def candidate_key(
    reliability_model: ReliabilityModelType,
    execution_mode: DemandExecutionMode,
) -> str:
    return (
        f"{reliability_model.value}:"
        f"{execution_mode.value}"
    )


def _all_items_have(
    items: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> bool:
    return bool(items) and all(predicate(item) for item in items)


def _reliability_parameters(
    item: dict[str, Any],
) -> dict[str, Any]:
    value = item.get("reliability")
    return value if isinstance(value, dict) else {}


def _has_positive(
    mapping: dict[str, Any],
    key: str,
) -> bool:
    value = mapping.get(key)
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _model_requirements(
    model: ReliabilityModelType,
    snapshot: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    items = list(snapshot.get("items") or [])
    stages = list(snapshot.get("stages") or [])
    missing: list[str] = []
    sources: dict[str, str] = {}

    if not items:
        missing.append("demand_items")
    if not stages or not all(
        _has_positive(stage, "duration_hours")
        for stage in stages
    ):
        missing.append("mission_duration")
    else:
        sources["mission_duration"] = "scenario_snapshot"
    if not _all_items_have(
        items,
        lambda item: _has_positive(
            item,
            "installed_positions",
        ),
    ):
        missing.append("installed_positions")
    else:
        sources["installed_positions"] = "scenario_snapshot"

    checks: dict[
        ReliabilityModelType,
        tuple[
            tuple[str, Callable[[dict[str, Any]], bool]],
            ...,
        ],
    ] = {
        ReliabilityModelType.EXPONENTIAL: (
            (
                "failure_rate_or_mtbf",
                lambda params: (
                    _has_positive(params, "failure_rate")
                    or _has_positive(params, "mtbf_hours")
                ),
            ),
        ),
        ReliabilityModelType.WEIBULL: (
            (
                "weibull_shape",
                lambda params: _has_positive(
                    params,
                    "weibull_shape",
                ),
            ),
            (
                "weibull_scale",
                lambda params: _has_positive(
                    params,
                    "weibull_scale",
                ),
            ),
        ),
        ReliabilityModelType.BINOMIAL: (
            (
                "binomial_trials",
                lambda params: _has_positive(
                    params,
                    "binomial_trials",
                ),
            ),
            (
                "binomial_probability",
                lambda params: (
                    params.get("binomial_probability") is not None
                    and 0
                    <= float(params["binomial_probability"])
                    <= 1
                ),
            ),
        ),
        ReliabilityModelType.NEGATIVE_BINOMIAL: (
            (
                "negative_binomial_r",
                lambda params: _has_positive(
                    params,
                    "negative_binomial_r",
                ),
            ),
            (
                "negative_binomial_p",
                lambda params: (
                    params.get("negative_binomial_p") is not None
                    and 0
                    < float(params["negative_binomial_p"])
                    <= 1
                ),
            ),
        ),
        ReliabilityModelType.EMPIRICAL: (
            (
                "empirical_mean",
                lambda params: (
                    params.get("empirical_mean") is not None
                    and float(params["empirical_mean"]) >= 0
                ),
            ),
            (
                "empirical_variance",
                lambda params: (
                    params.get("empirical_variance") is not None
                    and float(params["empirical_variance"]) >= 0
                ),
            ),
        ),
    }
    for requirement, predicate in checks[model]:
        if not _all_items_have(
            items,
            lambda item: predicate(
                _reliability_parameters(item)
            ),
        ):
            missing.append(requirement)
        else:
            sources[requirement] = "scenario_snapshot"
    return missing, sources


def _execution_requirements(
    mode: DemandExecutionMode,
    snapshot: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    if mode is DemandExecutionMode.ANALYTICAL:
        return [], {}

    simulation = snapshot.get("simulation")
    simulation = (
        simulation
        if isinstance(simulation, dict)
        else {}
    )
    missing = []
    sources = {
        "random_seed": "server_default:20260723",
    }
    if not _has_positive(simulation, "max_runs"):
        missing.append("simulation_max_runs")
    else:
        sources["simulation_max_runs"] = "scenario_snapshot"
    return missing, sources


def _score_candidate(
    model: ReliabilityModelType,
    mode: DemandExecutionMode,
    snapshot: dict[str, Any],
) -> tuple[int, list[str]]:
    items = list(snapshot.get("items") or [])
    reasons: list[str] = []
    model_score = {
        ReliabilityModelType.EXPONENTIAL: 55,
        ReliabilityModelType.WEIBULL: 60,
        ReliabilityModelType.BINOMIAL: 55,
        ReliabilityModelType.NEGATIVE_BINOMIAL: 55,
        ReliabilityModelType.EMPIRICAL: 50,
    }[model]
    if _all_items_have(
        items,
        lambda item: (
            _reliability_parameters(item).get("model_type")
            == model.value
        ),
    ):
        model_score += 15
        reasons.append("reliability_model_matches_snapshot")

    has_age = any(item.get("age_groups") for item in items)
    has_shock = any(
        item.get("common_shocks")
        for item in items
    )
    has_repair = any(item.get("repair") for item in items)
    multi_stage = len(snapshot.get("stages") or []) > 1

    if model is ReliabilityModelType.WEIBULL and has_age:
        model_score += 5
        reasons.append("age_distribution_available")

    if mode is DemandExecutionMode.ANALYTICAL:
        model_score += 12
        reasons.append("analytical_execution_is_efficient")
    else:
        model_score += 5
        if has_shock:
            model_score += 25
            reasons.append("common_shock_favors_simulation")
        if multi_stage:
            model_score += 10
            reasons.append("multi_stage_favors_simulation")
        if has_repair:
            model_score += 8
            reasons.append("repair_pipeline_favors_simulation")
        if has_age:
            model_score += 3
            reasons.append("age_distribution_favors_simulation")

    return min(model_score, 100), reasons


def _risk(
    *,
    applicable: bool,
    score: int,
) -> str:
    if not applicable or score < 65:
        return "HIGH"
    if score < 80:
        return "MEDIUM"
    return "LOW"


class ModelRecommendationService:
    def __init__(self) -> None:
        self.version_repository = (
            DemandScenarioVersionRepository()
        )
        self.snapshot_builder = calculation_service

    def recommend(
        self,
        session: Session,
        actor: ActorContext,
        scenario_version_id: int,
        *,
        explanation_hint: str | None = None,
    ) -> ModelRecommendationSet:
        del explanation_hint
        version = self.version_repository.get_by_id(
            session,
            actor.tenant_id,
            scenario_version_id,
        )
        if version is None:
            raise NotFoundError(
                "demand_scenario_version",
                scenario_version_id,
            )
        if version.status is not ScenarioVersionStatus.PUBLISHED:
            raise BusinessValidationError(
                "scenario version must be published",
                code="SCENARIO_NOT_PUBLISHED",
            )

        snapshot, warnings = self.snapshot_builder.build_snapshot(
            session,
            actor,
            CalculationPreviewRequest(
                scenario_version_id=scenario_version_id,
            ),
        )
        recommendations = []
        for model in RELIABILITY_ORDER:
            model_missing, model_sources = (
                _model_requirements(model, snapshot)
            )
            for mode in EXECUTION_ORDER:
                mode_missing, mode_sources = (
                    _execution_requirements(mode, snapshot)
                )
                missing = [*model_missing, *mode_missing]
                score, reasons = _score_candidate(
                    model,
                    mode,
                    snapshot,
                )
                applicable = not missing
                recommendations.append(
                    CandidateRecommendation(
                        candidate_key=candidate_key(
                            model,
                            mode,
                        ),
                        reliability_model=model,
                        execution_mode=mode,
                        applicable=applicable,
                        score=score,
                        reasons=reasons,
                        missing_requirements=missing,
                        parameter_sources={
                            **model_sources,
                            **mode_sources,
                        },
                        risk=_risk(
                            applicable=applicable,
                            score=score,
                        ),
                        rule_version=RULE_VERSION,
                    )
                )

        recommendations.sort(
            key=lambda item: (
                not item.applicable,
                -item.score,
                RELIABILITY_ORDER.index(
                    item.reliability_model
                ),
                EXECUTION_ORDER.index(item.execution_mode),
            )
        )
        primary = next(
            (
                item
                for item in recommendations
                if item.applicable
            ),
            None,
        )
        return ModelRecommendationSet(
            scenario_version_id=scenario_version_id,
            primary=primary,
            items=recommendations,
            rule_version=RULE_VERSION,
            warnings=warnings,
        )


model_recommendation_service = ModelRecommendationService()
