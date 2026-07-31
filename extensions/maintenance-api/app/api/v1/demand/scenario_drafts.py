from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.scenario_draft import (
    ScenarioDraftCreateRequest,
    ScenarioDraftEnvelope,
    ScenarioDraftSaveRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.scenario_draft_service import (
    scenario_draft_service,
)

router = APIRouter(tags=["demand: scenario drafts"])
SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]


@router.post(
    "/scenario-drafts",
    response_model=MaintenanceSuccessResponse[
        ScenarioDraftEnvelope
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_draft(
    payload: ScenarioDraftCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    envelope = scenario_draft_service.create(
        session,
        actor,
        title=payload.title,
        sensitivity_level=payload.sensitivity_level,
    )
    return success_response(
        envelope,
        "Scenario draft created",
        actor=actor,
        version=envelope.version,
    )


@router.get(
    "/scenario-drafts/{session_id}",
    response_model=MaintenanceSuccessResponse[
        ScenarioDraftEnvelope
    ],
)
def get_draft(
    session_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    envelope = scenario_draft_service.get(
        session,
        actor,
        session_id,
    )
    return success_response(
        envelope,
        actor=actor,
        version=envelope.version,
    )


@router.put(
    "/scenario-drafts/{session_id}",
    response_model=MaintenanceSuccessResponse[
        ScenarioDraftEnvelope
    ],
)
def save_draft(
    session_id: int,
    payload: ScenarioDraftSaveRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    envelope = scenario_draft_service.save(
        session,
        actor,
        session_id,
        expected_version=payload.expected_version,
        draft=payload.draft,
    )
    return success_response(
        envelope,
        "Scenario draft saved",
        actor=actor,
        version=envelope.version,
    )


@router.post(
    "/scenario-drafts/{session_id}/validate",
    response_model=MaintenanceSuccessResponse[
        ScenarioDraftEnvelope
    ],
)
def validate_draft(
    session_id: int,
    session: SessionDep,
    actor: ContributorDep,
):
    envelope = scenario_draft_service.validate(
        session,
        actor,
        session_id,
    )
    return success_response(
        envelope,
        "Scenario draft validated",
        actor=actor,
        version=envelope.version,
    )
