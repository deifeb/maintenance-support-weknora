from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.equipment import EquipmentModelCreate, EquipmentModelRead, EquipmentModelUpdate
from app.services import equipment_service

router = APIRouter(prefix="/equipment-models", tags=["master-data: equipment models"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "", response_model=SuccessResponse[EquipmentModelRead], status_code=status.HTTP_201_CREATED
)
def create_equipment(payload: EquipmentModelCreate, session: SessionDep):
    item = equipment_service.create(session, payload)
    return success_response(EquipmentModelRead.model_validate(item), "Equipment model created")


@router.get("", response_model=SuccessResponse[PageData[EquipmentModelRead]])
def list_equipment(session: SessionDep, params: Annotated[dict, Depends(list_params)]):
    return success_response(equipment_service.list(session, **params), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[EquipmentModelRead])
def get_equipment(identifier: int, session: SessionDep):
    return success_response(
        EquipmentModelRead.model_validate(equipment_service.get(session, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[EquipmentModelRead])
def update_equipment(identifier: int, payload: EquipmentModelUpdate, session: SessionDep):
    item = equipment_service.update(session, identifier, payload)
    return success_response(EquipmentModelRead.model_validate(item), "Equipment model updated")


@router.patch("/{identifier}/active", response_model=SuccessResponse[EquipmentModelRead])
def set_equipment_active(identifier: int, payload: ActivePatch, session: SessionDep):
    item = equipment_service.set_active(session, identifier, payload.is_active)
    return success_response(
        EquipmentModelRead.model_validate(item), "Equipment model status updated"
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_equipment(identifier: int, session: SessionDep):
    equipment_service.delete(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="equipment_model", identifier=identifier)
    )
