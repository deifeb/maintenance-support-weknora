from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

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
