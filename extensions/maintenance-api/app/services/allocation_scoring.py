from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.core.exceptions import BusinessValidationError

_SCORE_QUANTUM = Decimal("0.000001")
_ONE = Decimal("1.000000")
_ZERO = Decimal("0.000000")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    balance_id: int
    score: Decimal
    normalized_metrics: dict[str, Decimal]
    candidate: Any


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise BusinessValidationError(
            "allocation values must use exact decimals",
            code="ALLOCATION_RULE_VERSION_CONFLICT",
        )
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BusinessValidationError(
            "allocation value is not a valid decimal",
            code="ALLOCATION_RULE_VERSION_CONFLICT",
        ) from exc
    if not result.is_finite():
        raise BusinessValidationError(
            "allocation value must be finite",
            code="ALLOCATION_RULE_VERSION_CONFLICT",
        )
    return result


def validate_weights(weights: Mapping[str, Decimal]) -> None:
    total = sum((_decimal(value) for value in weights.values()), Decimal("0"))
    if total != _ONE:
        raise BusinessValidationError(
            "Allocation weights must sum to 1.000000",
            code="ALLOCATION_RULE_VERSION_CONFLICT",
            details={"actual_total": str(total)},
        )


def _passes_hard_rules(hard_rules: Mapping[str, Any], candidate: Any) -> bool:
    if hard_rules.get("exclude_frozen") and bool(getattr(candidate, "frozen", False)):
        return False
    if hard_rules.get("exclude_expired") and bool(getattr(candidate, "expired", False)):
        return False
    if hard_rules.get("require_available") and not bool(
        getattr(candidate, "available", False)
    ):
        return False
    return True


def _normalize_metric(value: Any, bounds: Mapping[str, Any]) -> Decimal:
    observed = _decimal(value)
    minimum = _decimal(bounds["min"])
    maximum = _decimal(bounds["max"])
    if maximum <= minimum:
        raise BusinessValidationError(
            "normalization max must be greater than min",
            code="ALLOCATION_RULE_VERSION_CONFLICT",
        )
    clamped = min(max(observed, minimum), maximum)
    return ((clamped - minimum) / (maximum - minimum)).quantize(_SCORE_QUANTUM)


def _tie_break(item: RankedCandidate) -> tuple[Any, ...]:
    candidate = item.candidate
    expiry = getattr(candidate, "expiry_date", None)
    if expiry is None:
        expiry = date.max
    return (
        -item.score,
        int(getattr(candidate, "warehouse_priority", 2**31 - 1)),
        int(getattr(candidate, "location_priority", 2**31 - 1)),
        expiry,
        str(getattr(candidate, "lot_code", "")),
        int(item.balance_id),
    )


def rank_candidates(rule: Any, candidates: Sequence[Any]) -> list[RankedCandidate]:
    weights = {key: _decimal(value) for key, value in rule.weights.items()}
    validate_weights(weights)

    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        if not _passes_hard_rules(rule.hard_rules, candidate):
            continue
        normalized: dict[str, Decimal] = {}
        score = Decimal("0")
        metrics = getattr(candidate, "metrics", {})
        for key, weight in weights.items():
            if key not in rule.normalization or key not in metrics:
                raise BusinessValidationError(
                    "scoring input is missing a configured metric",
                    code="ALLOCATION_RULE_VERSION_CONFLICT",
                    details={"metric": key},
                )
            value = _normalize_metric(metrics[key], rule.normalization[key])
            normalized[key] = value
            score += weight * value
        ranked.append(
            RankedCandidate(
                balance_id=int(candidate.balance_id),
                score=score.quantize(_SCORE_QUANTUM),
                normalized_metrics=normalized,
                candidate=candidate,
            )
        )

    ranked.sort(key=_tie_break)
    return ranked