from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import ReliabilityModelType
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.reliability import (
    ReliabilityProfileCreate,
    ReliabilityProfileRead,
    ReliabilityProfileUpdate,
)
from app.services import reliability_service

router = APIRouter(prefix="/reliability-profiles", tags=["master-data: reliability"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[ReliabilityProfileRead], status_code=status.HTTP_201_CREATED)
def create_profile(payload: ReliabilityProfileCreate, session: SessionDep):
    item = reliability_service.create_profile(session, payload)
    return success_response(ReliabilityProfileRead.model_validate(item), "Reliability profile created")


@router.get("", response_model=SuccessResponse[PageData[ReliabilityProfileRead]])
def list_profiles(
    session: SessionDep,
    params: Annotated[dict, Depends(list_params)],
    spare_part_id: int | None = Query(default=None),
    configuration_version_id: int | None = Query(default=None),
    model_type: ReliabilityModelType | None = Query(default=None),
):
    filters = {
        "spare_part_id": spare_part_id,
        "configuration_version_id": configuration_version_id,
        "model_type": model_type,
    }
    return success_response(reliability_service.list(session, **params, filters=filters), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[ReliabilityProfileRead])
def get_profile(identifier: int, session: SessionDep):
    return success_response(ReliabilityProfileRead.model_validate(reliability_service.get(session, identifier)))


@router.put("/{identifier}", response_model=SuccessResponse[ReliabilityProfileRead])
def update_profile(identifier: int, payload: ReliabilityProfileUpdate, session: SessionDep):
    return success_response(
        ReliabilityProfileRead.model_validate(reliability_service.update_profile(session, identifier, payload)),
        "Reliability profile updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[ReliabilityProfileRead])
def set_profile_active(identifier: int, payload: ActivePatch, session: SessionDep):
    return success_response(
        ReliabilityProfileRead.model_validate(
            reliability_service.set_active(session, identifier, payload.is_active)
        ),
        "Reliability profile status updated",
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_profile(identifier: int, session: SessionDep):
    reliability_service.delete(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="reliability_profile", identifier=identifier)
    )
