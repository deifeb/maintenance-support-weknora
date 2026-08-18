from __future__ import annotations

from typing import Annotated, Literal

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
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.demand_review import (
    DemandReviewBatchDecisionRequest,
    DemandReviewDecisionRequest,
    DemandReviewDecisionStatus,
    DemandReviewPublicRead,
    DemandReviewRunRequest,
    DemandReviewStatus,
    DemandReviewSummaryRead,
    DemandReviewTransitionRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.demand_review_service import DemandReviewService

router = APIRouter(
    prefix="/demand-lists",
    tags=["reviews: demand lists"],
)

SessionDep = Annotated[
    Session,
    Depends(get_db_session),
]

ViewerDep: object
ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep: object
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep: object
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

demand_review_service = DemandReviewService()


@router.get(
    "",
    response_model=MaintenanceSuccessResponse[
        PageData[DemandReviewSummaryRead]
    ],
)
def list_demand_list_reviews(
    session: SessionDep,
    actor: ViewerDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: DemandReviewStatus | None = Query(
        default=None,
        alias="status",
    ),
    source_demand_list_id: int | None = Query(
        default=None,
        gt=0,
    ),
    sort_by: Literal[
        "id",
        "status",
        "created_at",
        "updated_at",
    ] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
):
    result = demand_review_service.list(
        session,
        actor,
        page=page,
        page_size=page_size,
        status=status_filter,
        source_demand_list_id=source_demand_list_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_response(
        result,
        actor=actor,
    )


@router.post(
    "/{demand_list_id}/run",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def run_demand_list_review(
    demand_list_id: int,
    payload: DemandReviewRunRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_review_service.run_public(
        session,
        actor,
        demand_list_id,
        expected_source_version=payload.expected_source_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand review completed",
        actor=actor,
        version=result.version,
    )


@router.get(
    "/{review_id}",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
)
def get_demand_list_review(
    review_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    result = demand_review_service.get(
        session,
        actor,
        review_id,
    )
    return success_response(
        result,
        actor=actor,
        version=result.version,
    )


@router.put(
    "/{review_id}/findings/{finding_id}/decision",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
)
def decide_demand_review_finding(
    review_id: int,
    finding_id: int,
    payload: DemandReviewDecisionRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_review_service.decide_finding_public(
        session,
        actor,
        review_id,
        finding_id,
        expected_review_version=payload.expected_review_version,
        expected_finding_version=payload.expected_finding_version,
        action=DemandReviewDecisionStatus(payload.action),
        final_quantity=payload.final_quantity,
        reason=payload.reason,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand review finding decided",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{review_id}/batch-decisions",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
)
def batch_decide_demand_review_findings(
    review_id: int,
    payload: DemandReviewBatchDecisionRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_review_service.batch_decide_public(
        session,
        actor,
        review_id,
        expected_review_version=payload.expected_review_version,
        commands=payload.decisions,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand review findings decided",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{review_id}/derive",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
)
def derive_demand_list_from_review(
    review_id: int,
    payload: DemandReviewTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_review_service.derive_public(
        session,
        actor,
        review_id,
        expected_review_version=payload.expected_review_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list draft derived from review",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{review_id}/void",
    response_model=MaintenanceSuccessResponse[
        DemandReviewPublicRead
    ],
)
def void_demand_list_review(
    review_id: int,
    payload: DemandReviewTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_review_service.void_public(
        session,
        actor,
        review_id,
        expected_review_version=payload.expected_review_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand review voided",
        actor=actor,
        version=result.version,
    )
