from __future__ import annotations

import json
from typing import Annotated, Any

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
from app.schemas.inventory_reservation import InventoryReservationRead
from app.schemas.inventory_stocktake import InventoryStocktakeRead
from app.schemas.inventory_transfer import TransferRead
from app.security.actor import ActorContext
from app.security.permissions import require_viewer
from app.services.inventory_query_service import inventory_query_service

router = APIRouter(tags=["inventory: queries"])

SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]


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


TenantGuardDep = Annotated[None, Depends(reject_tenant_override)]


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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return success_response(
        inventory_query_service.list_balances(
            session,
            actor,
            page=page,
            page_size=page_size,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return success_response(
        inventory_query_service.list_transactions(
            session,
            actor,
            page=page,
            page_size=page_size,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return success_response(
        inventory_query_service.list_reservations(
            session,
            actor,
            page=page,
            page_size=page_size,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return success_response(
        inventory_query_service.list_transfers(
            session,
            actor,
            page=page,
            page_size=page_size,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return success_response(
        inventory_query_service.list_stocktakes(
            session,
            actor,
            page=page,
            page_size=page_size,
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
