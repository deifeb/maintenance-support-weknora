from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import CalculationDecisionType

DEMAND_DECISION_RISK_RULE_VERSION = "DEMAND-DECISION-RISK-1"

_MATERIAL_WARNING_TOKENS = (
    "MISSING",
    "NON_CONVERGENCE",
    "NOT_CONVERGED",
    "HIGH",
)


@dataclass(frozen=True, slots=True)
class DecisionCandidateEvidence:
    child_id: int
    recommended_quantity: Decimal
    p50: Decimal | None
    p99: Decimal | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionRiskEvaluation:
    decision_type: CalculationDecisionType
    risk: str
    requires_admin_confirmation: bool
    rule_version: str
    changed_candidate: bool
    changed_quantity: bool


def _has_material_warning(warnings: tuple[str, ...]) -> bool:
    return any(
        any(
            token in warning.upper()
            for token in _MATERIAL_WARNING_TOKENS
        )
        for warning in warnings
    )


def evaluate_decision_risk(
    *,
    source_child_id: int,
    selected_child_id: int,
    source_quantity: Decimal,
    selected_quantity: Decimal,
    final_quantity: Decimal,
    criticality_level: str | None,
    successful_candidates: tuple[
        DecisionCandidateEvidence,
        ...,
    ],
) -> DecisionRiskEvaluation:
    changed_candidate = selected_child_id != source_child_id
    changed_quantity = final_quantity != selected_quantity

    ten_percent_reduction = (
        selected_quantity > 0
        and final_quantity
        <= selected_quantity * Decimal("0.90")
    )
    critical_reduction = (
        (criticality_level or "").upper()
        in {"HIGH", "CRITICAL"}
        and final_quantity < selected_quantity
    )

    complete_intervals = tuple(
        candidate
        for candidate in successful_candidates
        if candidate.p50 is not None
        and candidate.p99 is not None
    )
    outside_all_ranges = (
        bool(complete_intervals)
        and all(
            final_quantity < candidate.p50
            or final_quantity > candidate.p99
            for candidate in complete_intervals
        )
    )

    non_primary_material_difference = (
        changed_candidate
        and source_quantity > 0
        and abs(selected_quantity - source_quantity)
        / source_quantity
        >= Decimal("0.10")
    )

    selected_evidence = next(
        (
            candidate
            for candidate in successful_candidates
            if candidate.child_id == selected_child_id
        ),
        None,
    )
    material_warning = (
        selected_evidence is not None
        and _has_material_warning(
            selected_evidence.warnings
        )
    )

    requires_admin_confirmation = any(
        (
            ten_percent_reduction,
            critical_reduction,
            outside_all_ranges,
            non_primary_material_difference,
            material_warning,
        )
    )

    if changed_quantity:
        decision_type = (
            CalculationDecisionType.MANUAL_QUANTITY
        )
    elif changed_candidate:
        decision_type = (
            CalculationDecisionType.ALTERNATIVE_CANDIDATE
        )
    else:
        decision_type = (
            CalculationDecisionType.SYSTEM_RECOMMENDATION
        )

    return DecisionRiskEvaluation(
        decision_type=decision_type,
        risk=(
            "HIGH"
            if requires_admin_confirmation
            else "LOW"
        ),
        requires_admin_confirmation=(
            requires_admin_confirmation
        ),
        rule_version=DEMAND_DECISION_RISK_RULE_VERSION,
        changed_candidate=changed_candidate,
        changed_quantity=changed_quantity,
    )
