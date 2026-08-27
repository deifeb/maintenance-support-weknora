from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.allocations.common import (
    IdempotencyKeyDep,
    PlanListQueryGuardDep,
    SessionDep,
    TenantGuardDep,
)
from app.core.responses import success_response
from app.schemas.allocation import (
    AllocationPlanActionResult,
    AllocationPlanConfirmCommand,
    AllocationPlanCreateCommand,
    AllocationPlanExecuteCommand,
    AllocationPlanExecutionResult,
    AllocationPlanLineEditCommand,
    AllocationPlanLineRead,
    AllocationPlanPreviewCommand,
    AllocationPlanRead,
    AllocationPlanRegenerateCommand,
    AllocationPlanRegenerationResult,
    AllocationPlanSummaryRead,
    AllocationPlanVoidCommand,
)
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.allocation_plan_service import (
    allocation_plan_service,
)

# PLAN05_4D_TASK6_GREEN_D: thin plan transaction adapters.
router = APIRouter(tags=["allocations: plans"])

ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]


def _page_data(
    items: list[AllocationPlanSummaryRead],
    *,
    page: int,
    page_size: int,
    total: int,
) -> PageData[AllocationPlanSummaryRead]:
    pages = (total + page_size - 1) // page_size
    return PageData(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get(
    "/plans",
    response_model=MaintenanceSuccessResponse[
        PageData[AllocationPlanSummaryRead]
    ],
)
def list_plans(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: PlanListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    source_demand_list_id: int | None = Query(
        default=None,
        gt=0,
    ),
    rule_id: int | None = Query(default=None, gt=0),
):
    items, total = allocation_plan_service.list_read(
        session,
        actor,
        page=page,
        page_size=page_size,
        status=status,
        source_demand_list_id=source_demand_list_id,
        rule_id=rule_id,
    )
    return success_response(
        _page_data(
            items,
            page=page,
            page_size=page_size,
            total=total,
        ),
        "Allocation plans queried",
        actor=actor,
    )


@router.post(
    "/plans",
    response_model=MaintenanceSuccessResponse[AllocationPlanRead],
)
def create_plan(
    payload: AllocationPlanCreateCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    plan = allocation_plan_service.create(
        session,
        actor,
        payload.source_demand_list_id,
        idempotency_key=idempotency_key,
        expected_source_version=payload.expected_source_version,
    )
    result = allocation_plan_service.get_read(
        session,
        actor,
        plan.id,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan created",
        actor=actor,
        version=result.version,
    )


@router.get(
    "/plans/{plan_id}",
    response_model=MaintenanceSuccessResponse[AllocationPlanRead],
)
def get_plan(
    plan_id: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    result = allocation_plan_service.get_read(
        session,
        actor,
        plan_id,
    )
    return success_response(
        result,
        "Allocation plan queried",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/plans/{plan_id}/preview",
    response_model=MaintenanceSuccessResponse[AllocationPlanRead],
)
def preview_plan(
    plan_id: int,
    payload: AllocationPlanPreviewCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
):
    allocation_plan_service.preview(
        session,
        actor,
        plan_id,
        command=payload,
    )
    result = allocation_plan_service.get_read(
        session,
        actor,
        plan_id,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan previewed",
        actor=actor,
        version=result.version,
    )


@router.put(
    "/plans/{plan_id}/lines/{line_id}",
    response_model=MaintenanceSuccessResponse[
        AllocationPlanLineRead
    ],
)
def edit_plan_line(
    plan_id: int,
    line_id: int,
    payload: AllocationPlanLineEditCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
):
    allocation_plan_service.edit_line(
        session,
        actor,
        plan_id,
        line_id,
        command=payload,
    )
    plan = allocation_plan_service.get_read(
        session,
        actor,
        plan_id,
    )
    result = next(
        item
        for item in plan.lines
        if item.id == line_id
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan line updated",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/plans/{plan_id}/confirm",
    response_model=MaintenanceSuccessResponse[
        AllocationPlanActionResult
    ],
)
def confirm_plan(
    plan_id: int,
    payload: AllocationPlanConfirmCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = allocation_plan_service.confirm(
        session,
        actor,
        plan_id,
        command=payload,
        idempotency_key=idempotency_key,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan confirmed",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/plans/{plan_id}/execute",
    response_model=MaintenanceSuccessResponse[
        AllocationPlanExecutionResult
    ],
)
def execute_plan(
    plan_id: int,
    payload: AllocationPlanExecuteCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = allocation_plan_service.execute(
        session,
        actor,
        plan_id,
        command=payload,
        idempotency_key=idempotency_key,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan executed",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/plans/{plan_id}/void",
    response_model=MaintenanceSuccessResponse[
        AllocationPlanActionResult
    ],
)
def void_plan(
    plan_id: int,
    payload: AllocationPlanVoidCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
):
    result = allocation_plan_service.void(
        session,
        actor,
        plan_id,
        command=payload,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan voided",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/plans/{plan_id}/regenerate",
    response_model=MaintenanceSuccessResponse[
        AllocationPlanRegenerationResult
    ],
)
def regenerate_plan(
    plan_id: int,
    payload: AllocationPlanRegenerateCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = allocation_plan_service.regenerate(
        session,
        actor,
        plan_id,
        command=payload,
        idempotency_key=idempotency_key,
    )
    session.commit()
    return success_response(
        result,
        "Allocation plan regenerated",
        actor=actor,
        version=result.version,
    )
