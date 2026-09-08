from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import DemandListStatus
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.demand_list import (
    DemandListConfirmRequest,
    DemandListCreateRequest,
    DemandListItemUpdateRequest,
    DemandListRead,
    DemandListSummaryRead,
    DemandListTransitionRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.demand_list_service import (
    demand_list_service,
)

router = APIRouter(
    prefix="/demand-lists",
    tags=["demand: demand lists"],
)

SessionDep = Annotated[
    Session,
    Depends(get_db_session),
]
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
IdempotencyKeyDep = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
]


@router.post(
    "",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_demand_list(
    payload: DemandListCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.create_from_group(
        session,
        actor,
        calculation_group_id=(
            payload.calculation_group_id
        ),
        name=payload.name,
        description=payload.description,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list created",
        actor=actor,
        version=result.version,
    )


@router.get(
    "",
    response_model=MaintenanceSuccessResponse[
        PageData[DemandListSummaryRead]
    ],
)
def list_demand_lists(
    session: SessionDep,
    actor: ViewerDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: DemandListStatus | None = Query(
        default=None,
        alias="status",
    ),
    lineage_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=36,
    ),
):
    result = demand_list_service.list(
        session,
        actor,
        page=page,
        page_size=page_size,
        status=status_filter,
        lineage_id=lineage_id,
    )
    return success_response(
        result,
        actor=actor,
    )


@router.get(
    "/{demand_list_id}",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def get_demand_list(
    demand_list_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    result = demand_list_service.get(
        session,
        actor,
        demand_list_id,
    )
    return success_response(
        result,
        actor=actor,
        version=result.version,
    )


@router.put(
    "/{demand_list_id}/items/{item_id}",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def update_demand_list_item(
    demand_list_id: int,
    item_id: int,
    payload: DemandListItemUpdateRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    result = demand_list_service.update_item(
        session,
        actor,
        demand_list_id,
        item_id,
        expected_version=payload.expected_version,
        final_quantity=payload.final_quantity,
        adjustment_reason=payload.adjustment_reason,
    )
    return success_response(
        result,
        "Demand list item updated",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/submit",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def submit_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.submit(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list submitted",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/confirm",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def confirm_demand_list(
    demand_list_id: int,
    payload: DemandListConfirmRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.confirm(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        confirmation_note=payload.confirmation_note,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list confirmed",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/publish",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def publish_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.publish(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list published",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/derive",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def derive_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.derive(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list version derived",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/void",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def void_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.void(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list voided",
        actor=actor,
        version=result.version,
    )
