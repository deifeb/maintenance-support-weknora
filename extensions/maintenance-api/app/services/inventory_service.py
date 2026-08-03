from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Warehouse, WarehouseInventory
from app.models.enums import WarehouseStatus
from app.repositories import (
    InventoryRepository,
    SparePartRepository,
    WarehouseRepository,
)
from app.schemas.inventory import (
    InventoryAdjustment,
    InventoryQuantities,
    WarehouseInventoryCreate,
    WarehouseInventoryRead,
    WarehouseInventoryUpdate,
)
from app.security.actor import ActorContext
from app.services.base import CrudService


class InventoryService(CrudService):
    def __init__(self) -> None:
        self.inventory_repository = InventoryRepository()
        self.warehouse_repository = WarehouseRepository()
        self.spare_part_repository = SparePartRepository()
        super().__init__(
            self.inventory_repository,
            resource_name="warehouse_inventory",
            read_schema=WarehouseInventoryRead,
            keyword_fields=(),
        )

    def _warehouse(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> Warehouse:
        warehouse = self.warehouse_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if warehouse is None:
            raise NotFoundError("warehouse", identifier)
        return warehouse

    def _validate_references(
        self,
        session: Session,
        actor: ActorContext,
        warehouse_id: int,
        spare_part_id: int,
    ) -> Warehouse:
        warehouse = self._warehouse(
            session,
            actor,
            warehouse_id,
        )
        if self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            spare_part_id,
        ) is None:
            raise NotFoundError(
                "spare_part",
                spare_part_id,
            )
        return warehouse

    def _validate_state(
        self,
        warehouse: Warehouse,
    ) -> None:
        if (
            warehouse.status != WarehouseStatus.NORMAL
            or not warehouse.is_active
        ):
            raise ConflictError(
                "warehouse is not available for inventory changes"
            )

    def create_inventory(
        self,
        session: Session,
        actor: ActorContext,
        payload: WarehouseInventoryCreate,
        *,
        commit: bool = True,
    ) -> WarehouseInventory:
        warehouse = self._validate_references(
            session,
            actor,
            payload.warehouse_id,
            payload.spare_part_id,
        )
        self._validate_state(warehouse)
        if self.inventory_repository.get_by_business_key(
            session,
            actor.tenant_id,
            payload.warehouse_id,
            payload.spare_part_id,
        ):
            raise ConflictError(
                "inventory already exists for warehouse "
                "and spare part"
            )
        return super().create(
            session,
            actor,
            payload,
            commit=commit,
        )

    def update_inventory(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: WarehouseInventoryUpdate,
    ) -> WarehouseInventory:
        current = self.get(
            session,
            actor,
            identifier,
        )
        warehouse = self._validate_references(
            session,
            actor,
            current.warehouse_id,
            current.spare_part_id,
        )
        self._validate_state(warehouse)
        data = {
            "on_hand_quantity": current.on_hand_quantity,
            "reserved_quantity": current.reserved_quantity,
            "damaged_quantity": current.damaged_quantity,
            "quarantined_quantity": (
                current.quarantined_quantity
            ),
            "in_transit_quantity": current.in_transit_quantity,
            "safety_stock": current.safety_stock,
            "reorder_point": current.reorder_point,
            "maximum_stock": current.maximum_stock,
            **payload.model_dump(exclude_unset=True),
        }
        InventoryQuantities.model_validate(data)
        return super().update(
            session,
            actor,
            identifier,
            payload,
        )

    def adjust(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: InventoryAdjustment,
    ) -> WarehouseInventory:
        current = self.get(
            session,
            actor,
            identifier,
        )
        warehouse = self._validate_references(
            session,
            actor,
            current.warehouse_id,
            current.spare_part_id,
        )
        self._validate_state(warehouse)
        values = InventoryQuantities(
            on_hand_quantity=(
                current.on_hand_quantity
                + payload.on_hand_delta
            ),
            reserved_quantity=(
                current.reserved_quantity
                + payload.reserved_delta
            ),
            damaged_quantity=(
                current.damaged_quantity
                + payload.damaged_delta
            ),
            quarantined_quantity=(
                current.quarantined_quantity
                + payload.quarantined_delta
            ),
            in_transit_quantity=(
                current.in_transit_quantity
                + payload.in_transit_delta
            ),
            safety_stock=current.safety_stock,
            reorder_point=current.reorder_point,
            maximum_stock=current.maximum_stock,
        )
        self.inventory_repository.update(
            session,
            actor.tenant_id,
            current,
            {
                "on_hand_quantity": values.on_hand_quantity,
                "reserved_quantity": (
                    values.reserved_quantity
                ),
                "damaged_quantity": values.damaged_quantity,
                "quarantined_quantity": (
                    values.quarantined_quantity
                ),
                "in_transit_quantity": (
                    values.in_transit_quantity
                ),
                "notes": payload.reason,
            },
        )
        self._commit(session)
        session.refresh(current)
        return current


inventory_service = InventoryService()
