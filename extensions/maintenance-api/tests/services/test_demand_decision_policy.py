from decimal import Decimal
from importlib import import_module

import pytest
from app.models.enums import CalculationDecisionType


def _policy():
    try:
        return import_module(
            "app.services.demand_decision_policy"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "decision risk policy module is missing",
            pytrace=False,
        )


def _candidate(
    *,
    child_id: int = 1,
    recommended_quantity: str = "100",
    p50: str | None = "90",
    p99: str | None = "110",
    warnings: tuple[str, ...] = (),
):
    policy = _policy()
    return policy.DecisionCandidateEvidence(
        child_id=child_id,
        recommended_quantity=Decimal(
            recommended_quantity
        ),
        p50=Decimal(p50) if p50 is not None else None,
        p99=Decimal(p99) if p99 is not None else None,
        warnings=warnings,
    )


def _evaluate(
    *,
    source_child_id: int = 1,
    selected_child_id: int = 1,
    source_quantity: str = "100",
    selected_quantity: str = "100",
    final_quantity: str = "100",
    criticality_level: str | None = "MEDIUM",
    candidates=None,
):
    policy = _policy()
    evidence = (
        candidates
        if candidates is not None
        else (_candidate(),)
    )
    return policy.evaluate_decision_risk(
        source_child_id=source_child_id,
        selected_child_id=selected_child_id,
        source_quantity=Decimal(source_quantity),
        selected_quantity=Decimal(
            selected_quantity
        ),
        final_quantity=Decimal(final_quantity),
        criticality_level=criticality_level,
        successful_candidates=tuple(evidence),
    )


def test_default_system_quantity_is_low_risk() -> None:
    result = _evaluate()

    assert result.decision_type is (
        CalculationDecisionType.SYSTEM_RECOMMENDATION
    )
    assert result.risk == "LOW"
    assert result.requires_admin_confirmation is False
    assert (
        result.rule_version
        == "DEMAND-DECISION-RISK-1"
    )
    assert result.changed_candidate is False
    assert result.changed_quantity is False


def test_ten_percent_reduction_requires_admin() -> None:
    result = _evaluate(final_quantity="90")

    assert result.decision_type is (
        CalculationDecisionType.MANUAL_QUANTITY
    )
    assert result.risk == "HIGH"
    assert result.requires_admin_confirmation is True
    assert result.changed_quantity is True


def test_high_criticality_reduction_requires_admin() -> None:
    result = _evaluate(
        final_quantity="99",
        criticality_level="HIGH",
    )

    assert result.risk == "HIGH"
    assert result.requires_admin_confirmation is True


def test_outside_every_complete_interval_requires_admin() -> None:
    result = _evaluate(
        final_quantity="120",
        candidates=(
            _candidate(
                child_id=1,
                recommended_quantity="100",
                p50="90",
                p99="110",
            ),
            _candidate(
                child_id=2,
                recommended_quantity="105",
                p50="95",
                p99="115",
            ),
        ),
    )

    assert result.risk == "HIGH"
    assert result.requires_admin_confirmation is True


def test_incomplete_intervals_do_not_trigger_range_risk() -> None:
    result = _evaluate(
        final_quantity="120",
        candidates=(
            _candidate(
                p50=None,
                p99=None,
            ),
        ),
    )

    assert result.risk == "LOW"
    assert result.requires_admin_confirmation is False


def test_materially_different_alternative_requires_admin() -> None:
    result = _evaluate(
        selected_child_id=2,
        selected_quantity="120",
        final_quantity="120",
        candidates=(
            _candidate(child_id=1),
            _candidate(
                child_id=2,
                recommended_quantity="120",
                p50="110",
                p99="130",
            ),
        ),
    )

    assert result.decision_type is (
        CalculationDecisionType.ALTERNATIVE_CANDIDATE
    )
    assert result.risk == "HIGH"
    assert result.requires_admin_confirmation is True
    assert result.changed_candidate is True


@pytest.mark.parametrize(
    "warning",
    (
        "MISSING_PARAMETER",
        "simulation_non_convergence",
        "NOT_CONVERGED",
        "high_variance",
    ),
)
def test_material_warning_requires_admin(
    warning: str,
) -> None:
    result = _evaluate(
        candidates=(
            _candidate(warnings=(warning,)),
        ),
    )

    assert result.risk == "HIGH"
    assert result.requires_admin_confirmation is True
