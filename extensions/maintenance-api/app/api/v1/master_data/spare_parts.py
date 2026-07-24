from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.catalog import SparePartCreate, SparePartRead, SparePartUpdate
from app.schemas.common import PageData, SuccessResponse
from app.services import spare_part_service

router = APIRouter(prefix="/spare-parts", tags=["master-data: spare parts"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[SparePartRead], status_code=status.HTTP_201_CREATED)
def create_spare_part(payload: SparePartCreate, session: SessionDep):
    return success_response(
        SparePartRead.model_validate(spare_part_service.create(session, payload)),
        "Spare part created",
    )


@router.get("", response_model=SuccessResponse[PageData[SparePartRead]])
def list_spare_parts(session: SessionDep, params: Annotated[dict, Depends(list_params)]):
    return success_response(spare_part_service.list(session, **params), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[SparePartRead])
def get_spare_part(identifier: int, session: SessionDep):
    return success_response(
        SparePartRead.model_validate(spare_part_service.get(session, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[SparePartRead])
def update_spare_part(identifier: int, payload: SparePartUpdate, session: SessionDep):
    return success_response(
        SparePartRead.model_validate(spare_part_service.update(session, identifier, payload)),
        "Spare part updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[SparePartRead])
def set_spare_part_active(identifier: int, payload: ActivePatch, session: SessionDep):
    return success_response(
        SparePartRead.model_validate(
            spare_part_service.set_active(session, identifier, payload.is_active)
        ),
        "Spare part status updated",
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_spare_part(identifier: int, session: SessionDep):
    spare_part_service.delete(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="spare_part", identifier=identifier)
    )
