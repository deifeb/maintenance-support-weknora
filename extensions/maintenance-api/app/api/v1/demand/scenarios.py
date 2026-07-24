from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.v1.master_data.common import list_params
from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.base import DeleteResult
from app.schemas.common import PageData, SuccessResponse
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
from app.services.scenario_service import scenario_service

router = APIRouter(tags=["demand: scenarios"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/scenarios",
    response_model=SuccessResponse[ScenarioTemplateRead],
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(payload: ScenarioTemplateCreate, session: SessionDep):
    return success_response(
        ScenarioTemplateRead.model_validate(scenario_service.create_template(session, payload)),
        "Scenario created",
    )


@router.get("/scenarios", response_model=SuccessResponse[PageData[ScenarioTemplateRead]])
def list_scenarios(session: SessionDep, params: Annotated[dict, Depends(list_params)]):
    return success_response(scenario_service.list_templates(session, **params), "Query completed")


@router.get("/scenarios/{identifier}", response_model=SuccessResponse[ScenarioTemplateRead])
def get_scenario(identifier: int, session: SessionDep):
    return success_response(
        ScenarioTemplateRead.model_validate(scenario_service.get_template(session, identifier))
    )


@router.put("/scenarios/{identifier}", response_model=SuccessResponse[ScenarioTemplateRead])
def update_scenario(identifier: int, payload: ScenarioTemplateUpdate, session: SessionDep):
    return success_response(
        ScenarioTemplateRead.model_validate(
            scenario_service.update_template(session, identifier, payload)
        )
    )


@router.delete("/scenarios/{identifier}", response_model=SuccessResponse[DeleteResult])
def delete_scenario(identifier: int, session: SessionDep):
    scenario_service.delete_template(session, identifier)
    return success_response(
        DeleteResult(deleted=True, resource="demand_scenario", identifier=identifier)
    )


@router.post(
    "/scenarios/{scenario_id}/versions",
    response_model=SuccessResponse[ScenarioVersionRead],
    status_code=status.HTTP_201_CREATED,
)
def create_version(scenario_id: int, payload: ScenarioVersionCreate, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(
            scenario_service.create_version(session, scenario_id, payload)
        ),
        "Scenario version created",
    )


@router.get("/scenarios/{scenario_id}/versions")
def list_versions(scenario_id: int, session: SessionDep):
    return success_response(
        [
            ScenarioVersionRead.model_validate(row).model_dump(mode="json")
            for row in scenario_service.list_versions(session, scenario_id)
        ]
    )


@router.get("/scenario-versions/{version_id}", response_model=SuccessResponse[ScenarioVersionRead])
def get_version(version_id: int, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(scenario_service.get_version(session, version_id))
    )


@router.put("/scenario-versions/{version_id}", response_model=SuccessResponse[ScenarioVersionRead])
def update_version(version_id: int, payload: ScenarioVersionUpdate, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(
            scenario_service.update_version(session, version_id, payload)
        )
    )


@router.post(
    "/scenario-versions/{version_id}/validate",
    response_model=SuccessResponse[ScenarioValidationResult],
)
def validate_version(version_id: int, session: SessionDep):
    return success_response(scenario_service.validate_version(session, version_id))


@router.post(
    "/scenario-versions/{version_id}/publish", response_model=SuccessResponse[ScenarioVersionRead]
)
def publish_version(version_id: int, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(scenario_service.publish_version(session, version_id)),
        "Scenario published",
    )


@router.post(
    "/scenario-versions/{version_id}/clone", response_model=SuccessResponse[ScenarioVersionRead]
)
def clone_version(version_id: int, payload: ScenarioCloneRequest, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(
            scenario_service.clone_version(
                session, version_id, payload.version_code, payload.version_name
            )
        ),
        "Scenario cloned",
    )


@router.post(
    "/scenario-versions/{version_id}/retire", response_model=SuccessResponse[ScenarioVersionRead]
)
def retire_version(version_id: int, session: SessionDep):
    return success_response(
        ScenarioVersionRead.model_validate(scenario_service.retire_version(session, version_id)),
        "Scenario retired",
    )


@router.get("/scenario-versions/{version_id}/full")
def full_version(version_id: int, session: SessionDep):
    version = scenario_service.get_version(session, version_id, full=True)
    payload = {
        "version": ScenarioVersionRead.model_validate(version).model_dump(mode="json"),
        "stages": [jsonable_encoder(stage) for stage in version.stages],
        "fleet_groups": [jsonable_encoder(group) for group in version.fleet_groups],
        "overrides": [jsonable_encoder(item) for item in version.overrides],
    }
    return success_response(payload)


@router.post("/scenario-versions/{version_id}/stages", status_code=status.HTTP_201_CREATED)
def add_stage(version_id: int, payload: ScenarioStageCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_stage(session, version_id, payload))
    )


@router.post("/scenario-versions/{version_id}/fleet-groups", status_code=status.HTTP_201_CREATED)
def add_fleet_group(version_id: int, payload: FleetGroupCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_fleet_group(session, version_id, payload))
    )


@router.post("/fleet-groups/{group_id}/age-groups", status_code=status.HTTP_201_CREATED)
def add_age_group(group_id: int, payload: AgeGroupCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_age_group(session, group_id, payload))
    )


@router.post("/stages/{stage_id}/fleet-usages", status_code=status.HTTP_201_CREATED)
def add_fleet_usage(stage_id: int, payload: FleetUsageCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_fleet_usage(session, stage_id, payload))
    )


@router.post(
    "/scenario-versions/{version_id}/parameter-overrides", status_code=status.HTTP_201_CREATED
)
def add_override(version_id: int, payload: ParameterOverrideCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_override(session, version_id, payload))
    )


@router.post("/stages/{stage_id}/common-shocks", status_code=status.HTTP_201_CREATED)
def add_shock(stage_id: int, payload: CommonShockCreate, session: SessionDep):
    return success_response(
        jsonable_encoder(scenario_service.add_shock(session, stage_id, payload))
    )
