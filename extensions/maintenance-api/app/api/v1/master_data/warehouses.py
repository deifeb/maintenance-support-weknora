from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import MaintenanceSuccessResponse, PageData
from app.schemas.inventory import WarehouseCreate, WarehouseRead, WarehouseUpdate
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services import warehouse_service

router = APIRouter(prefix="/warehouses", tags=["master-data: warehouses"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=MaintenanceSuccessResponse[WarehouseRead], status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = warehouse_service.create(session, actor, payload)
    return success_response(
        WarehouseRead.model_validate(item),
        "Warehouse created",
        actor=actor,
        version=item.version,
    )


@router.get("", response_model=MaintenanceSuccessResponse[PageData[WarehouseRead]])
def list_warehouses(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
):
    return success_response(warehouse_service.list(session, actor, **params), "Query completed", actor=actor)


@router.get("/{identifier}", response_model=MaintenanceSuccessResponse[WarehouseRead])
def get_warehouse(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        WarehouseRead.model_validate(warehouse_service.get(session, actor, identifier)),
        actor=actor,
    )


@router.put("/{identifier}", response_model=MaintenanceSuccessResponse[WarehouseRead])
def update_warehouse(
    identifier: int,
    payload: WarehouseUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = warehouse_service.update(session, actor, identifier, payload)
    return success_response(
        WarehouseRead.model_validate(item),
        "Warehouse updated",
        actor=actor,
        version=item.version,
    )


@router.patch("/{identifier}/active", response_model=MaintenanceSuccessResponse[WarehouseRead])
def set_warehouse_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = warehouse_service.set_active(session, actor, identifier, payload.is_active)
    return success_response(
        WarehouseRead.model_validate(
            item
        ),
        "Warehouse status updated",
        actor=actor,
        version=item.version,
    )


@router.delete("/{identifier}", response_model=MaintenanceSuccessResponse[DeleteResult])
def delete_warehouse(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_admin)],
):
    warehouse_service.delete(session, actor, identifier)
    return success_response(DeleteResult(deleted=True, resource="warehouse", identifier=identifier), actor=actor)
