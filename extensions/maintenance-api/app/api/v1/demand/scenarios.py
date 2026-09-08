from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import DeleteResult
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.demand_scenario import (
    AgeGroupCreate,
    CommonShockCreate,
    FleetGroupCreate,
    FleetUsageCreate,
    ParameterOverrideCreate,
    ScenarioCloneRequest,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioTemplateRead,
    ScenarioTemplateUpdate,
    ScenarioValidationResult,
    ScenarioVersionCreate,
    ScenarioVersionRead,
    ScenarioVersionUpdate,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.scenario_service import scenario_service

router = APIRouter(tags=["demand: scenarios"])
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
    "/scenarios",
    response_model=MaintenanceSuccessResponse[
        ScenarioTemplateRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(
    payload: ScenarioTemplateCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = scenario_service.create_template(
        session,
        actor,
        payload,
    )
    return success_response(
        ScenarioTemplateRead.model_validate(row),
        "Scenario created",
        actor=actor,
        version=row.version,
    )


@router.get(
    "/scenarios",
    response_model=MaintenanceSuccessResponse[
        PageData[ScenarioTemplateRead]
    ],
)
def list_scenarios(
    session: SessionDep,
    actor: ViewerDep,
    params: Annotated[dict, Depends(list_params)],
):
    return success_response(
        scenario_service.list_templates(
            session,
            actor,
            **params,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/scenarios/{identifier}",
    response_model=MaintenanceSuccessResponse[
        ScenarioTemplateRead
    ],
)
def get_scenario(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
):
    row = scenario_service.get_template(
        session,
        actor,
        identifier,
    )
    return success_response(
        ScenarioTemplateRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.put(
    "/scenarios/{identifier}",
    response_model=MaintenanceSuccessResponse[
        ScenarioTemplateRead
    ],
)
def update_scenario(
    identifier: int,
    payload: ScenarioTemplateUpdate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = scenario_service.update_template(
        session,
        actor,
        identifier,
        payload,
    )
    return success_response(
        ScenarioTemplateRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.delete(
    "/scenarios/{identifier}",
    response_model=MaintenanceSuccessResponse[
        DeleteResult
    ],
)
def delete_scenario(
    identifier: int,
    session: SessionDep,
    actor: AdminDep,
):
    scenario_service.delete_template(
        session,
        actor,
        identifier,
    )
    return success_response(
        DeleteResult(
            deleted=True,
            resource="demand_scenario",
            identifier=identifier,
        ),
        actor=actor,
    )


@router.post(
    "/scenarios/{scenario_id}/versions",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    scenario_id: int,
    payload: ScenarioVersionCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = scenario_service.create_version(
        session,
        actor,
        scenario_id,
        payload,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        "Scenario version created",
        actor=actor,
        version=row.version,
    )


@router.get("/scenarios/{scenario_id}/versions")
def list_versions(
    scenario_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    return success_response(
        [
            ScenarioVersionRead.model_validate(
                row
            ).model_dump(mode="json")
            for row in scenario_service.list_versions(
                session,
                actor,
                scenario_id,
            )
        ],
        actor=actor,
    )


@router.get(
    "/scenario-versions/{version_id}",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
)
def get_version(
    version_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    row = scenario_service.get_version(
        session,
        actor,
        version_id,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.put(
    "/scenario-versions/{version_id}",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
)
def update_version(
    version_id: int,
    payload: ScenarioVersionUpdate,
    session: SessionDep,
    actor: ContributorDep,
):
    row = scenario_service.update_version(
        session,
        actor,
        version_id,
        payload,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        actor=actor,
        version=row.version,
    )


@router.post(
    "/scenario-versions/{version_id}/validate",
    response_model=MaintenanceSuccessResponse[
        ScenarioValidationResult
    ],
)
def validate_version(
    version_id: int,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        scenario_service.validate_version(
            session,
            actor,
            version_id,
        ),
        actor=actor,
    )


@router.post(
    "/scenario-versions/{version_id}/publish",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
)
def publish_version(
    version_id: int,
    session: SessionDep,
    actor: AdminDep,
):
    row = scenario_service.publish_version(
        session,
        actor,
        version_id,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        "Scenario published",
        actor=actor,
        version=row.version,
    )


@router.post(
    "/scenario-versions/{version_id}/clone",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
)
def clone_version(
    version_id: int,
    payload: ScenarioCloneRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    row = scenario_service.clone_version(
        session,
        actor,
        version_id,
        payload.version_code,
        payload.version_name,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        "Scenario cloned",
        actor=actor,
        version=row.version,
    )


@router.post(
    "/scenario-versions/{version_id}/retire",
    response_model=MaintenanceSuccessResponse[
        ScenarioVersionRead
    ],
)
def retire_version(
    version_id: int,
    session: SessionDep,
    actor: AdminDep,
):
    row = scenario_service.retire_version(
        session,
        actor,
        version_id,
    )
    return success_response(
        ScenarioVersionRead.model_validate(row),
        "Scenario retired",
        actor=actor,
        version=row.version,
    )


@router.get("/scenario-versions/{version_id}/full")
def full_version(
    version_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    version = scenario_service.get_version(
        session,
        actor,
        version_id,
        full=True,
    )
    payload = {
        "version": ScenarioVersionRead.model_validate(
            version
        ).model_dump(mode="json"),
        "stages": [
            jsonable_encoder(stage)
            for stage in version.stages
        ],
        "fleet_groups": [
            jsonable_encoder(group)
            for group in version.fleet_groups
        ],
        "overrides": [
            jsonable_encoder(item)
            for item in version.overrides
        ],
    }
    return success_response(
        payload,
        actor=actor,
        version=version.version,
    )


@router.post(
    "/scenario-versions/{version_id}/stages",
    status_code=status.HTTP_201_CREATED,
)
def add_stage(
    version_id: int,
    payload: ScenarioStageCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_stage(
                session,
                actor,
                version_id,
                payload,
            )
        ),
        actor=actor,
    )


@router.post(
    "/scenario-versions/{version_id}/fleet-groups",
    status_code=status.HTTP_201_CREATED,
)
def add_fleet_group(
    version_id: int,
    payload: FleetGroupCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_fleet_group(
                session,
                actor,
                version_id,
                payload,
            )
        ),
        actor=actor,
    )


@router.post(
    "/fleet-groups/{group_id}/age-groups",
    status_code=status.HTTP_201_CREATED,
)
def add_age_group(
    group_id: int,
    payload: AgeGroupCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_age_group(
                session,
                actor,
                group_id,
                payload,
            )
        ),
        actor=actor,
    )


@router.post(
    "/stages/{stage_id}/fleet-usages",
    status_code=status.HTTP_201_CREATED,
)
def add_fleet_usage(
    stage_id: int,
    payload: FleetUsageCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_fleet_usage(
                session,
                actor,
                stage_id,
                payload,
            )
        ),
        actor=actor,
    )


@router.post(
    "/scenario-versions/{version_id}/parameter-overrides",
    status_code=status.HTTP_201_CREATED,
)
def add_override(
    version_id: int,
    payload: ParameterOverrideCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_override(
                session,
                actor,
                version_id,
                payload,
            )
        ),
        actor=actor,
    )


@router.post(
    "/stages/{stage_id}/common-shocks",
    status_code=status.HTTP_201_CREATED,
)
def add_shock(
    stage_id: int,
    payload: CommonShockCreate,
    session: SessionDep,
    actor: ContributorDep,
):
    return success_response(
        jsonable_encoder(
            scenario_service.add_shock(
                session,
                actor,
                stage_id,
                payload,
            )
        ),
        actor=actor,
    )
