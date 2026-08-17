from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import ORMModel
from app.schemas.inventory_ledger import MAX_INVENTORY_QUANTITY

_QUANTITY_QUANTUM = Decimal("0.0001")
_ZERO = Decimal("0.0000")


def _exact_quantity(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("quantity must be an exact decimal value")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
        quantized = decimal_value.quantize(_QUANTITY_QUANTUM)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("quantity must fit Numeric(18,4)") from exc
    if not decimal_value.is_finite() or decimal_value != quantized:
        raise ValueError("quantity must have at most four decimal places")
    if abs(quantized) > MAX_INVENTORY_QUANTITY:
        raise ValueError("quantity must fit Numeric(18,4)")
    if positive and quantized <= _ZERO:
        raise ValueError("quantity must be greater than zero")
    if not positive and quantized < _ZERO:
        raise ValueError("quantity must be non-negative")
    return quantized


class ReserveCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_type: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=128)
    spare_part_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    requested_quantity: Decimal
    allow_partial: bool = False
    expected_balance_versions: dict[int, int]
    as_of: date
    location_id: int | None = Field(default=None, gt=0)
    lot_id: int | None = Field(default=None, gt=0)
    serial_item_id: int | None = Field(default=None, gt=0)
    expires_at: datetime | None = None
    fefo_override_reason: str | None = Field(default=None, max_length=500)

    @field_validator("requested_quantity", mode="before")
    @classmethod
    def validate_requested_quantity(cls, value: Any) -> Decimal:
        return _exact_quantity(value, positive=True)

    @field_validator("owner_type", "owner_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("fefo_override_reason")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("expected_balance_versions")
    @classmethod
    def validate_expected_versions(cls, value: dict[int, int]) -> dict[int, int]:
        if not value:
            raise ValueError("expected_balance_versions cannot be empty")
        normalized: dict[int, int] = {}
        for balance_id, version in value.items():
            if balance_id <= 0 or version <= 0:
                raise ValueError("balance ids and versions must be positive")
            normalized[int(balance_id)] = int(version)
        return normalized


class ReservationQuantityLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    reservation_line_id: int = Field(gt=0)
    quantity: Decimal

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: Any) -> Decimal:
        return _exact_quantity(value, positive=True)


class ReturnLine(ReservationQuantityLine):
    issue_transaction_id: int = Field(gt=0)


class IssueCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)
    lines: tuple[ReservationQuantityLine, ...]

    @model_validator(mode="after")
    def require_lines(self) -> IssueCommand:
        if not self.lines:
            raise ValueError("issue requires at least one line")
        return self


class ReleaseCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)
    lines: tuple[ReservationQuantityLine, ...] = ()


class ReturnCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)
    lines: tuple[ReturnLine, ...]

    @model_validator(mode="after")
    def require_lines(self) -> ReturnCommand:
        if not self.lines:
            raise ValueError("return requires at least one line")
        return self


class CancelCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)


class ExpireCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_version: int = Field(gt=0)
    as_of: datetime


class InventoryReservationLineRead(ORMModel):
    id: int
    reservation_id: int
    spare_part_id: int
    balance_id: int
    lot_id: int | None
    serial_item_id: int | None
    requested_quantity: Decimal
    reserved_quantity: Decimal
    issued_quantity: Decimal
    released_quantity: Decimal
    expected_balance_version: int
    fefo_rank: int
    fefo_override_reason: str | None
    version: int


class InventoryReservationRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    tenant_id: str
    owner_type: str
    owner_id: str
    status: str
    expires_at: datetime | None
    allow_partial: bool
    actor_user_id: str
    actor_roles: list[str]
    request_id: str
    version: int
    requested_quantity: Decimal
    reserved_quantity: Decimal
    issued_quantity: Decimal
    released_quantity: Decimal
    unfilled_quantity: Decimal
    line_errors: tuple[str, ...] = ()
    lines: tuple[InventoryReservationLineRead, ...]
