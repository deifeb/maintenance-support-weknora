from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import ConfigurationStatus
from app.schemas.base import DeleteResult
from app.schemas.common import PageData, SuccessResponse
from app.schemas.equipment import (
    ConfigurationCloneRequest,
    ConfigurationItemCreate,
    ConfigurationItemRead,
    ConfigurationItemUpdate,
    ConfigurationTree,
    ConfigurationVersionCreate,
    ConfigurationVersionRead,
    ConfigurationVersionUpdate,
)
from app.services import configuration_service

router = APIRouter(tags=["master-data: configurations"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/configuration-versions",
    response_model=SuccessResponse[ConfigurationVersionRead],
    status_code=status.HTTP_201_CREATED,
)
def create_version(payload: ConfigurationVersionCreate, session: SessionDep):
    item = configuration_service.create_version(session, payload)
    return success_response(ConfigurationVersionRead.model_validate(item), "Configuration version created")


@router.get(
    "/configuration-versions",
    response_model=SuccessResponse[PageData[ConfigurationVersionRead]],
)
def list_versions(
    session: SessionDep,
    params: Annotated[dict, Depends(list_params)],
    equipment_model_id: int | None = Query(default=None),
    status_filter: ConfigurationStatus | None = Query(default=None, alias="status"),
):
    filters = {
        "equipment_model_id": equipment_model_id,
        "status": status_filter,
    }
    return success_response(
        configuration_service.list(session, **params, filters=filters),
        "Query completed",
    )


@router.get(
    "/configuration-versions/{identifier}",
    response_model=SuccessResponse[ConfigurationVersionRead],
)
def get_version(identifier: int, session: SessionDep):
    return success_response(
        ConfigurationVersionRead.model_validate(configuration_service.get(session, identifier))
    )


@router.put(
    "/configuration-versions/{identifier}",
    response_model=SuccessResponse[ConfigurationVersionRead],
)
def update_version(identifier: int, payload: ConfigurationVersionUpdate, session: SessionDep):
    item = configuration_service.update_version(session, identifier, payload)
    return success_response(ConfigurationVersionRead.model_validate(item), "Configuration version updated")


@router.delete(
    "/configuration-versions/{identifier}",
    response_model=SuccessResponse[DeleteResult],
)
def delete_version(identifier: int, session: SessionDep):
    configuration_service.delete(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="configuration_version", identifier=identifier)
    )


@router.post(
    "/configuration-versions/{identifier}/publish",
    response_model=SuccessResponse[ConfigurationVersionRead],
)
def publish_version(identifier: int, session: SessionDep):
    item = configuration_service.publish(session, identifier)
    return success_response(ConfigurationVersionRead.model_validate(item), "Configuration published")


@router.post(
    "/configuration-versions/{identifier}/retire",
    response_model=SuccessResponse[ConfigurationVersionRead],
)
def retire_version(identifier: int, session: SessionDep):
    item = configuration_service.retire(session, identifier)
    return success_response(ConfigurationVersionRead.model_validate(item), "Configuration retired")


@router.post(
    "/configuration-versions/{identifier}/clone",
    response_model=SuccessResponse[ConfigurationVersionRead],
    status_code=status.HTTP_201_CREATED,
)
def clone_version(identifier: int, payload: ConfigurationCloneRequest, session: SessionDep):
    item = configuration_service.clone(session, identifier, payload)
    return success_response(ConfigurationVersionRead.model_validate(item), "Configuration cloned")


@router.get(
    "/configuration-versions/{identifier}/tree",
    response_model=SuccessResponse[ConfigurationTree],
)
def get_tree(identifier: int, session: SessionDep):
    return success_response(configuration_service.tree(session, identifier), "Configuration tree retrieved")


@router.post(
    "/configuration-items",
    response_model=SuccessResponse[ConfigurationItemRead],
    status_code=status.HTTP_201_CREATED,
)
def create_item(payload: ConfigurationItemCreate, session: SessionDep):
    item = configuration_service.create_item(session, payload)
    return success_response(ConfigurationItemRead.model_validate(item), "Configuration item created")


@router.put(
    "/configuration-items/{identifier}",
    response_model=SuccessResponse[ConfigurationItemRead],
)
def update_item(identifier: int, payload: ConfigurationItemUpdate, session: SessionDep):
    item = configuration_service.update_item(session, identifier, payload)
    return success_response(ConfigurationItemRead.model_validate(item), "Configuration item updated")


@router.delete(
    "/configuration-items/{identifier}",
    response_model=SuccessResponse[DeleteResult],
)
def delete_item(identifier: int, session: SessionDep):
    configuration_service.delete_item(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="configuration_item", identifier=identifier)
    )
