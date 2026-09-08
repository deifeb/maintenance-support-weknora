from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import DataSourceType
from app.schemas.base import ActivePatch, DeleteResult
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.repair import (
    RepairProfileCreate,
    RepairProfileRead,
    RepairProfileUpdate,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.repair_service import repair_service

router = APIRouter(
    prefix="/repair-profiles",
    tags=["demand: repair profiles"],
)
SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep = Annotated[
    ActorContext,
    Depends(require_admin),
]


@router.post(
    "",
    response_model=MaintenanceSuccessResponse[
        RepairProfileRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: RepairProfileCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = repair_service.create_profile(
        session,
        actor,
        payload,
    )
    return success_response(
        RepairProfileRead.model_validate(row),
        "Repair profile created",
        actor=actor,
        version=row.version,
    )


@router.get(
    "",
    response_model=MaintenanceSuccessResponse[
        PageData[RepairProfileRead]
    ],
)
def list_profiles(
    session: SessionDep,
    actor: ViewerDep,
    params: Annotated[dict, Depends(list_params)],
    spare_part_id: int | None = Query(default=None),
    configuration_version_id: int | None = Query(
        default=None
    ),
    maintenance_level: str | None = Query(default=None),
    data_source_type: DataSourceType | None = Query(
        default=None
    ),
):
    filters = {
        "spare_part_id": spare_part_id,
        "configuration_version_id": (
            configuration_version_id
        ),
        "maintenance_level": maintenance_level,
        "data_source_type": data_source_type,
    }
    return success_response(
        repair_service.list(
            session,
            actor,
            **params,
            filters=filters,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/{identifier}",
    response_model=MaintenanceSuccessResponse[
        RepairProfileRead
    ],
)
def get_profile(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
):
    row = repair_service.get(
        session,
        actor,
        identifier,
    )
    return success_response(
        RepairProfileRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.put(
    "/{identifier}",
    response_model=MaintenanceSuccessResponse[
        RepairProfileRead
    ],
)
def update_profile(
    identifier: int,
    payload: RepairProfileUpdate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = repair_service.update_profile(
        session,
        actor,
        identifier,
        payload,
    )
    return success_response(
        RepairProfileRead.model_validate(row),
        "Repair profile updated",
        actor=actor,
        version=row.version,
    )


@router.patch(
    "/{identifier}/active",
    response_model=MaintenanceSuccessResponse[
        RepairProfileRead
    ],
)
def set_active(
    identifier: int,
    payload: ActivePatch,
    session: SessionDep,
    actor: ContributorDep,
):
    row = repair_service.set_active(
        session,
        actor,
        identifier,
        payload.is_active,
    )
    return success_response(
        RepairProfileRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.delete(
    "/{identifier}",
    response_model=MaintenanceSuccessResponse[
        DeleteResult
    ],
)
def delete_profile(
    identifier: int,
    session: SessionDep,
    actor: AdminDep,
):
    repair_service.delete(
        session,
        actor,
        identifier,
    )
    return success_response(
        DeleteResult(
            deleted=True,
            resource="repair_profile",
            identifier=identifier,
        ),
        actor=actor,
    )
