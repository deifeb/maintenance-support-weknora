from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import DataSourceType
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.repair import RepairProfileCreate, RepairProfileRead, RepairProfileUpdate
from app.services.repair_service import repair_service

router = APIRouter(prefix="/repair-profiles", tags=["demand: repair profiles"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "", response_model=SuccessResponse[RepairProfileRead], status_code=status.HTTP_201_CREATED
)
def create_profile(payload: RepairProfileCreate, session: SessionDep):
    return success_response(
        RepairProfileRead.model_validate(repair_service.create_profile(session, payload)),
        "Repair profile created",
    )


@router.get("", response_model=SuccessResponse[PageData[RepairProfileRead]])
def list_profiles(
    session: SessionDep,
    params: Annotated[dict, Depends(list_params)],
    spare_part_id: int | None = Query(default=None),
    configuration_version_id: int | None = Query(default=None),
    maintenance_level: str | None = Query(default=None),
    data_source_type: DataSourceType | None = Query(default=None),
):
    filters = {
        "spare_part_id": spare_part_id,
        "configuration_version_id": configuration_version_id,
        "maintenance_level": maintenance_level,
        "data_source_type": data_source_type,
    }
    return success_response(
        repair_service.list(session, **params, filters=filters), "Query completed"
    )


@router.get("/{identifier}", response_model=SuccessResponse[RepairProfileRead])
def get_profile(identifier: int, session: SessionDep):
    return success_response(
        RepairProfileRead.model_validate(repair_service.get(session, identifier))
    )


@router.put("/{identifier}", response_model=SuccessResponse[RepairProfileRead])
def update_profile(identifier: int, payload: RepairProfileUpdate, session: SessionDep):
    return success_response(
        RepairProfileRead.model_validate(
            repair_service.update_profile(session, identifier, payload)
        ),
        "Repair profile updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[RepairProfileRead])
def set_active(identifier: int, payload: ActivePatch, session: SessionDep):
    return success_response(
        RepairProfileRead.model_validate(
            repair_service.set_active(session, identifier, payload.is_active)
        )
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_profile(identifier: int, session: SessionDep):
    repair_service.delete(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="repair_profile", identifier=identifier)
    )
