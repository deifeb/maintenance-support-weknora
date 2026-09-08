from __future__ import annotations

import importlib
import itertools
from datetime import date
from decimal import Decimal
from types import ModuleType

import pytest


def _fefo_api() -> ModuleType:
    try:
        return importlib.import_module("app.services.inventory_fefo_service")
    except ModuleNotFoundError as exc:
        if exc.name == "app.services.inventory_fefo_service":
            pytest.fail("Task 3 requires app.services.inventory_fefo_service")
        raise


def _candidate(
    *,
    balance_id: int,
    available: str,
    expiry: date | None,
    received: date | None,
    lot_id: int | None,
    location_id: int,
    serial_item_id: int | None = None,
    exclusion_facts: tuple[str, ...] = (),
):
    api = _fefo_api()
    return api.FEFOCandidate(
        balance_id=balance_id,
        location_id=location_id,
        lot_id=lot_id,
        serial_item_id=serial_item_id,
        expiry_date=expiry,
        received_date=received,
        available_quantity=Decimal(available),
        exclusion_facts=exclusion_facts,
    )


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (Decimal("3.0000"), [(11, "3.0000")]),
        (Decimal("7.0000"), [(11, "5.0000"), (12, "2.0000")]),
    ],
)
def test_fefo_is_deterministic(requested, expected) -> None:
    api = _fefo_api()
    candidates = (
        _candidate(
            balance_id=11,
            available="5.0000",
            expiry=date(2026, 8, 10),
            received=date(2026, 7, 1),
            lot_id=1,
            location_id=1,
        ),
        _candidate(
            balance_id=12,
            available="5.0000",
            expiry=date(2026, 8, 20),
            received=date(2026, 7, 2),
            lot_id=2,
            location_id=1,
        ),
    )

    result = api.select_fefo(
        tuple(reversed(candidates)),
        requested,
        as_of=date(2026, 8, 4),
    )

    assert [
        (line.balance_id, format(line.quantity, ".4f"))
        for line in result.lines
    ] == expected
    assert [line.rank for line in result.lines] == list(range(1, len(expected) + 1))


def test_fefo_puts_missing_expiry_and_received_dates_last() -> None:
    api = _fefo_api()
    candidates = (
        _candidate(
            balance_id=31,
            available="1.0000",
            expiry=None,
            received=date(2026, 6, 1),
            lot_id=1,
            location_id=1,
        ),
        _candidate(
            balance_id=32,
            available="1.0000",
            expiry=date(2026, 8, 20),
            received=None,
            lot_id=2,
            location_id=1,
        ),
        _candidate(
            balance_id=33,
            available="1.0000",
            expiry=date(2026, 8, 20),
            received=date(2026, 6, 1),
            lot_id=3,
            location_id=1,
        ),
    )

    result = api.select_fefo(candidates, Decimal("3.0000"), as_of=date(2026, 8, 4))

    assert [line.balance_id for line in result.lines] == [33, 32, 31]


def test_fefo_uses_lot_location_and_balance_tie_breakers() -> None:
    api = _fefo_api()
    common = {
        "available": "1.0000",
        "expiry": date(2026, 8, 20),
        "received": date(2026, 6, 1),
    }
    candidates = (
        _candidate(balance_id=44, lot_id=None, location_id=1, **common),
        _candidate(balance_id=43, lot_id=2, location_id=1, **common),
        _candidate(balance_id=42, lot_id=1, location_id=2, **common),
        _candidate(balance_id=41, lot_id=1, location_id=1, **common),
        _candidate(balance_id=40, lot_id=1, location_id=1, **common),
    )

    result = api.select_fefo(candidates, Decimal("5.0000"), as_of=date(2026, 8, 4))

    assert [line.balance_id for line in result.lines] == [40, 41, 42, 43, 44]


