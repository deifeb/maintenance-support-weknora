from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryStocktake,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

WRITE_ROUTES = {
    "create": (
        "post",
        "/api/v1/inventory/stocktakes",
    ),
    "start": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/start",
    ),
    "update_line": (
        "patch",
        "/api/v1/inventory/stocktakes/{stocktake_id}/lines/{line_id}",
    ),
    "review": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/review",
    ),
    "confirm_preview": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/confirm/preview",
    ),
    "confirm_execute": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/confirm/execute",
    ),
    "rebase": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/rebase",
    ),
    "cancel": (
        "post",
        "/api/v1/inventory/stocktakes/{stocktake_id}/cancel",
    ),
}
EXPECTED_OPENAPI_OPERATIONS = {
    (method, path)
    for method, path in WRITE_ROUTES.values()
}
STOCKTAKES_ROUTE_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "inventory"
    / "stocktakes.py"
)


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    role: MaintenanceRole,
    request_id: str,
    tenant_id: str = "tenant-a",
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{role.value}-{tenant_id}",
        role=role,
        request_id=request_id,
    )
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _path_for(
    operation: str,
    *,
    stocktake_id: int = 1,
    line_id: int = 1,
) -> str:
    _, template = WRITE_ROUTES[operation]
    return template.format(
        stocktake_id=stocktake_id,
        line_id=line_id,
    )


def _minimal_payload(operation: str) -> dict[str, Any]:
    if operation == "create":
        return {
            "warehouse_id": 1,
            "location_id": 1,
        }
    if operation in {"start", "review", "cancel"}:
        return {"expected_version": 1}
    if operation == "update_line":
        return {
            "expected_version": 1,
            "expected_line_version": 1,
            "counted_quantity": "1.0000",
        }
    if operation == "confirm_preview":
        return {"expected_version": 1}
    if operation == "confirm_execute":
        return {
            "transaction_id": 1,
            "expected_transaction_version": 1,
            "confirmation_token": "slice9e-token",
        }
    if operation == "rebase":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "line_id": 1,
                    "action": "RECOUNT",
                }
            ],
        }
    raise AssertionError(f"unsupported operation: {operation}")


def _request(
    client: TestClient,
    operation: str,
    *,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any],
):
    method, _ = WRITE_ROUTES[operation]
    if method == "patch":
        return client.patch(
            path,
            headers=headers,
            json=payload,
        )
    return client.post(
        path,
        headers=headers,
        json=payload,
    )


def _seed_scope(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
    quantities: tuple[str, ...] = (
        "10.0000",
        "4.0000",
    ),
) -> dict[str, Any]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-API-STK-{suffix}",
        name=f"Stocktake API Warehouse {suffix}",
    )
    session.add(warehouse)
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-API-STK-{suffix}",
        name=f"Stocktake API Location {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    balances: list[InventoryBalance] = []
    for index, quantity in enumerate(
        quantities,
        start=1,
    ):
        part = SparePart(
            tenant_id=tenant_id,
            code=f"SP-API-STK-{suffix}-{index}",
            name=f"Stocktake API Spare {suffix} {index}",
            unit="EA",
            is_serialized=False,
        )
        session.add(part)
        session.flush()

        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=part.id,
            lot_id=None,
            on_hand_quantity=Decimal(quantity),
            reserved_quantity=Decimal("0.0000"),
            damaged_quantity=Decimal("0.0000"),
            quarantined_quantity=Decimal("0.0000"),
            in_transit_quantity=Decimal("0.0000"),
        )
        session.add(balance)
        session.flush()
        balances.append(balance)

    session.commit()
    return {
        "warehouse": warehouse,
        "location": location,
        "balances": balances,
    }


def _assert_success(
    response,
    *,
    request_id: str,
    tenant_id: str = "tenant-a",
) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("success") is True, payload
    assert payload["meta"]["request_id"] == request_id
    assert payload["meta"]["tenant_id"] == tenant_id
    return payload["data"]


