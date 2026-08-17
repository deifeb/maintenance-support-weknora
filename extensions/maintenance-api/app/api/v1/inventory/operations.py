from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.inventory.common import IdempotencyKeyDep
from app.api.v1.inventory.queries import SessionDep, TenantGuardDep
from app.core.exceptions import (
    AppException,
    BusinessValidationError,
)
from app.core.responses import success_response
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.inventory_ledger import InventoryTransactionRead
from app.schemas.inventory_operation import InventoryOperationPreviewRead
from app.security.actor import ActorContext
from app.security.permissions import require_admin
from app.services.inventory_operation_service import (
    InventoryOperationService,
)

router = APIRouter(tags=["inventory: operations"])

AdminDep = Annotated[
    ActorContext,
    Depends(require_admin),
]
operation_service = InventoryOperationService()


class OperationPreviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_type: Literal["ADJUST", "FREEZE", "UNFREEZE"]
    balance_id: int = Field(gt=0)
    expected_balance_version: int = Field(gt=0)
    reason: str
    deltas: dict[str, Any] | None = None
    lot_id: int | None = Field(default=None, gt=0)
    expected_lot_version: int | None = Field(
        default=None,
        gt=0,
    )


class OperationExecuteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_transaction_version: int = Field(gt=0)
    confirmation_token: str = Field(min_length=1)


class ReversePreviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_transaction_version: int = Field(gt=0)
    reason: str


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


def _normalize_operation_error(
    exc: AppException,
    actor: ActorContext,
    *,
    transaction_id: int | None = None,
) -> None:
    if exc.request_id is None:
        exc.request_id = actor.request_id

    details = (
        dict(exc.details)
        if isinstance(exc.details, dict)
        else {}
    )

    is_transaction_version_conflict = (
        exc.code == "RESOURCE_CONFLICT"
        and details.get("conflict_object")
        == "inventory_transaction"
        and "expected_version" in details
        and "actual_version" in details
    )
    if is_transaction_version_conflict:
        exc.code = "INVENTORY_TRANSACTION_VERSION_CONFLICT"
        details["object_id"] = details.get(
            "object_id",
            details.get("transaction_id", transaction_id),
        )
        details.setdefault("affected_lines", [])
        details["retryable"] = False
        details.setdefault(
            "suggested_action",
            "reload inventory transaction and preview again",
        )
        exc.details = details
        raise exc

    if exc.code != "INVENTORY_OPERATION_STATE_CONFLICT":
        raise exc

    object_id = details.get("object_id")
    if object_id is None:
        object_id = details.get("transaction_id")
    if object_id is None:
        object_id = details.get("lot_id")
    if object_id is None:
        object_id = transaction_id

    details["conflict_object"] = details.get(
        "conflict_object",
        "inventory_transaction",
    )
    details["object_id"] = object_id
    details.setdefault("expected_version", None)
    details.setdefault("actual_version", None)
    details.setdefault("affected_lines", [])
    details["retryable"] = False
    details.setdefault(
        "suggested_action",
        "reload inventory state and preview again",
    )
    exc.details = details
    raise exc


@router.post(
    "/operations/preview",
    response_model=MaintenanceSuccessResponse[
        InventoryOperationPreviewRead
    ],
)
def preview_operation(
    payload: OperationPreviewCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = operation_service.preview(
            session,
            actor,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_operation_error(exc, actor)

    session.commit()
    return success_response(
        item,
        "Inventory operation previewed",
        actor=actor,
        version=item.transaction_version,
    )


@router.post(
    "/operations/{transaction_id}/execute",
    response_model=MaintenanceSuccessResponse[
        InventoryTransactionRead
    ],
)
def execute_operation(
    transaction_id: int,
    payload: OperationExecuteCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = operation_service.execute(
            session,
            actor,
            transaction_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_operation_error(
            exc,
            actor,
            transaction_id=transaction_id,
        )

    session.commit()
    return success_response(
        item,
        "Inventory operation executed",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/operations/{transaction_id}/reverse/preview",
    response_model=MaintenanceSuccessResponse[
        InventoryOperationPreviewRead
    ],
)
def preview_reverse_operation(
    transaction_id: int,
    payload: ReversePreviewCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = operation_service.preview_reverse(
            session,
            actor,
            transaction_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_operation_error(
            exc,
            actor,
            transaction_id=transaction_id,
        )

    session.commit()
    return success_response(
        item,
        "Inventory reversal previewed",
        actor=actor,
        version=item.transaction_version,
    )


@router.post(
    "/operations/{transaction_id}/reverse/execute",
    response_model=MaintenanceSuccessResponse[
        InventoryTransactionRead
    ],
)
def execute_reverse_operation(
    transaction_id: int,
    payload: OperationExecuteCommand,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = operation_service.execute(
            session,
            actor,
            transaction_id,
            command=payload,
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_operation_error(
            exc,
            actor,
            transaction_id=transaction_id,
        )

    session.commit()
    return success_response(
        item,
        "Inventory reversal executed",
        actor=actor,
        version=item.version,
    )
