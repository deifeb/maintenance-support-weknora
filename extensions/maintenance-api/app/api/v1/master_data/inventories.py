from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import MaintenanceSuccessResponse, PageData
from app.schemas.inventory import (
    InventoryAdjustment,
    InventoryAdjustmentRead,
    WarehouseInventoryCreate,
    WarehouseInventoryRead,
    WarehouseInventoryUpdate,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services import inventory_service

router = APIRouter(prefix="/inventories", tags=["master-data: inventories"])
SessionDep = Annotated[Session, Depends(get_db_session)]
AdminDep = Annotated[ActorContext, Depends(require_admin)]


@router.post(
    "", response_model=MaintenanceSuccessResponse[WarehouseInventoryRead], status_code=status.HTTP_201_CREATED
)
def create_inventory(
    payload: WarehouseInventoryCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = inventory_service.create_inventory(session, actor, payload)
    return success_response(WarehouseInventoryRead.model_validate(item), "Inventory created", actor=actor, version=item.version)


@router.get("", response_model=MaintenanceSuccessResponse[PageData[WarehouseInventoryRead]])
def list_inventories(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
    warehouse_id: int | None = Query(default=None),
    spare_part_id: int | None = Query(default=None),
):
    filters = {"warehouse_id": warehouse_id, "spare_part_id": spare_part_id}
    return success_response(
        inventory_service.list(session, actor, **params, filters=filters), "Query completed",
        actor=actor,
    )


@router.get("/{identifier}", response_model=MaintenanceSuccessResponse[WarehouseInventoryRead])
def get_inventory(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        WarehouseInventoryRead.model_validate(inventory_service.get(session, actor, identifier)),
        actor=actor,
    )


@router.put("/{identifier}", response_model=MaintenanceSuccessResponse[WarehouseInventoryRead])
def update_inventory(
    identifier: int,
    payload: WarehouseInventoryUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = inventory_service.update_inventory(session, actor, identifier, payload)
    return success_response(
        WarehouseInventoryRead.model_validate(
            item
        ),
        "Inventory updated",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/{identifier}/adjust",
    response_model=MaintenanceSuccessResponse[InventoryAdjustmentRead],
)
def adjust_inventory(
    identifier: int,
    payload: InventoryAdjustment,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ],
):
    item = inventory_service.adjust(
        session,
        actor,
        identifier,
        payload,
        idempotency_key=idempotency_key,
    )
    return success_response(
        item,
        "Inventory adjusted",
        actor=actor,
        version=item.summary.version,
    )