def _assert_error(
    response,
    *,
    status_code: int,
    code: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert payload.get("success") is False, (
        "expected maintenance error envelope, "
        f"got: {payload}"
    )
    error = payload.get("error")
    assert isinstance(error, dict), payload
    assert error.get("code") == code
    if request_id is not None:
        assert error.get("request_id") == request_id
    return error


def _create_stocktake(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    suffix: str,
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
    tenant_id: str = "tenant-a",
    quantities: tuple[str, ...] = (
        "10.0000",
        "4.0000",
    ),
) -> tuple[dict[str, Any], dict[str, Any]]:
    facts = _seed_scope(
        session,
        tenant_id=tenant_id,
        suffix=suffix,
        quantities=quantities,
    )
    request_id = f"slice9e-create-{suffix}"
    response = client.post(
        "/api/v1/inventory/stocktakes",
        headers=_headers(
            internal_auth_headers,
            role=role,
            tenant_id=tenant_id,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "warehouse_id": facts["warehouse"].id,
            "location_id": facts["location"].id,
        },
    )
    stocktake = _assert_success(
        response,
        request_id=request_id,
        tenant_id=tenant_id,
    )
    assert stocktake["status"] == "DRAFT"
    return facts, stocktake


def _start_stocktake(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    *,
    suffix: str,
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
    tenant_id: str = "tenant-a",
) -> dict[str, Any]:
    request_id = f"slice9e-start-{suffix}"
    response = client.post(
        _path_for(
            "start",
            stocktake_id=stocktake["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            tenant_id=tenant_id,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": stocktake["version"]},
    )
    started = _assert_success(
        response,
        request_id=request_id,
        tenant_id=tenant_id,
    )
    assert started["status"] == "COUNTING"
    return started


def _count_line(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    line: dict[str, Any],
    *,
    suffix: str,
    quantity: Decimal,
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> dict[str, Any]:
    request_id = f"slice9e-count-{suffix}-{line['id']}"
    response = client.patch(
        _path_for(
            "update_line",
            stocktake_id=stocktake["id"],
            line_id=line["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": stocktake["version"],
            "expected_line_version": line["version"],
            "counted_quantity": format(
                quantity,
                ".4f",
            ),
        },
    )
    return _assert_success(
        response,
        request_id=request_id,
    )


def _count_all_with_minus_one(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    *,
    suffix: str,
) -> dict[str, Any]:
    current = stocktake
    original_ids = [
        line["id"]
        for line in stocktake["lines"]
    ]
    for line_id in original_ids:
        line = next(
            item
            for item in current["lines"]
            if item["id"] == line_id
        )
        quantity = (
            Decimal(line["system_quantity"])
            - Decimal("1.0000")
        )
        current = _count_line(
            client,
            internal_auth_headers,
            current,
            line,
            suffix=suffix,
            quantity=quantity,
        )
    return current


def _review_stocktake(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    *,
    suffix: str,
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> dict[str, Any]:
    request_id = f"slice9e-review-{suffix}"
    response = client.post(
        _path_for(
            "review",
            stocktake_id=stocktake["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": stocktake["version"]},
    )
    reviewed = _assert_success(
        response,
        request_id=request_id,
    )
    assert reviewed["status"] == "REVIEWING"
    return reviewed


def _reviewed_stocktake(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    suffix: str,
    quantities: tuple[str, ...] = (
        "10.0000",
        "4.0000",
    ),
) -> tuple[dict[str, Any], dict[str, Any]]:
    facts, created = _create_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix=suffix,
        quantities=quantities,
    )
    started = _start_stocktake(
        client,
        internal_auth_headers,
        created,
        suffix=suffix,
    )
    counted = _count_all_with_minus_one(
        client,
        internal_auth_headers,
        started,
        suffix=suffix,
    )
    reviewed = _review_stocktake(
        client,
        internal_auth_headers,
        counted,
        suffix=suffix,
    )
    return facts, reviewed


def _confirm_preview(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    *,
    suffix: str,
    role: MaintenanceRole = MaintenanceRole.ADMIN,
) -> dict[str, Any]:
    request_id = f"slice9e-confirm-preview-{suffix}"
    response = client.post(
        _path_for(
            "confirm_preview",
            stocktake_id=stocktake["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": stocktake["version"]},
    )
    return _assert_success(
        response,
        request_id=request_id,
    )


def _confirm_execute(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    stocktake: dict[str, Any],
    preview: dict[str, Any],
    *,
    suffix: str,
    role: MaintenanceRole = MaintenanceRole.ADMIN,
) -> dict[str, Any]:
    request_id = f"slice9e-confirm-execute-{suffix}"
    response = client.post(
        _path_for(
            "confirm_execute",
            stocktake_id=stocktake["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "transaction_id": preview["transaction_id"],
            "expected_transaction_version": (
                preview["transaction_version"]
            ),
            "confirmation_token": preview[
                "confirmation_token"
            ],
        },
    )
    return _assert_success(
        response,
        request_id=request_id,
    )


def _balance(
    session: Session,
    balance_id: int,
) -> InventoryBalance:
    session.expire_all()
    item = session.get(InventoryBalance, balance_id)
    assert item is not None
    return item


def _transaction(
    session: Session,
    transaction_id: int,
) -> InventoryTransaction:
    session.expire_all()
    item = session.get(
        InventoryTransaction,
        transaction_id,
    )
    assert item is not None
    return item


def test_inventory_stocktake_write_routes_are_registered(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    missing = sorted(
        f"{method.upper()} {path}"
        for method, path in EXPECTED_OPENAPI_OPERATIONS
        if method not in openapi_paths.get(path, {})
    )
    assert missing == [], (
        "Task 9 Slice 9E missing stocktake write routes: "
        f"{missing}"
    )


def test_inventory_stocktake_routes_require_authentication(
    client: TestClient,
) -> None:
    failures: list[tuple[str, int]] = []
    for operation in WRITE_ROUTES:
        response = _request(
            client,
            operation,
            path=_path_for(operation),
            headers={
                "Idempotency-Key": (
                    f"slice9e-unauth-{operation}"
                )
            },
            payload=_minimal_payload(operation),
        )
        if response.status_code != 401:
            failures.append(
                (operation, response.status_code)
            )
    assert failures == []


def test_inventory_stocktake_routes_reject_viewer(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int]] = []
    for operation in WRITE_ROUTES:
        response = _request(
            client,
            operation,
            path=_path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.VIEWER,
                request_id=f"slice9e-viewer-{operation}",
                idempotency_key=f"slice9e-viewer-{operation}",
            ),
            payload=_minimal_payload(operation),
        )
        if response.status_code != 403:
            failures.append(
                (operation, response.status_code)
            )
    assert failures == []


@pytest.mark.parametrize(
    "operation",
    [
        "confirm_preview",
        "confirm_execute",
    ],
)
def test_stocktake_confirm_routes_reject_contributor(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    operation: str,
) -> None:
    response = _request(
        client,
        operation,
        path=_path_for(operation),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=f"slice9e-contributor-{operation}",
            idempotency_key=f"slice9e-contributor-{operation}",
        ),
        payload=_minimal_payload(operation),
    )
    assert response.status_code == 403, response.text


def test_all_stocktake_writes_require_idempotency_key(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    expected_roles = {
        "create": MaintenanceRole.CONTRIBUTOR,
        "start": MaintenanceRole.CONTRIBUTOR,
        "update_line": MaintenanceRole.CONTRIBUTOR,
        "review": MaintenanceRole.CONTRIBUTOR,
        "confirm_preview": MaintenanceRole.ADMIN,
        "confirm_execute": MaintenanceRole.ADMIN,
        "rebase": MaintenanceRole.CONTRIBUTOR,
        "cancel": MaintenanceRole.CONTRIBUTOR,
    }
    failures: list[tuple[str, int, str | None]] = []
    for operation, role in expected_roles.items():
        request_id = f"slice9e-missing-key-{operation}"
        response = _request(
            client,
            operation,
            path=_path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=role,
                request_id=request_id,
            ),
            payload=_minimal_payload(operation),
        )
        if response.status_code != 422:
            failures.append(
                (operation, response.status_code, None)
            )
            continue
        error = response.json().get("error", {})
        if (
            error.get("code")
            != "IDEMPOTENCY_KEY_REQUIRED"
            or error.get("request_id") != request_id
        ):
            failures.append(
                (
                    operation,
                    response.status_code,
                    error.get("code"),
                )
            )
    assert failures == []


def test_stocktake_writes_reject_tenant_id_query_or_body(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    expected_roles = {
        "create": MaintenanceRole.CONTRIBUTOR,
        "start": MaintenanceRole.CONTRIBUTOR,
        "update_line": MaintenanceRole.CONTRIBUTOR,
        "review": MaintenanceRole.CONTRIBUTOR,
        "confirm_preview": MaintenanceRole.ADMIN,
        "confirm_execute": MaintenanceRole.ADMIN,
        "rebase": MaintenanceRole.CONTRIBUTOR,
        "cancel": MaintenanceRole.CONTRIBUTOR,
    }
    failures: list[tuple[str, str, int]] = []
    for operation, role in expected_roles.items():
        path = _path_for(operation)
        payload = _minimal_payload(operation)
        headers = _headers(
            internal_auth_headers,
            role=role,
            request_id=f"slice9e-tenant-{operation}",
            idempotency_key=f"slice9e-tenant-{operation}",
        )

        query_response = _request(
            client,
            operation,
            path=f"{path}?tenant_id=tenant-b",
            headers=headers,
            payload=payload,
        )
        if query_response.status_code != 422:
            failures.append(
                (
                    operation,
                    "query",
                    query_response.status_code,
                )
            )

        body_response = _request(
            client,
            operation,
            path=path,
            headers=headers,
            payload={
                **payload,
                "tenant_id": "tenant-b",
            },
        )
        if body_response.status_code != 422:
            failures.append(
                (
                    operation,
                    "body",
                    body_response.status_code,
                )
            )
    assert failures == []


def test_contributor_can_create_start_count_review_and_cancel(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, created = _create_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONTRIBUTOR-LIFECYCLE",
        quantities=("5.0000",),
    )
    assert len(created["lines"]) == 1
    line = created["lines"][0]
    assert line["system_quantity"] == "5.0000"
    assert line["counted_quantity"] is None
    assert line["variance_quantity"] is None
    assert line["resolution"] == "PENDING"

    started = _start_stocktake(
        client,
        internal_auth_headers,
        created,
        suffix="CONTRIBUTOR-LIFECYCLE",
    )
    counted = _count_line(
        client,
        internal_auth_headers,
        started,
        started["lines"][0],
        suffix="CONTRIBUTOR-LIFECYCLE",
        quantity=Decimal("4.0000"),
    )
    assert counted["status"] == "COUNTING"
    assert counted["lines"][0]["counted_quantity"] == "4.0000"
    assert counted["lines"][0]["variance_quantity"] == "-1.0000"

    reviewed = _review_stocktake(
        client,
        internal_auth_headers,
        counted,
        suffix="CONTRIBUTOR-LIFECYCLE",
    )
    assert reviewed["status"] == "REVIEWING"

    # Use a separate DRAFT stocktake to prove contributor cancel.
    _, cancellable = _create_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONTRIBUTOR-CANCEL",
        quantities=("1.0000",),
    )
    request_id = "slice9e-contributor-cancel"
    cancelled_response = client.post(
        _path_for(
            "cancel",
            stocktake_id=cancellable["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": cancellable["version"],
        },
    )
    cancelled = _assert_success(
        cancelled_response,
        request_id=request_id,
    )
    assert cancelled["status"] == "CANCELLED"

    source = _balance(
        session,
        facts["balances"][0].id,
    )
    assert source.on_hand_quantity == Decimal("5.0000")


def test_create_stocktake_replay_and_reused_key_contract(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts = _seed_scope(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REPLAY",
        quantities=("3.0000",),
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="slice9e-create-replay",
        idempotency_key="slice9e-create-replay",
    )
    payload = {
        "warehouse_id": facts["warehouse"].id,
        "location_id": facts["location"].id,
    }

    first = client.post(
        "/api/v1/inventory/stocktakes",
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9e-create-replay",
    )
    replay = client.post(
        "/api/v1/inventory/stocktakes",
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9e-create-replay",
    )
    assert replay_data == first_data
    session.expire_all()
    assert session.scalar(
        select(func.count(InventoryStocktake.id))
    ) == 1

    foreign_scope = _seed_scope(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REUSED",
        quantities=("2.0000",),
    )
    conflict = client.post(
        "/api/v1/inventory/stocktakes",
        headers=headers,
        json={
            "warehouse_id": foreign_scope["warehouse"].id,
            "location_id": foreign_scope["location"].id,
        },
    )
    error = _assert_error(
        conflict,
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        request_id="slice9e-create-replay",
    )
    assert error["details"]["retryable"] is False


def test_stocktake_is_tenant_scoped(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, created = _create_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="TENANT-SCOPE",
        tenant_id="tenant-a",
        quantities=("3.0000",),
    )
    request_id = "slice9e-cross-tenant"
    response = client.post(
        _path_for(
            "start",
            stocktake_id=created["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            tenant_id="tenant-b",
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": created["version"]},
    )
    _assert_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        request_id=request_id,
    )


def test_stocktake_version_conflict_is_stable(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, created = _create_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="VERSION-CONFLICT",
        quantities=("2.0000",),
    )
    request_id = "slice9e-version-conflict"
    response = client.post(
        _path_for(
            "start",
            stocktake_id=created["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": created["version"] + 1,
        },
    )
    error = _assert_error(
        response,
        status_code=409,
        code="STOCKTAKE_VERSION_CONFLICT",
        request_id=request_id,
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_stocktake"
    assert details["object_id"] == created["id"]
    assert details["retryable"] is False
    assert details["affected_lines"] == []


def test_confirm_preview_requires_admin_and_has_no_mutation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONFIRM-PREVIEW",
        quantities=("5.0000",),
    )
    contributor_response = client.post(
        _path_for(
            "confirm_preview",
            stocktake_id=reviewed["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id="slice9e-confirm-preview-contributor",
            idempotency_key="slice9e-confirm-preview-contributor",
        ),
        json={"expected_version": reviewed["version"]},
    )
    assert contributor_response.status_code == 403

    balance_id = facts["balances"][0].id
    before = _balance(
        session,
        balance_id,
    ).on_hand_quantity
    ledger_before = session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    )

    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="CONFIRM-PREVIEW",
    )
    assert preview["status"] == "PREVIEWED"
    assert preview["operation_type"] == "STOCKTAKE_CONFIRM"
    assert preview["confirmation_token"]
    assert preview["transaction_version"] > 0
    assert "_extensions" not in preview
    assert (
        _balance(session, balance_id).on_hand_quantity
        == before
    )
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_before

    stored = _transaction(
        session,
        preview["transaction_id"],
    )
    assert stored.confirmation_token_hash == hashlib.sha256(
        preview["confirmation_token"].encode("utf-8")
    ).hexdigest()
    assert stored.confirmation_token_hash != preview[
        "confirmation_token"
    ]
    assert preview["confirmation_token"] not in str(
        stored.response_snapshot_json
    )


def test_confirm_preview_replay_returns_plaintext_token_once(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="PREVIEW-REPLAY",
        quantities=("4.0000",),
    )
    path = _path_for(
        "confirm_preview",
        stocktake_id=reviewed["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9e-preview-replay",
        idempotency_key="slice9e-preview-replay",
    )
    payload = {"expected_version": reviewed["version"]}

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9e-preview-replay",
    )
    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9e-preview-replay",
    )
    assert first_data["confirmation_token"]
    assert replay_data["confirmation_token"] is None
    assert (
        replay_data["transaction_id"]
        == first_data["transaction_id"]
    )


def test_confirm_execute_adjusts_all_nonconflicting_lines_once(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONFIRM-FULL",
        quantities=("10.0000", "4.0000"),
    )
    original_quantities = {
        balance.id: balance.on_hand_quantity
        for balance in facts["balances"]
    }
    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="CONFIRM-FULL",
    )
    result = _confirm_execute(
        client,
        internal_auth_headers,
        reviewed,
        preview,
        suffix="CONFIRM-FULL",
    )
    assert result["status"] == "CONFIRMED"
    assert all(
        line["resolution"] == "ADJUSTED"
        for line in result["lines"]
    )
    for balance in facts["balances"]:
        assert (
            _balance(
                session,
                balance.id,
            ).on_hand_quantity
            == original_quantities[balance.id]
            - Decimal("1.0000")
        )
    transaction = _transaction(
        session,
        preview["transaction_id"],
    )
    assert transaction.status == "COMPLETED"


def test_confirm_execute_partial_conflict_mutates_only_successful_lines(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONFIRM-PARTIAL",
        quantities=("10.0000", "4.0000"),
    )
    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="CONFIRM-PARTIAL",
    )

    conflicted_balance = _balance(
        session,
        facts["balances"][1].id,
    )
    conflicted_before = conflicted_balance.on_hand_quantity
    conflicted_balance.version += 1
    session.commit()

    result = _confirm_execute(
        client,
        internal_auth_headers,
        reviewed,
        preview,
        suffix="CONFIRM-PARTIAL",
    )
    assert result["status"] == "CONFLICTED"

    success_line = next(
        line
        for line in result["lines"]
        if line["balance_id"] == facts["balances"][0].id
    )
    conflict_line = next(
        line
        for line in result["lines"]
        if line["balance_id"] == facts["balances"][1].id
    )
    assert success_line["resolution"] == "ADJUSTED"
    assert success_line["confirmed_transaction_id"] == preview[
        "transaction_id"
    ]
    assert conflict_line["resolution"] == "CONFLICTED"
    assert conflict_line["confirmed_transaction_id"] is None
    assert conflict_line["conflict_details"]["code"] == (
        "STOCKTAKE_VERSION_CONFLICT"
    )

    assert (
        _balance(
            session,
            facts["balances"][0].id,
        ).on_hand_quantity
        == Decimal("9.0000")
    )
    assert (
        _balance(
            session,
            facts["balances"][1].id,
        ).on_hand_quantity
        == conflicted_before
    )
    transaction = _transaction(
        session,
        preview["transaction_id"],
    )
    assert transaction.status == "PARTIALLY_COMPLETED"


def test_partial_confirm_rebase_recount_does_not_repeat_adjusted_line(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="PARTIAL-REBASE",
        quantities=("10.0000", "4.0000"),
    )
    first_preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="PARTIAL-REBASE-1",
    )
    conflict_balance = _balance(
        session,
        facts["balances"][1].id,
    )
    conflict_balance.version += 1
    session.commit()
    partial = _confirm_execute(
        client,
        internal_auth_headers,
        reviewed,
        first_preview,
        suffix="PARTIAL-REBASE-1",
    )
    assert partial["status"] == "CONFLICTED"

    adjusted_line = next(
        line
        for line in partial["lines"]
        if line["resolution"] == "ADJUSTED"
    )
    conflict_line = next(
        line
        for line in partial["lines"]
        if line["resolution"] == "CONFLICTED"
    )
    adjusted_balance_id = adjusted_line["balance_id"]
    adjusted_after_first = _balance(
        session,
        adjusted_balance_id,
    )
    adjusted_quantity = adjusted_after_first.on_hand_quantity
    adjusted_version = adjusted_after_first.version
    first_ledger_count = session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    )

    rebase_request_id = "slice9e-rebase-recount"
    rebase_response = client.post(
        _path_for(
            "rebase",
            stocktake_id=partial["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=rebase_request_id,
            idempotency_key=rebase_request_id,
        ),
        json={
            "expected_version": partial["version"],
            "lines": [
                {
                    "line_id": conflict_line["id"],
                    "action": "RECOUNT",
                }
            ],
        },
    )
    rebased = _assert_success(
        rebase_response,
        request_id=rebase_request_id,
    )
    assert rebased["status"] == "COUNTING"
    adjusted_after_rebase = next(
        line
        for line in rebased["lines"]
        if line["id"] == adjusted_line["id"]
    )
    assert adjusted_after_rebase["resolution"] == "ADJUSTED"

    adjusted_recount_response = client.patch(
        _path_for(
            "update_line",
            stocktake_id=rebased["id"],
            line_id=adjusted_line["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id="slice9e-adjusted-recount",
            idempotency_key="slice9e-adjusted-recount",
        ),
        json={
            "expected_version": rebased["version"],
            "expected_line_version": (
                adjusted_after_rebase["version"]
            ),
            "counted_quantity": "8.0000",
        },
    )
    _assert_error(
        adjusted_recount_response,
        status_code=409,
        code="STOCKTAKE_LINE_ALREADY_CONFIRMED",
        request_id="slice9e-adjusted-recount",
    )

    recount_line = next(
        line
        for line in rebased["lines"]
        if line["id"] == conflict_line["id"]
    )
    current_conflict_balance = _balance(
        session,
        recount_line["balance_id"],
    )
    recounted = _count_line(
        client,
        internal_auth_headers,
        rebased,
        recount_line,
        suffix="PARTIAL-REBASE-2",
        quantity=current_conflict_balance.on_hand_quantity,
    )
    reviewed_again = _review_stocktake(
        client,
        internal_auth_headers,
        recounted,
        suffix="PARTIAL-REBASE-2",
    )
    second_preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed_again,
        suffix="PARTIAL-REBASE-2",
    )
    completed = _confirm_execute(
        client,
        internal_auth_headers,
        reviewed_again,
        second_preview,
        suffix="PARTIAL-REBASE-2",
    )
    assert completed["status"] == "CONFIRMED"

    adjusted_after_second = _balance(
        session,
        adjusted_balance_id,
    )
    assert adjusted_after_second.on_hand_quantity == adjusted_quantity
    assert adjusted_after_second.version == adjusted_version
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == first_ledger_count


def test_baseline_accept_requires_admin(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="BASELINE-ACCEPT",
        quantities=("6.0000",),
    )
    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="BASELINE-ACCEPT",
    )
    balance = _balance(
        session,
        facts["balances"][0].id,
    )
    balance.version += 1
    session.commit()
    partial = _confirm_execute(
        client,
        internal_auth_headers,
        reviewed,
        preview,
        suffix="BASELINE-ACCEPT",
    )
    assert partial["status"] == "CONFLICTED"
    line = partial["lines"][0]

    contributor_response = client.post(
        _path_for(
            "rebase",
            stocktake_id=partial["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id="slice9e-baseline-contributor",
            idempotency_key="slice9e-baseline-contributor",
        ),
        json={
            "expected_version": partial["version"],
            "lines": [
                {
                    "line_id": line["id"],
                    "action": "BASELINE_ACCEPT",
                }
            ],
        },
    )
    assert contributor_response.status_code == 403

    request_id = "slice9e-baseline-admin"
    admin_response = client.post(
        _path_for(
            "rebase",
            stocktake_id=partial["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": partial["version"],
            "lines": [
                {
                    "line_id": line["id"],
                    "action": "BASELINE_ACCEPT",
                }
            ],
        },
    )
    rebased = _assert_success(
        admin_response,
        request_id=request_id,
    )
    assert rebased["status"] == "COUNTING"
    assert rebased["lines"][0]["resolution"] == "BASELINE_ACCEPTED"


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("INVENTORY_CONFIRMATION_TOKEN_INVALID", 422),
        ("INVENTORY_CONFIRMATION_EXPIRED", 422),
        ("INVENTORY_TRANSACTION_VERSION_CONFLICT", 409),
    ],
)
def test_confirm_execute_stable_confirmation_errors(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    code: str,
    status_code: int,
) -> None:
    _, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix=f"CONFIRM-ERROR-{code}",
        quantities=("5.0000",),
    )
    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix=f"CONFIRM-ERROR-{code}",
    )
    transaction = _transaction(
        session,
        preview["transaction_id"],
    )

    token = preview["confirmation_token"]
    expected_transaction_version = preview[
        "transaction_version"
    ]
    if code == "INVENTORY_CONFIRMATION_TOKEN_INVALID":
        token = "definitely-wrong-stocktake-token"
    elif code == "INVENTORY_CONFIRMATION_EXPIRED":
        transaction.confirmation_expires_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        )
        session.commit()
    else:
        transaction.version += 1
        expected_actual_version = transaction.version
        session.commit()

    request_id = f"slice9e-confirm-error-{code}"
    response = client.post(
        _path_for(
            "confirm_execute",
            stocktake_id=reviewed["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "transaction_id": preview["transaction_id"],
            "expected_transaction_version": (
                expected_transaction_version
            ),
            "confirmation_token": token,
        },
    )
    error = _assert_error(
        response,
        status_code=status_code,
        code=code,
        request_id=request_id,
    )
    details = error["details"]
    assert details["retryable"] is False
    if code == "INVENTORY_TRANSACTION_VERSION_CONFLICT":
        assert details["conflict_object"] == (
            "inventory_transaction"
        )
        assert details["expected_version"] == (
            expected_transaction_version
        )
        assert details["actual_version"] == (
            expected_actual_version
        )


def test_confirm_execute_replay_does_not_repeat_adjustment(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, reviewed = _reviewed_stocktake(
        client,
        session,
        internal_auth_headers,
        suffix="CONFIRM-REPLAY",
        quantities=("7.0000",),
    )
    preview = _confirm_preview(
        client,
        internal_auth_headers,
        reviewed,
        suffix="CONFIRM-REPLAY",
    )
    path = _path_for(
        "confirm_execute",
        stocktake_id=reviewed["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9e-confirm-execute-replay",
        idempotency_key="slice9e-confirm-execute-replay",
    )
    payload = {
        "transaction_id": preview["transaction_id"],
        "expected_transaction_version": (
            preview["transaction_version"]
        ),
        "confirmation_token": preview["confirmation_token"],
    }

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9e-confirm-execute-replay",
    )
    balance_id = facts["balances"][0].id
    balance_after_first = _balance(
        session,
        balance_id,
    )
    quantity_after_first = balance_after_first.on_hand_quantity
    version_after_first = balance_after_first.version
    ledger_after_first = session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    )

    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9e-confirm-execute-replay",
    )
    assert replay_data == first_data
    balance_after_replay = _balance(
        session,
        balance_id,
    )
    assert balance_after_replay.on_hand_quantity == quantity_after_first
    assert balance_after_replay.version == version_after_first
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_after_first


