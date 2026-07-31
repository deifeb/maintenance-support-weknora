from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models import CalculationGroup
from app.models.enums import CalculationGroupStatus
from app.schemas.calculation_group import (
    CalculationGroupCreateRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.calculation_group_service import (
    calculation_group_service,
)

router = APIRouter(
    prefix="/calculation-groups",
    tags=["demand: calculation groups"],
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


def _group_dict(group: CalculationGroup) -> dict[str, object]:
    return {
        "id": group.id,
        "scenario_version_id": group.scenario_version_id,
        "status": group.status.value,
        "primary_candidate_key": (
            group.primary_candidate_key
        ),
        "recommendation_snapshot": (
            group.recommendation_snapshot_json
        ),
        "parameter_snapshot": group.parameter_snapshot_json,
        "last_event_sequence": group.last_event_sequence,
        "version": group.version,
        "created_by_user_id": group.created_by_user_id,
        "created_by_request_id": (
            group.created_by_request_id
        ),
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "current_children": [
            {
                "id": child.id,
                "candidate_key": child.candidate_key,
                "reliability_model": (
                    child.reliability_model.value
                ),
                "execution_mode": child.execution_mode.value,
                "calculation_id": child.calculation_id,
                "calculation_status": (
                    child.calculation.status.value
                ),
                "progress_percent": (
                    child.calculation.progress_percent
                ),
                "attempt_number": child.attempt_number,
                "is_primary": child.is_primary,
                "selection_reason": child.selection_reason,
            }
            for child in group.current_children
        ],
    }


@router.post("", status_code=201)
def create_group(
    payload: CalculationGroupCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ],
):
    group = calculation_group_service.create(
        session,
        actor,
        scenario_version_id=payload.scenario_version_id,
        primary_candidate_key=(
            payload.primary_candidate_key
        ),
        selected_candidate_keys=(
            payload.selected_candidate_keys
        ),
        random_seed=payload.random_seed,
        idempotency_key=idempotency_key,
    )
    return success_response(
        _group_dict(group),
        "Calculation group created",
        actor=actor,
        version=group.version,
    )


@router.get("")
def list_groups(
    session: SessionDep,
    actor: ViewerDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: CalculationGroupStatus | None = None,
):
    return success_response(
        calculation_group_service.list(
            session,
            actor,
            page=page,
            page_size=page_size,
            status=status,
        ),
        actor=actor,
    )


@router.get("/{group_id}")
def get_group(
    group_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    group = calculation_group_service.get(
        session,
        actor,
        group_id,
    )
    return success_response(
        _group_dict(group),
        actor=actor,
        version=group.version,
    )
