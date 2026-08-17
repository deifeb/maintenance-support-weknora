from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends

from app.api.v1.inventory.common import IdempotencyKeyDep
from app.api.v1.inventory.queries import SessionDep, TenantGuardDep
from app.core.exceptions import BusinessValidationError, ConflictError
from app.core.responses import success_response
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.inventory_reservation import (
    CancelCommand,
    InventoryReservationRead,
    IssueCommand,
    ReleaseCommand,
    ReserveCommand,
    ReturnCommand,
)
from app.security.actor import ActorContext
from app.security.permissions import require_contributor
from app.services.inventory_reservation_service import (
    InventoryReservationService,
)

router = APIRouter(tags=["inventory: reservations"])

ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
reservation_service = InventoryReservationService()


def _require_idempotency_key(
    value: str | None,
    actor: ActorContext,
) -> str:
    if value is not None:
        return value

    error = BusinessValidationError(
        "Idempotency-Key header is required",
        code="IDEMPOTENCY_KEY_REQUIRED",
        details={"retryable": False},
    )
    error.request_id = actor.request_id
    raise error


def _raise_reservation_state_conflict(
    exc: ConflictError,
    actor: ActorContext,
    reservation_id: int,
) -> NoReturn:
    if exc.code != "RESOURCE_CONFLICT":
        raise exc

    details = exc.details
    if (
        not isinstance(details, dict)
        or details.get("conflict_object")
        != "inventory_reservation"
    ):
        raise exc

    public_details = dict(details)
    public_details["object_id"] = reservation_id
    public_details["retryable"] = False
    public_details.setdefault("affected_lines", [])
    public_details.setdefault(
        "suggested_action",
        "reload_reservation",
    )

    error = ConflictError(
        exc.message,
        code="RESERVATION_STATE_CONFLICT",
        details=public_details,
    )
    error.request_id = actor.request_id
    raise error from exc


@router.post(
    "/reservations",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def create_reservation(
    payload: ReserveCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = reservation_service.reserve(
        session,
        actor,
        command=payload,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Reservation created",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/reservations/{reservation_id}/issue",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def issue_reservation(
    reservation_id: int,
    payload: IssueCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = reservation_service.issue(
            session,
            actor,
            reservation_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except ConflictError as exc:
        _raise_reservation_state_conflict(
            exc,
            actor,
            reservation_id,
        )

    session.commit()
    return success_response(
        item,
        "Reservation issued",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/reservations/{reservation_id}/release",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def release_reservation(
    reservation_id: int,
    payload: ReleaseCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = reservation_service.release(
            session,
            actor,
            reservation_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except ConflictError as exc:
        _raise_reservation_state_conflict(
            exc,
            actor,
            reservation_id,
        )

    session.commit()
    return success_response(
        item,
        "Reservation released",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/reservations/{reservation_id}/return",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def return_reservation(
    reservation_id: int,
    payload: ReturnCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = reservation_service.return_items(
            session,
            actor,
            reservation_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except ConflictError as exc:
        _raise_reservation_state_conflict(
            exc,
            actor,
            reservation_id,
        )

    session.commit()
    return success_response(
        item,
        "Reservation return recorded",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def cancel_reservation(
    reservation_id: int,
    payload: CancelCommand,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = reservation_service.cancel(
            session,
            actor,
            reservation_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except ConflictError as exc:
        _raise_reservation_state_conflict(
            exc,
            actor,
            reservation_id,
        )

    session.commit()
    return success_response(
        item,
        "Reservation cancelled",
        actor=actor,
        version=item.version,
    )