def test_stocktake_route_delegates_variance_mutation_and_state_to_service(
) -> None:
    assert STOCKTAKES_ROUTE_FILE.exists(), (
        "Task 9 Slice 9E requires "
        "app/api/v1/inventory/stocktakes.py"
    )

    source = STOCKTAKES_ROUTE_FILE.read_text(
        encoding="utf-8",
    )
    tree = ast.parse(
        source,
        filename=str(STOCKTAKES_ROUTE_FILE),
    )
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "InventoryStocktakeService" in imported_names
    assert "InventoryMutationPlan" not in imported_names
    assert "InventoryBalanceMutation" not in imported_names
    assert "InventoryLedgerRepository" not in imported_names
    assert "InventoryTransactionService" not in imported_names
    assert "InventoryStocktakeRepository" not in imported_names
    assert all(
        not module.startswith("sqlalchemy")
        for module in imported_modules
    )

    forbidden_calls = {
        "apply_plan",
        "apply_plan_to_transaction",
        "complete_preview_without_mutations",
        "_confirm_plan",
        "_rebase_command",
        "_execute_confirm_command",
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }
    assert forbidden_calls.isdisjoint(called)

    forbidden_assignment_attrs = {
        "status",
        "on_hand_quantity",
        "variance_quantity",
        "resolution",
        "confirmed_transaction_id",
        "conflict_details_json",
    }
    assigned_attrs: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        elif isinstance(node, ast.AugAssign):
            targets.append(node.target)

        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Attribute):
                    assigned_attrs.add(child.attr)

    assert forbidden_assignment_attrs.isdisjoint(
        assigned_attrs
    )
