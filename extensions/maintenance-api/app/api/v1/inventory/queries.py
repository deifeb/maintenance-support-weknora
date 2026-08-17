from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import MaintenanceSuccessResponse, PageData
from app.schemas.inventory_ledger import (
    InventoryBalanceRead,
    InventoryTransactionRead,
)
from app.schemas.inventory_operation import InventoryOperationType
from app.schemas.inventory_reservation import InventoryReservationRead
from app.schemas.inventory_stocktake import InventoryStocktakeRead
from app.schemas.inventory_transfer import TransferRead
from app.security.actor import ActorContext
from app.security.permissions import require_viewer
from app.services.inventory_query_service import inventory_query_service

router = APIRouter(tags=["inventory: queries"])

SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]

SortOrder = Literal["asc", "desc"]
BalanceSortBy = Literal[
    "id",
    "warehouse_id",
    "spare_part_id",
    "location_id",
    "lot_id",
    "on_hand_quantity",
    "reserved_quantity",
    "available_quantity",
]
TransactionSortBy = Literal[
    "id",
    "operation_type",
    "status",
    "completed_at",
]
ReservationSortBy = Literal["id", "status", "expires_at"]
TransferSortBy = Literal[
    "id",
    "status",
    "dispatched_at",
    "completed_at",
]
StocktakeSortBy = Literal[
    "id",
    "status",
    "snapshot_at",
    "confirmed_at",
]

TransactionStatusQuery = Literal[
    "PREVIEWED",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "EXPIRED",
    "REVERSED",
]
ReservationStatusQuery = Literal[
    "ACTIVE",
    "PARTIALLY_ISSUED",
    "FULFILLED",
    "RELEASED",
    "CANCELLED",
    "EXPIRED",
]
TransferStatusQuery = Literal[
    "DRAFT",
    "DISPATCHED",
    "PARTIALLY_RECEIVED",
    "COMPLETED",
    "CANCELLED",
]
StocktakeStatusQuery = Literal[
    "DRAFT",
    "COUNTING",
    "REVIEWING",
    "CONFIRMED",
    "CONFLICTED",
    "CANCELLED",
]


def _tenant_override_error(
    *,
    location: str,
    value: Any,
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": (location, "tenant_id"),
                "msg": "tenant_id is not accepted",
                "input": value,
            }
        ]
    )


async def reject_tenant_override(request: Request) -> None:
    if "tenant_id" in request.query_params:
        raise _tenant_override_error(
            location="query",
            value=request.query_params.get("tenant_id"),
        )

    raw_body = await request.body()
    if not raw_body:
        return

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return

    if isinstance(payload, dict) and "tenant_id" in payload:
        raise _tenant_override_error(
            location="body",
            value=payload["tenant_id"],
        )


def _duplicate_query_error(
    *,
    parameter: str,
    values: list[str],
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "multiple_argument_values",
                "loc": ("query", parameter),
                "msg": "query parameter must be provided at most once",
                "input": values,
            }
        ]
    )


def _reject_duplicate_query_parameters(parameter_names: frozenset[str]):
    async def dependency(request: Request) -> None:
        for parameter in parameter_names:
            values = request.query_params.getlist(parameter)
            if len(values) > 1:
                raise _duplicate_query_error(
                    parameter=parameter,
                    values=values,
                )

    return dependency


_COMMON_LIST_QUERY_PARAMS = frozenset(
    {"page", "page_size", "sort_by", "sort_order"}
)
_BALANCE_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {
        "warehouse_id",
        "spare_part_id",
        "location_id",
        "lot_id",
        "serial_item_id",
    }
)
_TRANSACTION_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"operation_type", "status", "reference_type", "reference_id"}
)
_RESERVATION_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"status", "owner_type", "owner_id"}
)
_TRANSFER_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {
        "status",
        "source_warehouse_id",
        "source_location_id",
        "target_warehouse_id",
        "target_location_id",
        "reference_type",
        "reference_id",
    }
)
_STOCKTAKE_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"status", "warehouse_id", "location_id"}
)

TenantGuardDep = Annotated[None, Depends(reject_tenant_override)]
BalanceListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_BALANCE_LIST_QUERY_PARAMS)),
]
TransactionListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_TRANSACTION_LIST_QUERY_PARAMS)),
]
ReservationListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_RESERVATION_LIST_QUERY_PARAMS)),
]
TransferListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_TRANSFER_LIST_QUERY_PARAMS)),
]
StocktakeListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_STOCKTAKE_LIST_QUERY_PARAMS)),
]


