
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import SparePart, Warehouse
from app.models.enums import WarehouseStatus
from app.repositories import InventoryRepository
from app.schemas.inventory import (
    InventoryAdjustment,
    InventoryQuantities,
    WarehouseInventoryCreate,
    WarehouseInventoryRead,
    WarehouseInventoryUpdate,
)
from app.services.base import CrudService


class InventoryService(CrudService):
    def __init__(self) -> None:
        self.inventory_repository = InventoryRepository()
        super().__init__(
            self.inventory_repository,
            resource_name="warehouse_inventory",
            read_schema=WarehouseInventoryRead,
            keyword_fields=(),
        )

    def _warehouse(self, session: Session, identifier: int) -> Warehouse:
        warehouse = session.get(Warehouse, identifier)
        if warehouse is None:
            raise NotFoundError("warehouse", identifier)
        return warehouse

    def _validate_references(self, session: Session, warehouse_id: int, spare_part_id: int) -> Warehouse:
        warehouse = self._warehouse(session, warehouse_id)
        if session.get(SparePart, spare_part_id) is None:
            raise NotFoundError("spare_part", spare_part_id)
        return warehouse

    def _validate_state(self, warehouse: Warehouse) -> None:
        if warehouse.status != WarehouseStatus.NORMAL or not warehouse.is_active:
            raise ConflictError("warehouse is not available for inventory changes")

    def create_inventory(self, session: Session, payload: WarehouseInventoryCreate, *, commit: bool = True):
        warehouse = self._validate_references(session, payload.warehouse_id, payload.spare_part_id)
        self._validate_state(warehouse)
        if self.inventory_repository.get_by_business_key(session, payload.warehouse_id, payload.spare_part_id):
            raise ConflictError("inventory already exists for warehouse and spare part")
        return super().create(session, payload, commit=commit)

    def update_inventory(self, session: Session, identifier: int, payload: WarehouseInventoryUpdate):
        current = self.get(session, identifier)
        warehouse = self._warehouse(session, current.warehouse_id)
        self._validate_state(warehouse)
        data = {
            "on_hand_quantity": current.on_hand_quantity,
            "reserved_quantity": current.reserved_quantity,
            "damaged_quantity": current.damaged_quantity,
            "quarantined_quantity": current.quarantined_quantity,
            "in_transit_quantity": current.in_transit_quantity,
            "safety_stock": current.safety_stock,
            "reorder_point": current.reorder_point,
            "maximum_stock": current.maximum_stock,
            **payload.model_dump(exclude_unset=True),
        }
        InventoryQuantities.model_validate(data)
        return super().update(session, identifier, payload)

    def adjust(self, session: Session, identifier: int, payload: InventoryAdjustment):
        current = self.get(session, identifier)
        warehouse = self._warehouse(session, current.warehouse_id)
        self._validate_state(warehouse)
        values = InventoryQuantities(
            on_hand_quantity=current.on_hand_quantity + payload.on_hand_delta,
            reserved_quantity=current.reserved_quantity + payload.reserved_delta,
            damaged_quantity=current.damaged_quantity + payload.damaged_delta,
            quarantined_quantity=current.quarantined_quantity + payload.quarantined_delta,
            in_transit_quantity=current.in_transit_quantity + payload.in_transit_delta,
            safety_stock=current.safety_stock,
            reorder_point=current.reorder_point,
            maximum_stock=current.maximum_stock,
        )
        current.on_hand_quantity = values.on_hand_quantity
        current.reserved_quantity = values.reserved_quantity
        current.damaged_quantity = values.damaged_quantity
        current.quarantined_quantity = values.quarantined_quantity
        current.in_transit_quantity = values.in_transit_quantity
        current.notes = payload.reason
        self._commit(session)
        session.refresh(current)
        return current


inventory_service = InventoryService()
