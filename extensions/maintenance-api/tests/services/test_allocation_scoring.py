from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal
from types import ModuleType, SimpleNamespace

import pytest
from app.core.exceptions import AppException


def _scoring_api() -> ModuleType:
    try:
        return importlib.import_module("app.services.allocation_scoring")
    except ModuleNotFoundError as exc:
        if exc.name == "app.services.allocation_scoring":
            pytest.fail("Task 2 RED requires app.services.allocation_scoring")
        raise


def _rule(**overrides):
    values = {
        "hard_rules": {
            "exclude_frozen": True,
            "exclude_expired": True,
            "require_available": True,
        },
        "weights": {
            "criticality": Decimal("0.600000"),
            "availability": Decimal("0.400000"),
        },
        "normalization": {
            "criticality": {"min": Decimal("0"), "max": Decimal("10")},
            "availability": {"min": Decimal("0"), "max": Decimal("10")},
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _candidate(
    balance_id: int,
    *,
    criticality: str = "5",
    availability: str = "5",
    warehouse_priority: int = 1,
    location_priority: int = 1,
    expiry_date: date | None = date(2026, 9, 1),
    lot_code: str = "LOT-001",
    frozen: bool = False,
    expired: bool = False,
    available: bool = True,
):
    return SimpleNamespace(
        balance_id=balance_id,
        metrics={
            "criticality": Decimal(criticality),
            "availability": Decimal(availability),
        },
        warehouse_priority=warehouse_priority,
        location_priority=location_priority,
        expiry_date=expiry_date,
        lot_code=lot_code,
        frozen=frozen,
        expired=expired,
        available=available,
    )


@pytest.mark.parametrize(
    "weights",
    [
        {"criticality": Decimal("0.600000"), "availability": Decimal("0.400001")},
        {"criticality": Decimal("0.600000"), "availability": Decimal("0.399999")},
    ],
)
def test_weights_must_sum_exactly_to_one(weights) -> None:
    api = _scoring_api()

    with pytest.raises(AppException) as raised:
        api.validate_weights(weights)

    assert raised.value.code == "ALLOCATION_RULE_VERSION_CONFLICT"


def test_exact_decimal_weights_are_accepted() -> None:
    api = _scoring_api()

    api.validate_weights(
        {
            "criticality": Decimal("0.600000"),
            "availability": Decimal("0.400000"),
        }
    )


def test_hard_rules_filter_before_scoring() -> None:
    api = _scoring_api()
    candidates = [
        _candidate(1),
        _candidate(2, frozen=True, criticality="10", availability="10"),
        _candidate(3, expired=True, criticality="10", availability="10"),
        _candidate(4, available=False, criticality="10", availability="10"),
    ]

    ranked = api.rank_candidates(_rule(), candidates)

    assert [item.balance_id for item in ranked] == [1]


def test_scoring_is_input_order_independent() -> None:
    api = _scoring_api()
    candidates = [
        _candidate(11, criticality="9", availability="3"),
        _candidate(12, criticality="6", availability="8"),
        _candidate(13, criticality="4", availability="9"),
    ]

    first = api.rank_candidates(_rule(), candidates)
    second = api.rank_candidates(_rule(), list(reversed(candidates)))

    assert [item.balance_id for item in first] == [item.balance_id for item in second]
    assert [item.score for item in first] == [item.score for item in second]


def test_equal_scores_use_full_deterministic_tie_break() -> None:
    api = _scoring_api()
    candidates = [
        _candidate(
            5,
            warehouse_priority=2,
            location_priority=1,
            expiry_date=date(2026, 8, 20),
            lot_code="LOT-A",
        ),
        _candidate(
            4,
            warehouse_priority=1,
            location_priority=2,
            expiry_date=date(2026, 8, 20),
            lot_code="LOT-A",
        ),
        _candidate(
            3,
            warehouse_priority=1,
            location_priority=1,
            expiry_date=date(2026, 8, 25),
            lot_code="LOT-A",
        ),
        _candidate(
            2,
            warehouse_priority=1,
            location_priority=1,
            expiry_date=date(2026, 8, 20),
            lot_code="LOT-B",
        ),
        _candidate(
            1,
            warehouse_priority=1,
            location_priority=1,
            expiry_date=date(2026, 8, 20),
            lot_code="LOT-A",
        ),
    ]

    ranked = api.rank_candidates(_rule(), candidates)

    assert [item.balance_id for item in ranked] == [1, 2, 3, 4, 5]


def test_scores_are_decimal_and_quantized_to_six_places() -> None:
    api = _scoring_api()

    ranked = api.rank_candidates(
        _rule(),
        [_candidate(1, criticality="7.3", availability="4.2")],
    )

    assert isinstance(ranked[0].score, Decimal)
    assert ranked[0].score == ranked[0].score.quantize(Decimal("0.000001"))


def test_normalization_clamps_out_of_range_values() -> None:
    api = _scoring_api()

    ranked = api.rank_candidates(
        _rule(
            weights={"criticality": Decimal("1.000000")},
            normalization={
                "criticality": {"min": Decimal("0"), "max": Decimal("10")}
            },
        ),
        [
            _candidate(1, criticality="-5"),
            _candidate(2, criticality="50"),
        ],
    )

    scores = {item.balance_id: item.score for item in ranked}
    assert scores[1] == Decimal("0.000000")
    assert scores[2] == Decimal("1.000000")