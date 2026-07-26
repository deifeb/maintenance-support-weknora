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
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services import inventory_service

router = APIRouter(prefix="/inventories", tags=["master-data: inventories"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "", response_model=SuccessResponse[WarehouseInventoryRead], status_code=status.HTTP_201_CREATED
)
def create_inventory(
    payload: WarehouseInventoryCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = inventory_service.create_inventory(session, actor, payload)
    return success_response(WarehouseInventoryRead.model_validate(item), "Inventory created")


@router.get("", response_model=SuccessResponse[PageData[WarehouseInventoryRead]])
def list_inventories(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
    warehouse_id: int | None = Query(default=None),
    spare_part_id: int | None = Query(default=None),
):
    filters = {"warehouse_id": warehouse_id, "spare_part_id": spare_part_id}
    return success_response(
        inventory_service.list(session, actor, **params, filters=filters), "Query completed"
    )


@router.get("/{identifier}", response_model=SuccessResponse[WarehouseInventoryRead])
def get_inventory(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        WarehouseInventoryRead.model_validate(inventory_service.get(session, actor, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[WarehouseInventoryRead])
def update_inventory(
    identifier: int,
    payload: WarehouseInventoryUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        WarehouseInventoryRead.model_validate(
            inventory_service.update_inventory(session, actor, identifier, payload)
        ),
        "Inventory updated",
    )


@router.post("/{identifier}/adjust", response_model=SuccessResponse[WarehouseInventoryRead])
def adjust_inventory(
    identifier: int,
    payload: InventoryAdjustment,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        WarehouseInventoryRead.model_validate(
            inventory_service.adjust(session, actor, identifier, payload)
        ),
        "Inventory adjusted",
    )
