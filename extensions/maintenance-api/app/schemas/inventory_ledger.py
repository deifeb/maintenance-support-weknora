from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.schemas.base import ORMModel


class InventoryBalanceRead(ORMModel):
    id: int
    warehouse_id: int
    location_id: int
    spare_part_id: int
    lot_id: int | None
    serial_item_id: int | None = None
    serial_item_ids: list[int] = Field(default_factory=list)
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    damaged_quantity: Decimal
    quarantined_quantity: Decimal
    in_transit_quantity: Decimal
    version: int

    @computed_field
    @property
    def available_quantity(self) -> Decimal:
        return (
            self.on_hand_quantity
            - self.reserved_quantity
            - self.damaged_quantity
            - self.quarantined_quantity
        )


class InventorySummaryRead(BaseModel):
    warehouse_id: int
    spare_part_id: int
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    damaged_quantity: Decimal
    quarantined_quantity: Decimal
    in_transit_quantity: Decimal
    safety_stock: Decimal
    reorder_point: Decimal
    maximum_stock: Decimal | None

    @computed_field
    @property
    def available_quantity(self) -> Decimal:
        return (
            self.on_hand_quantity
            - self.reserved_quantity
            - self.damaged_quantity
            - self.quarantined_quantity
        )


_QUANTITY_QUANTUM = Decimal("0.0001")
MAX_INVENTORY_QUANTITY = Decimal("99999999999999.9999")


class InventoryQuantityDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    on_hand: Decimal = Decimal("0.0000")
    reserved: Decimal = Decimal("0.0000")
    damaged: Decimal = Decimal("0.0000")
    quarantined: Decimal = Decimal("0.0000")
    in_transit: Decimal = Decimal("0.0000")

    @field_validator("*", mode="before")
    @classmethod
    def validate_numeric_18_4(cls, value: Any) -> Decimal:
        if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, int, str)):
            raise ValueError("quantity must be an exact decimal value")
        try:
            decimal_value = Decimal(value) if not isinstance(value, Decimal) else value
            quantized = decimal_value.quantize(_QUANTITY_QUANTUM)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("quantity must fit Numeric(18,4)") from exc
        if not decimal_value.is_finite() or decimal_value != quantized:
            raise ValueError("quantity must have at most four decimal places")
        if abs(quantized) > MAX_INVENTORY_QUANTITY:
            raise ValueError("quantity must fit Numeric(18,4)")
        return quantized


class InventoryLedgerEntryRead(ORMModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True,
    )

    id: int
    balance_id: int
    spare_part_id: int
    warehouse_id: int
    location_id: int
    lot_id: int | None
    serial_item_id: int | None
    on_hand_delta: Decimal
    reserved_delta: Decimal
    damaged_delta: Decimal
    quarantined_delta: Decimal
    in_transit_delta: Decimal
    state_before_json: dict[str, Any]
    state_after_json: dict[str, Any]
    before_balance_version: int
    resulting_balance_version: int
    created_at: datetime


class InventoryTransactionRead(ORMModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True,
    )

    id: int
    tenant_id: str
    operation_type: str
    status: str
    idempotency_key: str
    request_hash: str
    reason: str
    actor_user_id: str
    actor_roles: list[str] = Field(validation_alias="actor_roles_json")
    request_id: str
    version: int
    completed_at: datetime
    entries: list[InventoryLedgerEntryRead]
