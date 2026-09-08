from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_QUANTITY_QUANTUM = Decimal("0.0001")


def _stocktake_quantity(value: Any) -> Decimal:
    if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("quantity must be an exact decimal value")

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
        quantized = decimal_value.quantize(_QUANTITY_QUANTUM)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("quantity must fit Numeric(18,4)") from exc

    if not decimal_value.is_finite() or decimal_value != quantized:
        raise ValueError("quantity must have at most four decimal places")
    if quantized < 0:
        raise ValueError("quantity must be non-negative")
    return quantized


class StocktakeCreateCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    warehouse_id: int = Field(gt=0)
    location_id: int = Field(gt=0)


class StocktakeCountCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)
    expected_line_version: int = Field(gt=0)
    counted_quantity: Decimal

    @field_validator("counted_quantity", mode="before")
    @classmethod
    def validate_counted_quantity(cls, value: Any) -> Decimal:
        return _stocktake_quantity(value)


class InventoryStocktakeLineRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    stocktake_id: int
    balance_id: int
    spare_part_id: int
    lot_id: int | None
    serial_item_id: int | None
    system_quantity: Decimal
    counted_quantity: Decimal | None
    variance_quantity: Decimal | None
    snapshot_balance_version: int
    confirmed_transaction_id: int | None
    resolution: str
    conflict_details: dict[str, Any] | None = None
    version: int


class InventoryStocktakeRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    tenant_id: str
    warehouse_id: int
    location_id: int
    status: str
    snapshot_at: datetime
    actor_user_id: str
    actor_roles: list[str]
    request_id: str
    version: int
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    lines: tuple[InventoryStocktakeLineRead, ...]
