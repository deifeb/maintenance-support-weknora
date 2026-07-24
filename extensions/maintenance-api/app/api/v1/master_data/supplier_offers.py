from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch
from app.schemas.common import PageData, SuccessResponse
from app.schemas.supplier import SupplierOfferCreate, SupplierOfferRead, SupplierOfferUpdate
from app.services import supplier_offer_service

router = APIRouter(prefix="/supplier-offers", tags=["master-data: supplier offers"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "", response_model=SuccessResponse[SupplierOfferRead], status_code=status.HTTP_201_CREATED
)
def create_offer(payload: SupplierOfferCreate, session: SessionDep):
    item = supplier_offer_service.create_offer(session, payload)
    return success_response(SupplierOfferRead.model_validate(item), "Supplier offer created")


@router.get("", response_model=SuccessResponse[PageData[SupplierOfferRead]])
def list_offers(
    session: SessionDep,
    params: Annotated[dict, Depends(list_params)],
    supplier_id: int | None = Query(default=None),
    spare_part_id: int | None = Query(default=None),
):
    filters = {"supplier_id": supplier_id, "spare_part_id": spare_part_id}
    return success_response(
        supplier_offer_service.list(session, **params, filters=filters), "Query completed"
    )


@router.get("/{identifier}", response_model=SuccessResponse[SupplierOfferRead])
def get_offer(identifier: int, session: SessionDep):
    return success_response(
        SupplierOfferRead.model_validate(supplier_offer_service.get(session, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[SupplierOfferRead])
def update_offer(identifier: int, payload: SupplierOfferUpdate, session: SessionDep):
    return success_response(
        SupplierOfferRead.model_validate(
            supplier_offer_service.update_offer(session, identifier, payload)
        ),
        "Supplier offer updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[SupplierOfferRead])
def set_offer_active(identifier: int, payload: ActivePatch, session: SessionDep):
    return success_response(
        SupplierOfferRead.model_validate(
            supplier_offer_service.set_active(session, identifier, payload.is_active)
        ),
        "Supplier offer status updated",
    )
