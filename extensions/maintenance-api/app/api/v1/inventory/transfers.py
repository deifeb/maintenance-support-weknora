from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.inventory.common import IdempotencyKeyDep
from app.api.v1.inventory.queries import SessionDep, TenantGuardDep
from app.core.exceptions import AppException, BusinessValidationError
from app.core.responses import success_response
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.inventory_operation import InventoryOperationPreviewRead
from app.schemas.inventory_transfer import TransferCreateCommand, TransferRead
from app.security.actor import ActorContext
from app.security.permissions import require_admin
from app.services.inventory_transfer_service import InventoryTransferService

router = APIRouter(tags=["inventory: transfers"])

AdminDep = Annotated[
    ActorContext,
    Depends(require_admin),
]
transfer_service = InventoryTransferService()


class TransferVersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)


class TransferExecuteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: int = Field(gt=0)
    expected_transaction_version: int = Field(gt=0)
    confirmation_token: str = Field(min_length=1)


class TransferReceiveLineCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfer_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)


class TransferReceivePreviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    lines: tuple[TransferReceiveLineCommand, ...] = Field(
        min_length=1,
    )


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


def _normalize_transfer_error(
    exc: AppException,
    actor: ActorContext,
) -> None:
    if exc.request_id is None:
        exc.request_id = actor.request_id

    if exc.code not in {
        "INVENTORY_CONFIRMATION_EXPIRED",
        "INVENTORY_TRANSACTION_VERSION_CONFLICT",
    }:
        raise exc

    details = (
        dict(exc.details)
        if isinstance(exc.details, dict)
        else {}
    )
    details["retryable"] = False
    exc.details = details
    raise exc


@router.post(
    "/transfers",
    response_model=MaintenanceSuccessResponse[TransferRead],
)
def create_transfer(
    payload: TransferCreateCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = transfer_service.create(
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
        "Inventory transfer created",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/transfers/{transfer_id}/dispatch/preview",
    response_model=MaintenanceSuccessResponse[
        InventoryOperationPreviewRead
    ],
)
def preview_transfer_dispatch(
    transfer_id: int,
    payload: TransferVersionCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = transfer_service.preview_dispatch(
        session,
        actor,
        transfer_id,
        command=payload,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory transfer dispatch previewed",
        actor=actor,
        version=item.transaction_version,
    )


@router.post(
    "/transfers/{transfer_id}/dispatch/execute",
    response_model=MaintenanceSuccessResponse[TransferRead],
)
def execute_transfer_dispatch(
    transfer_id: int,
    payload: TransferExecuteCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = transfer_service.execute_dispatch(
            session,
            actor,
            transfer_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_transfer_error(exc, actor)
    session.commit()
    return success_response(
        item,
        "Inventory transfer dispatched",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/transfers/{transfer_id}/receive/preview",
    response_model=MaintenanceSuccessResponse[
        InventoryOperationPreviewRead
    ],
)
def preview_transfer_receive(
    transfer_id: int,
    payload: TransferReceivePreviewCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = transfer_service.preview_receive(
        session,
        actor,
        transfer_id,
        command=payload,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory transfer receipt previewed",
        actor=actor,
        version=item.transaction_version,
    )


@router.post(
    "/transfers/{transfer_id}/receive/execute",
    response_model=MaintenanceSuccessResponse[TransferRead],
)
def execute_transfer_receive(
    transfer_id: int,
    payload: TransferExecuteCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = transfer_service.execute_receive(
            session,
            actor,
            transfer_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_transfer_error(exc, actor)
    session.commit()
    return success_response(
        item,
        "Inventory transfer receipt executed",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/transfers/{transfer_id}/cancel",
    response_model=MaintenanceSuccessResponse[TransferRead],
)
def cancel_transfer(
    transfer_id: int,
    payload: TransferVersionCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = transfer_service.cancel(
        session,
        actor,
        transfer_id,
        expected_version=payload.expected_version,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory transfer cancelled",
        actor=actor,
        version=item.version,
    )
