from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["master-data: suppliers"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[SupplierRead], status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        SupplierRead.model_validate(supplier_service.create(session, actor, payload)),
        "Supplier created",
    )


@router.get("", response_model=SuccessResponse[PageData[SupplierRead]])
def list_suppliers(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
):
    return success_response(supplier_service.list(session, actor, **params), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[SupplierRead])
def get_supplier(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        SupplierRead.model_validate(supplier_service.get(session, actor, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[SupplierRead])
def update_supplier(
    identifier: int,
    payload: SupplierUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        SupplierRead.model_validate(supplier_service.update(session, actor, identifier, payload)),
        "Supplier updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[SupplierRead])
def set_supplier_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        SupplierRead.model_validate(
            supplier_service.set_active(session, actor, identifier, payload.is_active)
        ),
        "Supplier status updated",
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_supplier(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    supplier_service.delete(session, actor, identifier)
    return success_response(DeleteResult(deleted=True, resource="supplier", identifier=identifier))
