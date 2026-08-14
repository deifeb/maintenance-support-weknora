from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.inventory_ledger import MAX_INVENTORY_QUANTITY

_QUANTITY_QUANTUM = Decimal("0.0001")


def _exact_positive_quantity(value: Any) -> Decimal:
    if isinstance(value, (bool, float)) or not isinstance(
        value,
        (Decimal, int, str),
    ):
        raise ValueError("quantity must be an exact decimal value")

    try:
        decimal_value = (
            value if isinstance(value, Decimal) else Decimal(value)
        )
        quantized = decimal_value.quantize(_QUANTITY_QUANTUM)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("quantity must fit Numeric(18,4)") from exc

    if not decimal_value.is_finite() or decimal_value != quantized:
        raise ValueError(
            "quantity must have at most four decimal places"
        )

    if quantized <= Decimal("0.0000"):
        raise ValueError("quantity must be greater than zero")

    if quantized > MAX_INVENTORY_QUANTITY:
        raise ValueError("quantity must fit Numeric(18,4)")

    return quantized


class TransferCreateLineCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    spare_part_id: int = Field(gt=0)
    source_balance_id: int = Field(gt=0)
    lot_id: int | None = Field(default=None, gt=0)
    serial_item_id: int | None = Field(default=None, gt=0)
    quantity: Decimal
    expected_source_version: int = Field(gt=0)

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: Any) -> Decimal:
        return _exact_positive_quantity(value)


class TransferCreateCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_warehouse_id: int = Field(gt=0)
    source_location_id: int = Field(gt=0)
    target_warehouse_id: int = Field(gt=0)
    target_location_id: int = Field(gt=0)

    reference_type: str | None = Field(
        default=None,
        max_length=64,
    )
    reference_id: str | None = Field(
        default=None,
        max_length=128,
    )
    reason: str = Field(min_length=1, max_length=500)

    lines: tuple[TransferCreateLineCommand, ...]

    @field_validator(
        "reference_type",
        "reference_id",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_transfer(self) -> TransferCreateCommand:
        if not self.lines:
            raise ValueError(
                "transfer requires at least one line"
            )

        if (
            self.source_location_id
            == self.target_location_id
        ):
            raise ValueError(
                "source and target locations must differ"
            )

        return self


class TransferLineRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    transfer_id: int
    spare_part_id: int

    source_balance_id: int
    target_balance_id: int

    lot_id: int | None
    serial_item_id: int | None

    requested_quantity: Decimal
    dispatched_quantity: Decimal
    received_quantity: Decimal

    expected_source_version: int
    expected_target_version: int
    version: int


class TransferRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    tenant_id: str
    status: str

    source_warehouse_id: int
    source_location_id: int
    target_warehouse_id: int
    target_location_id: int

    reference_type: str | None
    reference_id: str | None
    reason: str

    actor_user_id: str
    actor_roles: list[str]
    request_id: str

    version: int

    dispatched_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None

    lines: tuple[TransferLineRead, ...]
