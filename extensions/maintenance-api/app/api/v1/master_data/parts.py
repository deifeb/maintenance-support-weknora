from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.catalog import PartCreate, PartRead, PartUpdate
from app.schemas.common import PageData, SuccessResponse
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services import part_service

router = APIRouter(prefix="/parts", tags=["master-data: parts"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=SuccessResponse[PartRead], status_code=status.HTTP_201_CREATED)
def create_part(
    payload: PartCreate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        PartRead.model_validate(part_service.create(session, actor, payload)), "Part created"
    )


@router.get("", response_model=SuccessResponse[PageData[PartRead]])
def list_parts(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
    params: Annotated[dict, Depends(list_params)],
):
    return success_response(part_service.list(session, actor, **params), "Query completed")


@router.get("/{identifier}", response_model=SuccessResponse[PartRead])
def get_part(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_viewer)],
):
    return success_response(PartRead.model_validate(part_service.get(session, actor, identifier)))


@router.put("/{identifier}", response_model=SuccessResponse[PartRead])
def update_part(
    identifier: int,
    payload: PartUpdate,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        PartRead.model_validate(part_service.update(session, actor, identifier, payload)),
        "Part updated",
    )


@router.patch("/{identifier}/active", response_model=SuccessResponse[PartRead])
def set_part_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    return success_response(
        PartRead.model_validate(
            part_service.set_active(session, actor, identifier, payload.is_active)
        ),
        "Part status updated",
    )


@router.delete("/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_part(
    identifier: int,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
):
    part_service.delete(session, actor, identifier)
    return success_response(DeleteResult(deleted=True, resource="part", identifier=identifier))
