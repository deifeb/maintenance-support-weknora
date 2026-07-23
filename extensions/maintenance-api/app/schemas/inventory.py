from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.models.enums import WarehouseStatus
from app.schemas.base import CodeModel, ORMModel, TimestampRead


class WarehouseBase(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    warehouse_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    organization: str | None = Field(default=None, max_length=200)
    responsible_person: str | None = Field(default=None, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    status: WarehouseStatus = WarehouseStatus.NORMAL
    description: str | None = None
    is_active: bool = True


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    warehouse_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    organization: str | None = Field(default=None, max_length=200)
    responsible_person: str | None = Field(default=None, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    status: WarehouseStatus | None = None
    description: str | None = None
    is_active: bool | None = None


class WarehouseRead(WarehouseBase, TimestampRead):
    id: int


class InventoryQuantities(BaseModel):
    on_hand_quantity: Decimal = Field(ge=0)
    reserved_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    damaged_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    quarantined_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    in_transit_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    safety_stock: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_stock: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_quantities(self):
        allocated = self.reserved_quantity + self.damaged_quantity + self.quarantined_quantity
        if allocated > self.on_hand_quantity:
            raise ValueError("reserved + damaged + quarantined cannot exceed on_hand")
        if self.reorder_point < self.safety_stock:
            raise ValueError("reorder_point must be at least safety_stock")
        if self.maximum_stock is not None and self.maximum_stock < self.reorder_point:
            raise ValueError("maximum_stock must be at least reorder_point")
        return self


class WarehouseInventoryCreate(InventoryQuantities):
    warehouse_id: int
    spare_part_id: int
    last_counted_at: datetime | None = None
    notes: str | None = None


class WarehouseInventoryUpdate(BaseModel):
    on_hand_quantity: Decimal | None = Field(default=None, ge=0)
    reserved_quantity: Decimal | None = Field(default=None, ge=0)
    damaged_quantity: Decimal | None = Field(default=None, ge=0)
    quarantined_quantity: Decimal | None = Field(default=None, ge=0)
    in_transit_quantity: Decimal | None = Field(default=None, ge=0)
    safety_stock: Decimal | None = Field(default=None, ge=0)
    reorder_point: Decimal | None = Field(default=None, ge=0)
    maximum_stock: Decimal | None = Field(default=None, ge=0)
    last_counted_at: datetime | None = None
    notes: str | None = None


class InventoryAdjustment(BaseModel):
    on_hand_delta: Decimal = Decimal("0")
    reserved_delta: Decimal = Decimal("0")
    damaged_delta: Decimal = Decimal("0")
    quarantined_delta: Decimal = Decimal("0")
    in_transit_delta: Decimal = Decimal("0")
    reason: str = Field(min_length=1, max_length=500)


class WarehouseInventoryRead(ORMModel):
    id: int
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
    last_counted_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def available_quantity(self) -> Decimal:
        return (
            self.on_hand_quantity
            - self.reserved_quantity
            - self.damaged_quantity
            - self.quarantined_quantity
        )
