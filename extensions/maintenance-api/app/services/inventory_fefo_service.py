from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_ZERO = Decimal("0.0000")


@dataclass(frozen=True)
class FEFOCandidate:
    balance_id: int
    location_id: int
    lot_id: int | None
    serial_item_id: int | None
    expiry_date: date | None
    received_date: date | None
    available_quantity: Decimal
    exclusion_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class FEFOSelectionLine:
    balance_id: int
    quantity: Decimal
    rank: int


@dataclass(frozen=True)
class FEFOExcludedCandidate:
    balance_id: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FEFOSelection:
    lines: tuple[FEFOSelectionLine, ...]
    unfilled_quantity: Decimal
    warnings: tuple[str, ...]
    excluded: tuple[FEFOExcludedCandidate, ...]


def select_fefo(
    candidates: Sequence[FEFOCandidate],
    requested_quantity: Decimal,
    *,
    as_of: date,
) -> FEFOSelection:
    """Select inventory in deterministic first-expiry-first-out order.

    The selector is intentionally pure: the caller supplies all candidate facts and
    the evaluation date. Database reads, logging, and wall-clock access belong to
    the repository/application layers.
    """

    requested = Decimal(requested_quantity)
    if requested < _ZERO:
        raise ValueError("requested_quantity must be non-negative")

    eligible: list[FEFOCandidate] = []
    excluded: list[FEFOExcludedCandidate] = []

    for candidate in candidates:
        reason_codes = _exclusion_reasons(candidate, as_of=as_of)
        if reason_codes:
            excluded.append(
                FEFOExcludedCandidate(
                    balance_id=candidate.balance_id,
                    reason_codes=reason_codes,
                )
            )
        else:
            eligible.append(candidate)

    eligible.sort(key=_selection_key)
    excluded.sort(key=lambda item: item.balance_id)

    remaining = requested
    lines: list[FEFOSelectionLine] = []
    for candidate in eligible:
        if remaining <= _ZERO:
            break
        quantity = min(candidate.available_quantity, remaining)
        if quantity <= _ZERO:
            continue
        lines.append(
            FEFOSelectionLine(
                balance_id=candidate.balance_id,
                quantity=quantity,
                rank=len(lines) + 1,
            )
        )
        remaining -= quantity

    warnings = (
        ("INSUFFICIENT_AVAILABLE_INVENTORY",)
        if remaining > _ZERO
        else ()
    )
    return FEFOSelection(
        lines=tuple(lines),
        unfilled_quantity=max(remaining, _ZERO),
        warnings=warnings,
        excluded=tuple(excluded),
    )


def _exclusion_reasons(
    candidate: FEFOCandidate,
    *,
    as_of: date,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.expiry_date is not None and candidate.expiry_date < as_of:
        reasons.append("EXPIRED")
    reasons.extend(candidate.exclusion_facts)
    if candidate.available_quantity <= _ZERO:
        reasons.append("NO_AVAILABLE_QUANTITY")
    return tuple(dict.fromkeys(reasons))


def _selection_key(candidate: FEFOCandidate) -> tuple:
    return (
        candidate.expiry_date is None,
        candidate.expiry_date or date.max,
        candidate.received_date is None,
        candidate.received_date or date.max,
        candidate.lot_id is None,
        candidate.lot_id or 0,
        candidate.location_id,
        candidate.balance_id,
        candidate.serial_item_id is None,
        candidate.serial_item_id or 0,
    )
