from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch
from app.schemas.common import MaintenanceSuccessResponse, PageData
from app.schemas.supplier import SupplierOfferCreate, SupplierOfferRead, SupplierOfferUpdate
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services import supplier_offer_service

router = APIRouter(prefix="/supplier-offers", tags=["master-data: supplier offers"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "", response_model=MaintenanceSuccessResponse[SupplierOfferRead], status_code=status.HTTP_201_CREATED
)
def create_offer(
    payload: SupplierOfferCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = supplier_offer_service.create_offer(session, actor, payload)
    return success_response(SupplierOfferRead.model_validate(item), "Supplier offer created", actor=actor, version=item.version)


@router.get("", response_model=MaintenanceSuccessResponse[PageData[SupplierOfferRead]])
def list_offers(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
    supplier_id: int | None = Query(default=None),
    spare_part_id: int | None = Query(default=None),
):
    filters = {"supplier_id": supplier_id, "spare_part_id": spare_part_id}
    return success_response(
        supplier_offer_service.list(session, actor, **params, filters=filters), "Query completed",
        actor=actor,
    )


@router.get("/{identifier}", response_model=MaintenanceSuccessResponse[SupplierOfferRead])
def get_offer(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(
        SupplierOfferRead.model_validate(supplier_offer_service.get(session, actor, identifier)),
        actor=actor,
    )


@router.put("/{identifier}", response_model=MaintenanceSuccessResponse[SupplierOfferRead])
def update_offer(
    identifier: int,
    payload: SupplierOfferUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = supplier_offer_service.update_offer(session, actor, identifier, payload)
    return success_response(
        SupplierOfferRead.model_validate(
            item
        ),
        "Supplier offer updated",
        actor=actor,
        version=item.version,
    )


@router.patch("/{identifier}/active", response_model=MaintenanceSuccessResponse[SupplierOfferRead])
def set_offer_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    item = supplier_offer_service.set_active(session, actor, identifier, payload.is_active)
    return success_response(
        SupplierOfferRead.model_validate(
            item
        ),
        "Supplier offer status updated",
        actor=actor,
        version=item.version,
    )