@router.get(
    "/balances",
    response_model=MaintenanceSuccessResponse[
        PageData[InventoryBalanceRead]
    ],
)
def list_balances(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: BalanceListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    warehouse_id: int | None = Query(default=None, gt=0),
    spare_part_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    lot_id: int | None = Query(default=None, gt=0),
    serial_item_id: int | None = Query(default=None, gt=0),
    sort_by: BalanceSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
    return success_response(
        inventory_query_service.list_balances(
            session,
            actor,
            page=page,
            page_size=page_size,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=location_id,
            lot_id=lot_id,
            serial_item_id=serial_item_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/balances/{identifier}",
    response_model=MaintenanceSuccessResponse[InventoryBalanceRead],
)
def get_balance(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    item = inventory_query_service.get_balance(
        session,
        actor,
        identifier,
    )
    return success_response(
        item,
        actor=actor,
        version=item.version,
    )


@router.get(
    "/transactions",
    response_model=MaintenanceSuccessResponse[
        PageData[InventoryTransactionRead]
    ],
)
def list_transactions(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: TransactionListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operation_type: InventoryOperationType | None = Query(default=None),
    status: TransactionStatusQuery | None = Query(default=None),
    reference_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r".*\S.*",
    ),
    reference_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r".*\S.*",
    ),
    sort_by: TransactionSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
    return success_response(
        inventory_query_service.list_transactions(
            session,
            actor,
            page=page,
            page_size=page_size,
            operation_type=operation_type,
            status=status,
            reference_type=reference_type,
            reference_id=reference_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/transactions/{identifier}",
    response_model=MaintenanceSuccessResponse[
        InventoryTransactionRead
    ],
)
def get_transaction(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    item = inventory_query_service.get_transaction(
        session,
        actor,
        identifier,
    )
    return success_response(
        item,
        actor=actor,
        version=item.version,
    )


@router.get(
    "/reservations",
    response_model=MaintenanceSuccessResponse[
        PageData[InventoryReservationRead]
    ],
)
def list_reservations(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: ReservationListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: ReservationStatusQuery | None = Query(default=None),
    owner_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r".*\S.*",
    ),
    owner_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r".*\S.*",
    ),
    sort_by: ReservationSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
    return success_response(
        inventory_query_service.list_reservations(
            session,
            actor,
            page=page,
            page_size=page_size,
            status=status,
            owner_type=owner_type,
            owner_id=owner_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/reservations/{identifier}",
    response_model=MaintenanceSuccessResponse[
        InventoryReservationRead
    ],
)
def get_reservation(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    item = inventory_query_service.get_reservation(
        session,
        actor,
        identifier,
    )
    return success_response(
        item,
        actor=actor,
        version=item.version,
    )


@router.get(
    "/transfers",
    response_model=MaintenanceSuccessResponse[PageData[TransferRead]],
)
def list_transfers(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: TransferListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: TransferStatusQuery | None = Query(default=None),
    source_warehouse_id: int | None = Query(default=None, gt=0),
    source_location_id: int | None = Query(default=None, gt=0),
    target_warehouse_id: int | None = Query(default=None, gt=0),
    target_location_id: int | None = Query(default=None, gt=0),
    reference_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r".*\S.*",
    ),
    reference_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r".*\S.*",
    ),
    sort_by: TransferSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
    return success_response(
        inventory_query_service.list_transfers(
            session,
            actor,
            page=page,
            page_size=page_size,
            status=status,
            source_warehouse_id=source_warehouse_id,
            source_location_id=source_location_id,
            target_warehouse_id=target_warehouse_id,
            target_location_id=target_location_id,
            reference_type=reference_type,
            reference_id=reference_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/transfers/{identifier}",
    response_model=MaintenanceSuccessResponse[TransferRead],
)
def get_transfer(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    item = inventory_query_service.get_transfer(
        session,
        actor,
        identifier,
    )
    return success_response(
        item,
        actor=actor,
        version=item.version,
    )


@router.get(
    "/stocktakes",
    response_model=MaintenanceSuccessResponse[
        PageData[InventoryStocktakeRead]
    ],
)
def list_stocktakes(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: StocktakeListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: StocktakeStatusQuery | None = Query(default=None),
    warehouse_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    sort_by: StocktakeSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
    return success_response(
        inventory_query_service.list_stocktakes(
            session,
            actor,
            page=page,
            page_size=page_size,
            status=status,
            warehouse_id=warehouse_id,
            location_id=location_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        "Query completed",
        actor=actor,
    )


@router.get(
    "/stocktakes/{identifier}",
    response_model=MaintenanceSuccessResponse[
        InventoryStocktakeRead
    ],
)
def get_stocktake(
    identifier: int,
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
):
    item = inventory_query_service.get_stocktake(
        session,
        actor,
        identifier,
    )
    return success_response(
        item,
        actor=actor,
        version=item.version,
    )
