import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import SessionLocal, get_db_session
from app.models import CalculationGroup
from app.models.enums import CalculationGroupStatus
from app.schemas.calculation_group import (
    CalculationGroupCreateRequest,
    CalculationItemDecisionRead,
    CalculationItemDecisionSaveRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.calculation_group_service import (
    calculation_group_service,
)
from app.workers.calculation_group_executor import (
    calculation_group_executor,
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
    for child in group.current_children:
        if child.calculation.status.value == "PENDING":
            calculation_group_executor.submit(
                actor.tenant_id,
                child.id,
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


@router.get("/{group_id}/comparison")
def compare_group(
    group_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    comparison = calculation_group_service.comparison(
        session,
        actor,
        group_id,
    )
    return success_response(
        comparison.model_dump(mode="json"),
        actor=actor,
    )


@router.put("/{group_id}/decisions/{spare_part_id}")
def save_item_decision(
    group_id: int,
    spare_part_id: int,
    payload: CalculationItemDecisionSaveRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    decision = calculation_group_service.save_decision(
        session,
        actor,
        group_id,
        spare_part_id=spare_part_id,
        expected_version=payload.expected_version,
        selected_child_id=payload.selected_child_id,
        final_quantity=payload.final_quantity,
        reason=payload.reason,
    )
    return success_response(
        CalculationItemDecisionRead.model_validate(
            decision
        ).model_dump(mode="json"),
        "Calculation item decision saved",
        actor=actor,
        version=decision.version,
    )


@router.post("/{group_id}/retry-failed")
def retry_failed(
    group_id: int,
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
    group = calculation_group_service.retry_failed(
        session,
        actor,
        group_id,
        idempotency_key=idempotency_key,
    )
    for child in group.current_children:
        if child.calculation.status.value == "PENDING":
            calculation_group_executor.submit(
                actor.tenant_id,
                child.id,
            )
    return success_response(
        _group_dict(group),
        "Failed candidates queued",
        actor=actor,
        version=group.version,
    )


@router.post("/{group_id}/cancel-running")
def cancel_running(
    group_id: int,
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
    group = calculation_group_service.cancel_running(
        session,
        actor,
        group_id,
        idempotency_key=idempotency_key,
    )
    return success_response(
        _group_dict(group),
        "Cancellation requested",
        actor=actor,
        version=group.version,
    )


@router.get("/{group_id}/events")
def list_events(
    group_id: int,
    session: SessionDep,
    actor: ViewerDep,
    after_sequence: int = Query(0, ge=0),
):
    events = calculation_group_service.events(
        session,
        actor,
        group_id,
        after_sequence=after_sequence,
    )
    return success_response(
        [
            {
                "id": event.id,
                "group_id": event.group_id,
                "child_id": event.child_id,
                "sequence": event.sequence,
                "event_type": event.event_type,
                "payload": event.payload_json,
                "occurred_at": event.occurred_at,
            }
            for event in events
        ],
        actor=actor,
    )


@router.get("/{group_id}/events/stream")
def stream_events(
    group_id: int,
    session: SessionDep,
    actor: ViewerDep,
    last_event_sequence: int = Query(0, ge=0),
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
):
    calculation_group_service.get(
        session,
        actor,
        group_id,
    )
    cursor = last_event_sequence
    if last_event_id is not None:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError:
            cursor = last_event_sequence
    terminal = {
        CalculationGroupStatus.COMPLETED,
        CalculationGroupStatus.PARTIALLY_COMPLETED,
        CalculationGroupStatus.FAILED,
        CalculationGroupStatus.CANCELLED,
        CalculationGroupStatus.INTERRUPTED,
    }

    def generate():
        nonlocal cursor
        while True:
            with SessionLocal() as stream_session:
                events = (
                    calculation_group_service
                    .group_repository.list_events(
                        stream_session,
                        actor.tenant_id,
                        group_id,
                        after_sequence=cursor,
                    )
                )
                group = (
                    calculation_group_service
                    .group_repository.get(
                        stream_session,
                        actor.tenant_id,
                        group_id,
                    )
                )
                for event in events:
                    cursor = event.sequence
                    payload = json.dumps(
                        {
                            "group_id": event.group_id,
                            "child_id": event.child_id,
                            "sequence": event.sequence,
                            "type": event.event_type,
                            "payload": event.payload_json,
                            "occurred_at": (
                                event.occurred_at.isoformat()
                            ),
                        },
                        ensure_ascii=False,
                    )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {payload}\n\n"
                    )
                if (
                    group is None
                    or (
                        group.status in terminal
                    )
                ):
                    return
            yield ": heartbeat\n\n"
            time.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
