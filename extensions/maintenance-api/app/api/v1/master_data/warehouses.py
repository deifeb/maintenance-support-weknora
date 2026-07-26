from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.inventory import WarehouseCreate, WarehouseRead, WarehouseUpdate
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services import warehouse_service

router = APIRouter(prefix="/warehouses", tags=["master-data: warehouses"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[WarehouseRead], status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        WarehouseRead.model_validate(warehouse_service.create(session, actor, payload)),
        "Warehouse created",
    )


@router.get("", response_model=SuccessResponse[PageData[WarehouseRead]])
def list_warehouses(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
):
    return success_response(warehouse_service.list(session, actor, **params), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[WarehouseRead])
def get_warehouse(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        WarehouseRead.model_validate(warehouse_service.get(session, actor, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[WarehouseRead])
def update_warehouse(
    identifier: int,
    payload: WarehouseUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        WarehouseRead.model_validate(warehouse_service.update(session, actor, identifier, payload)),
        "Warehouse updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[WarehouseRead])
def set_warehouse_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        WarehouseRead.model_validate(
            warehouse_service.set_active(session, actor, identifier, payload.is_active)
        ),
        "Warehouse status updated",
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_warehouse(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    warehouse_service.delete(session, actor, identifier)
    return success_response(DeleteResult(deleted=True, resource="warehouse", identifier=identifier))
