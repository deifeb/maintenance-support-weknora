from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.inventory.common import IdempotencyKeyDep
from app.api.v1.inventory.queries import SessionDep, TenantGuardDep
from app.core.exceptions import AppException, BusinessValidationError
from app.core.responses import success_response
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.inventory_operation import InventoryOperationPreviewRead
from app.schemas.inventory_stocktake import InventoryStocktakeRead
from app.security.actor import ActorContext
from app.security.permissions import require_admin, require_contributor
from app.services.inventory_stocktake_service import InventoryStocktakeService

router = APIRouter(tags=["inventory: stocktakes"])

ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep = Annotated[
    ActorContext,
    Depends(require_admin),
]
stocktake_service = InventoryStocktakeService()


class StocktakeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int = Field(gt=0)
    location_id: int = Field(gt=0)


class StocktakeVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)


class StocktakeCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    expected_line_version: int = Field(gt=0)
    counted_quantity: Decimal = Field(ge=0)


class StocktakeConfirmExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: int = Field(gt=0)
    expected_transaction_version: int = Field(gt=0)
    confirmation_token: str = Field(min_length=1)


class StocktakeRebaseLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: int = Field(gt=0)
    action: Literal["RECOUNT", "BASELINE_ACCEPT"]


class StocktakeRebaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    lines: list[StocktakeRebaseLineRequest] = Field(
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


def _normalize_confirm_error(
    exc: AppException,
    actor: ActorContext,
) -> None:
    if exc.request_id is None:
        exc.request_id = actor.request_id

    if exc.code not in {
        "INVENTORY_CONFIRMATION_TOKEN_INVALID",
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
    "/stocktakes",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def create_stocktake(
    payload: StocktakeCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.create(
        session,
        actor,
        command=payload.model_dump(mode="python"),
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake created",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/start",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def start_stocktake(
    stocktake_id: int,
    payload: StocktakeVersionRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.start(
        session,
        actor,
        stocktake_id,
        expected_version=payload.expected_version,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake started",
        actor=actor,
        version=item.version,
    )


@router.patch(
    "/stocktakes/{stocktake_id}/lines/{line_id}",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def update_stocktake_line(
    stocktake_id: int,
    line_id: int,
    payload: StocktakeCountRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.record_count(
        session,
        actor,
        stocktake_id,
        line_id,
        command=payload.model_dump(mode="python"),
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake count recorded",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/review",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def review_stocktake(
    stocktake_id: int,
    payload: StocktakeVersionRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.review(
        session,
        actor,
        stocktake_id,
        expected_version=payload.expected_version,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake moved to review",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/confirm/preview",
    response_model=MaintenanceSuccessResponse[
        InventoryOperationPreviewRead
    ],
)
def preview_stocktake_confirm(
    stocktake_id: int,
    payload: StocktakeVersionRequest,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.preview_confirm(
        session,
        actor,
        stocktake_id,
        command=payload.model_dump(mode="python"),
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake confirmation previewed",
        actor=actor,
        version=item.transaction_version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/confirm/execute",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def execute_stocktake_confirm(
    stocktake_id: int,
    payload: StocktakeConfirmExecuteRequest,
    session: SessionDep,
    actor: AdminDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    try:
        item = stocktake_service.execute_confirm(
            session,
            actor,
            stocktake_id,
            command=payload.model_dump(mode="python"),
            idempotency_key=_require_idempotency_key(
                idempotency_key,
                actor,
            ),
        )
    except AppException as exc:
        _normalize_confirm_error(exc, actor)

    session.commit()
    return success_response(
        item,
        "Inventory stocktake confirmation executed",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/rebase",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def rebase_stocktake(
    stocktake_id: int,
    payload: StocktakeRebaseRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.rebase_lines(
        session,
        actor,
        stocktake_id,
        command=payload.model_dump(mode="python"),
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake conflicts rebased",
        actor=actor,
        version=item.version,
    )


@router.post(
    "/stocktakes/{stocktake_id}/cancel",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def cancel_stocktake(
    stocktake_id: int,
    payload: StocktakeVersionRequest,
    session: SessionDep,
    actor: ContributorDep,
    _tenant_guard: TenantGuardDep,
    idempotency_key: IdempotencyKeyDep,
):
    item = stocktake_service.cancel(
        session,
        actor,
        stocktake_id,
        expected_version=payload.expected_version,
        idempotency_key=_require_idempotency_key(
            idempotency_key,
            actor,
        ),
    )
    session.commit()
    return success_response(
        item,
        "Inventory stocktake cancelled",
        actor=actor,
        version=item.version,
    )
