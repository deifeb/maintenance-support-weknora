from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import PageData, SuccessResponse
from app.schemas.inventory import (
    InventoryAdjustment,
    WarehouseInventoryCreate,
    WarehouseInventoryRead,
    WarehouseInventoryUpdate,
)
from app.services import inventory_service

router = APIRouter(prefix="/inventories", tags=["master-data: inventories"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[WarehouseInventoryRead], status_code=status.HTTP_201_CREATED)
def create_inventory(payload: WarehouseInventoryCreate, session: SessionDep):
    item = inventory_service.create_inventory(session, payload)
    return success_response(WarehouseInventoryRead.model_validate(item), "Inventory created")


@router.get("", response_model=SuccessResponse[PageData[WarehouseInventoryRead]])
def list_inventories(
    session: SessionDep,
    params: Annotated[dict, Depends(list_params)],
    warehouse_id: int | None = Query(default=None),
    spare_part_id: int | None = Query(default=None),
):
    filters = {"warehouse_id": warehouse_id, "spare_part_id": spare_part_id}
    return success_response(inventory_service.list(session, **params, filters=filters), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[WarehouseInventoryRead])
def get_inventory(identifier: int, session: SessionDep):
    return success_response(WarehouseInventoryRead.model_validate(inventory_service.get(session, identifier)))


@router.put("/{identifier}", response_model=SuccessResponse[WarehouseInventoryRead])
def update_inventory(identifier: int, payload: WarehouseInventoryUpdate, session: SessionDep):
    return success_response(
        WarehouseInventoryRead.model_validate(inventory_service.update_inventory(session, identifier, payload)),
        "Inventory updated",
    )


@router.post("/{identifier}/adjust", response_model=SuccessResponse[WarehouseInventoryRead])
def adjust_inventory(identifier: int, payload: InventoryAdjustment, session: SessionDep):
    return success_response(
        WarehouseInventoryRead.model_validate(inventory_service.adjust(session, identifier, payload)),
        "Inventory adjusted",
    )