def test_fefo_is_invariant_under_input_permutations() -> None:
    api = _fefo_api()
    candidates = (
        _candidate(
            balance_id=51,
            available="2.0000",
            expiry=date(2026, 8, 10),
            received=date(2026, 7, 1),
            lot_id=1,
            location_id=1,
        ),
        _candidate(
            balance_id=52,
            available="2.0000",
            expiry=date(2026, 8, 11),
            received=date(2026, 7, 1),
            lot_id=2,
            location_id=1,
        ),
        _candidate(
            balance_id=53,
            available="2.0000",
            expiry=None,
            received=None,
            lot_id=None,
            location_id=2,
        ),
    )

    selections = {
        tuple(
            (line.balance_id, format(line.quantity, ".4f"))
            for line in api.select_fefo(
                permutation,
                Decimal("4.0000"),
                as_of=date(2026, 8, 4),
            ).lines
        )
        for permutation in itertools.permutations(candidates)
    }

    assert selections == {((51, "2.0000"), (52, "2.0000"))}


def test_fefo_excludes_candidates_with_stable_reason_codes() -> None:
    api = _fefo_api()
    candidates = (
        _candidate(
            balance_id=61,
            available="1.0000",
            expiry=date(2026, 8, 3),
            received=date(2026, 7, 1),
            lot_id=1,
            location_id=1,
        ),
        _candidate(
            balance_id=62,
            available="1.0000",
            expiry=date(2026, 8, 10),
            received=date(2026, 7, 1),
            lot_id=2,
            location_id=1,
            exclusion_facts=("LOT_FROZEN",),
        ),
        _candidate(
            balance_id=63,
            available="1.0000",
            expiry=date(2026, 8, 10),
            received=date(2026, 7, 1),
            lot_id=3,
            location_id=1,
            exclusion_facts=("LOT_QUALITY_QUARANTINED",),
        ),
        _candidate(
            balance_id=64,
            available="1.0000",
            expiry=None,
            received=None,
            lot_id=None,
            location_id=2,
            exclusion_facts=("LOCATION_INACTIVE", "LOCATION_NOT_PICKABLE"),
        ),
        _candidate(
            balance_id=65,
            available="1.0000",
            expiry=None,
            received=None,
            lot_id=4,
            location_id=3,
            serial_item_id=900,
            exclusion_facts=("SERIAL_STATUS_RESERVED",),
        ),
        _candidate(
            balance_id=66,
            available="0.0000",
            expiry=None,
            received=None,
            lot_id=None,
            location_id=4,
        ),
    )

    result = api.select_fefo(candidates, Decimal("1.0000"), as_of=date(2026, 8, 4))

    assert result.lines == ()
    assert {
        item.balance_id: item.reason_codes
        for item in result.excluded
    } == {
        61: ("EXPIRED",),
        62: ("LOT_FROZEN",),
        63: ("LOT_QUALITY_QUARANTINED",),
        64: ("LOCATION_INACTIVE", "LOCATION_NOT_PICKABLE"),
        65: ("SERIAL_STATUS_RESERVED",),
        66: ("NO_AVAILABLE_QUANTITY",),
    }


def test_fefo_reports_unfilled_quantity_for_partial_selection() -> None:
    api = _fefo_api()
    candidates = (
        _candidate(
            balance_id=71,
            available="2.0000",
            expiry=date(2026, 8, 10),
            received=date(2026, 7, 1),
            lot_id=1,
            location_id=1,
        ),
        _candidate(
            balance_id=72,
            available="1.5000",
            expiry=date(2026, 8, 11),
            received=date(2026, 7, 2),
            lot_id=2,
            location_id=1,
        ),
    )

    result = api.select_fefo(candidates, Decimal("5.0000"), as_of=date(2026, 8, 4))

    assert [format(line.quantity, ".4f") for line in result.lines] == ["2.0000", "1.5000"]
    assert result.unfilled_quantity == Decimal("1.5000")
    assert result.warnings
