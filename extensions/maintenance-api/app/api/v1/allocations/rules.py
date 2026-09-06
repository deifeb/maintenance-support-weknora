from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.allocations.common import (
    IdempotencyKeyDep,
    RuleListQueryGuardDep,
    SessionDep,
    TenantGuardDep,
)
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.schemas.allocation import (
    AllocationRuleActionResult,
    AllocationRuleDraftCommand,
    AllocationRulePublishCommand,
    AllocationRuleRead,
    AllocationRuleRetireCommand,
    AllocationSimulationSubmitCommand,
    AllocationSimulationSummaryRead,
)
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.allocation_rule_service import (
    AllocationRuleService,
)
from app.services.allocation_simulation_service import (
    allocation_simulation_service,
)
from app.workers.allocation_simulation_executor import (
    allocation_simulation_executor,
)

# PLAN05_4D_TASK6_GREEN_D: thin rule transaction adapters.
router = APIRouter(tags=["allocations: rules"])

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

allocation_rule_service = AllocationRuleService()


def _page_data(
    items: list[AllocationRuleRead],
    *,
    page: int,
    page_size: int,
    total: int,
) -> PageData[AllocationRuleRead]:
    pages = (total + page_size - 1) // page_size
    return PageData(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get(
    "/rules",
    response_model=MaintenanceSuccessResponse[
        PageData[AllocationRuleRead]
    ],
)
def list_rules(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: RuleListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    lineage_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=36,
    ),
):
    rules, total = allocation_rule_service.list_page(
        session,
        actor,
        page=page,
        page_size=page_size,
        status=status,
        lineage_id=lineage_id,
    )
    items = [
        allocation_rule_service.read(
            rule,
            latest_simulation=(
                allocation_simulation_service.latest_read_for_rule(
                    session,
                    actor.tenant_id,
                    rule.id,
                )
            ),
        )
        for rule in rules
    ]
    return success_response(
        _page_data(
            items,
            page=page,
            page_size=page_size,
            total=total,
        ),
        "Allocation rules queried",
        actor=actor,
    )


@router.post(
    "/rules",
    response_model=MaintenanceSuccessResponse[AllocationRuleRead],
)
def create_rule(
    payload: AllocationRuleDraftCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
):
    rule = allocation_rule_service.create_draft(
        session,
        actor,
        command=payload,
    )
    result = allocation_rule_service.read(
        rule,
        latest_simulation=None,
    )
    session.commit()
    return success_response(
        result,
        "Allocation rule created",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/rules/{rule_id}/simulate",
    response_model=MaintenanceSuccessResponse[
        AllocationSimulationSummaryRead
    ],
)
def simulate_rule(
    rule_id: int,
    payload: AllocationSimulationSubmitCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    simulation = allocation_simulation_service.submit(
        session,
        actor,
        candidate_rule_id=rule_id,
        baseline_rule_id=payload.baseline_rule_id,
        source_demand_list_id=payload.source_demand_list_id,
        sample_ref=payload.sample_ref,
        idempotency_key=idempotency_key,
        expected_rule_version=payload.expected_rule_version,
    )
    result = allocation_simulation_service.read(
        session,
        simulation,
    )

    session.commit()

    if result.status == "PENDING":
        try:
            allocation_simulation_executor.submit(
                actor.tenant_id,
                simulation.id,
            )
        except Exception as exc:
            allocation_simulation_service.fail_safely(
                actor.tenant_id,
                simulation.id,
                exc,
            )
            raise AppException(
                status_code=503,
                code="ALLOCATION_SIMULATION_ENQUEUE_FAILED",
                message=(
                    "Allocation simulation could not be enqueued"
                ),
                details={"retryable": True},
                request_id=actor.request_id,
            ) from exc

    return success_response(
        result,
        "Allocation simulation submitted",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/rules/{rule_id}/publish",
    response_model=MaintenanceSuccessResponse[
        AllocationRuleActionResult
    ],
)
def publish_rule(
    rule_id: int,
    payload: AllocationRulePublishCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    latest = allocation_simulation_service.latest_for_rule(
        session,
        actor.tenant_id,
        rule_id,
    )
    result = allocation_rule_service.publish_action(
        session,
        actor,
        rule_id,
        command=payload,
        latest_simulation=latest,
        idempotency_key=idempotency_key,
    )
    session.commit()
    return success_response(
        result,
        "Allocation rule published",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/rules/{rule_id}/retire",
    response_model=MaintenanceSuccessResponse[
        AllocationRuleActionResult
    ],
)
def retire_rule(
    rule_id: int,
    payload: AllocationRuleRetireCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
):
    rule = allocation_rule_service.retire(
        session,
        actor,
        rule_id,
        command=payload,
        idempotency_key="",
    )
    result = allocation_rule_service.action_result(rule)
    session.commit()
    return success_response(
        result,
        "Allocation rule retired",
        actor=actor,
        version=result.version,
    )
