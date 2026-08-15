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
    InventoryTransaction,
    InventoryTransfer,
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
        "/api/v1/inventory/transfers",
    ),
    "dispatch_preview": (
        "post",
        "/api/v1/inventory/transfers/{transfer_id}/dispatch/preview",
    ),
    "dispatch_execute": (
        "post",
        "/api/v1/inventory/transfers/{transfer_id}/dispatch/execute",
    ),
    "receive_preview": (
        "post",
        "/api/v1/inventory/transfers/{transfer_id}/receive/preview",
    ),
    "receive_execute": (
        "post",
        "/api/v1/inventory/transfers/{transfer_id}/receive/execute",
    ),
    "cancel": (
        "post",
        "/api/v1/inventory/transfers/{transfer_id}/cancel",
    ),
}
EXPECTED_OPENAPI_OPERATIONS = {
    (method, path)
    for method, path in WRITE_ROUTES.values()
}
TRANSFERS_ROUTE_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "inventory"
    / "transfers.py"
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
    transfer_id: int = 1,
) -> str:
    _, template = WRITE_ROUTES[operation]
    return template.format(transfer_id=transfer_id)


def _minimal_create_payload() -> dict[str, Any]:
    return {
        "source_warehouse_id": 1,
        "source_location_id": 1,
        "target_warehouse_id": 1,
        "target_location_id": 2,
        "reference_type": "work_order",
        "reference_id": "WO-SLICE9D",
        "reason": "slice9d transfer",
        "lines": [
            {
                "spare_part_id": 1,
                "source_balance_id": 1,
                "lot_id": None,
                "serial_item_id": None,
                "quantity": "2.0000",
                "expected_source_version": 1,
            }
        ],
    }


def _payload_for_route(operation: str) -> dict[str, Any]:
    if operation == "create":
        return _minimal_create_payload()
    if operation in {"dispatch_preview", "cancel"}:
        return {"expected_version": 1}
    if operation in {
        "dispatch_execute",
        "receive_execute",
    }:
        return {
            "transaction_id": 1,
            "expected_transaction_version": 1,
            "confirmation_token": "slice9d-token",
        }
    if operation == "receive_preview":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "transfer_line_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }
    raise AssertionError(f"unsupported route: {operation}")


def _seed_inventory(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
    on_hand: str = "10.0000",
) -> dict[str, Any]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-API-TR-{suffix}",
        name=f"Transfer API Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-API-TR-{suffix}",
        name=f"Transfer API Spare {suffix}",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, part])
    session.flush()

    source_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"SRC-API-TR-{suffix}",
        name=f"Transfer Source {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    target_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"DST-API-TR-{suffix}",
        name=f"Transfer Target {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add_all([source_location, target_location])
    session.flush()

    source = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=source_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(source)
    session.commit()

    return {
        "warehouse": warehouse,
        "part": part,
        "source_location": source_location,
        "target_location": target_location,
        "source": source,
    }


def _create_payload(
    facts: dict[str, Any],
    *,
    quantity: str = "2.0000",
    reason: str = "move stock to destination",
) -> dict[str, Any]:
    source = facts["source"]
    return {
        "source_warehouse_id": facts["warehouse"].id,
        "source_location_id": facts["source_location"].id,
        "target_warehouse_id": facts["warehouse"].id,
        "target_location_id": facts["target_location"].id,
        "reference_type": "work_order",
        "reference_id": "WO-TRANSFER-API",
        "reason": reason,
        "lines": [
            {
                "spare_part_id": facts["part"].id,
                "source_balance_id": source.id,
                "lot_id": source.lot_id,
                "serial_item_id": None,
                "quantity": quantity,
                "expected_source_version": source.version,
            }
        ],
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
    assert isinstance(error, dict), (
        "expected maintenance error object, "
        f"got: {payload}"
    )
    assert error.get("code") == code
    if request_id is not None:
        assert error.get("request_id") == request_id
    return error


def _create_transfer(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    suffix: str,
    tenant_id: str = "tenant-a",
    quantity: str = "2.0000",
) -> tuple[dict[str, Any], dict[str, Any]]:
    facts = _seed_inventory(
        session,
        tenant_id=tenant_id,
        suffix=suffix,
    )
    request_id = f"slice9d-create-{suffix}"
    response = client.post(
        "/api/v1/inventory/transfers",
        headers=_headers(
            internal_auth_headers,
            tenant_id=tenant_id,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json=_create_payload(
            facts,
            quantity=quantity,
        ),
    )
    transfer = _assert_success(
        response,
        request_id=request_id,
        tenant_id=tenant_id,
    )
    assert transfer["status"] == "DRAFT"
    return facts, transfer


def _dispatch_preview(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    transfer: dict[str, Any],
    *,
    suffix: str,
    tenant_id: str = "tenant-a",
) -> dict[str, Any]:
    request_id = f"slice9d-dispatch-preview-{suffix}"
    response = client.post(
        _path_for(
            "dispatch_preview",
            transfer_id=transfer["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            tenant_id=tenant_id,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": transfer["version"],
        },
    )
    return _assert_success(
        response,
        request_id=request_id,
        tenant_id=tenant_id,
    )


def _dispatch_execute(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    transfer: dict[str, Any],
    preview: dict[str, Any],
    *,
    suffix: str,
    tenant_id: str = "tenant-a",
) -> dict[str, Any]:
    request_id = f"slice9d-dispatch-execute-{suffix}"
    response = client.post(
        _path_for(
            "dispatch_execute",
            transfer_id=transfer["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            tenant_id=tenant_id,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "transaction_id": preview["transaction_id"],
            "expected_transaction_version": (
                preview["transaction_version"]
            ),
            "confirmation_token": preview["confirmation_token"],
        },
    )
    return _assert_success(
        response,
        request_id=request_id,
        tenant_id=tenant_id,
    )


def _dispatch_transfer(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    suffix: str,
    quantity: str = "2.0000",
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix=suffix,
        quantity=quantity,
    )
    preview = _dispatch_preview(
        client,
        internal_auth_headers,
        transfer,
        suffix=suffix,
    )
    dispatched = _dispatch_execute(
        client,
        internal_auth_headers,
        transfer,
        preview,
        suffix=suffix,
    )
    assert dispatched["status"] == "DISPATCHED"
    return facts, dispatched, preview


def _receive_preview(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    transfer: dict[str, Any],
    *,
    suffix: str,
    quantity: str,
) -> dict[str, Any]:
    request_id = f"slice9d-receive-preview-{suffix}"
    response = client.post(
        _path_for(
            "receive_preview",
            transfer_id=transfer["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": transfer["version"],
            "lines": [
                {
                    "transfer_line_id": transfer["lines"][0]["id"],
                    "quantity": quantity,
                }
            ],
        },
    )
    return _assert_success(
        response,
        request_id=request_id,
    )


def _receive_execute(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    transfer: dict[str, Any],
    preview: dict[str, Any],
    *,
    suffix: str,
) -> dict[str, Any]:
    request_id = f"slice9d-receive-execute-{suffix}"
    response = client.post(
        _path_for(
            "receive_execute",
            transfer_id=transfer["id"],
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
                preview["transaction_version"]
            ),
            "confirmation_token": preview["confirmation_token"],
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


def test_inventory_transfer_write_routes_are_registered(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    missing = sorted(
        f"{method.upper()} {path}"
        for method, path in EXPECTED_OPENAPI_OPERATIONS
        if method not in openapi_paths.get(path, {})
    )
    assert missing == [], (
        "Task 9 Slice 9D missing transfer write routes: "
        f"{missing}"
    )


def test_inventory_transfer_routes_require_authentication(
    client: TestClient,
) -> None:
    failures: list[tuple[str, int]] = []
    for operation in WRITE_ROUTES:
        response = client.post(
            _path_for(operation),
            headers={
                "Idempotency-Key": f"slice9d-unauth-{operation}",
            },
            json=_payload_for_route(operation),
        )
        if response.status_code != 401:
            failures.append(
                (operation, response.status_code)
            )
    assert failures == []


def test_inventory_transfer_routes_reject_viewer(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int]] = []
    for operation in WRITE_ROUTES:
        response = client.post(
            _path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.VIEWER,
                request_id=f"slice9d-viewer-{operation}",
                idempotency_key=f"slice9d-viewer-{operation}",
            ),
            json=_payload_for_route(operation),
        )
        if response.status_code != 403:
            failures.append(
                (operation, response.status_code)
            )
    assert failures == []


def test_inventory_transfer_routes_reject_contributor(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int]] = []
    for operation in WRITE_ROUTES:
        response = client.post(
            _path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.CONTRIBUTOR,
                request_id=f"slice9d-contributor-{operation}",
                idempotency_key=f"slice9d-contributor-{operation}",
            ),
            json=_payload_for_route(operation),
        )
        if response.status_code != 403:
            failures.append(
                (operation, response.status_code)
            )
    assert failures == []


def test_all_transfer_writes_require_idempotency_key(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int, str | None]] = []
    for operation in WRITE_ROUTES:
        request_id = f"slice9d-missing-key-{operation}"
        response = client.post(
            _path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.ADMIN,
                request_id=request_id,
            ),
            json=_payload_for_route(operation),
        )
        if response.status_code != 422:
            failures.append(
                (operation, response.status_code, None)
            )
            continue
        error = response.json().get("error", {})
        if (
            error.get("code") != "IDEMPOTENCY_KEY_REQUIRED"
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


def test_transfer_writes_reject_tenant_id_query_or_body(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, str, int]] = []
    for operation in WRITE_ROUTES:
        path = _path_for(operation)
        headers = _headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=f"slice9d-tenant-{operation}",
            idempotency_key=f"slice9d-tenant-{operation}",
        )
        payload = _payload_for_route(operation)

        query_response = client.post(
            path,
            params={"tenant_id": "tenant-b"},
            headers=headers,
            json=payload,
        )
        if query_response.status_code != 422:
            failures.append(
                (operation, "query", query_response.status_code)
            )

        body_response = client.post(
            path,
            headers=headers,
            json={
                **payload,
                "tenant_id": "tenant-b",
            },
        )
        if body_response.status_code != 422:
            failures.append(
                (operation, "body", body_response.status_code)
            )
    assert failures == []


def test_admin_can_create_draft_transfer(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="CREATE",
    )
    assert transfer["status"] == "DRAFT"
    assert transfer["version"] == 1
    assert len(transfer["lines"]) == 1
    line = transfer["lines"][0]
    assert line["source_balance_id"] == facts["source"].id
    assert line["target_balance_id"] > 0
    assert line["requested_quantity"] == "2.0000"
    assert line["dispatched_quantity"] == "0.0000"
    assert line["received_quantity"] == "0.0000"

    source = _balance(session, facts["source"].id)
    target = _balance(session, line["target_balance_id"])
    assert source.on_hand_quantity == Decimal("10.0000")
    assert target.on_hand_quantity == Decimal("0.0000")
    assert target.in_transit_quantity == Decimal("0.0000")


def test_create_transfer_idempotent_replay_has_one_transfer(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REPLAY",
    )
    payload = _create_payload(facts)
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-create-replay",
        idempotency_key="slice9d-create-replay",
    )

    first = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9d-create-replay",
    )
    replay = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9d-create-replay",
    )

    assert replay_data == first_data
    session.expire_all()
    assert session.scalar(
        select(func.count(InventoryTransfer.id))
    ) == 1


def test_create_transfer_reused_key_changed_payload_is_conflict(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REUSED",
    )
    payload = _create_payload(facts)
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-create-reused",
        idempotency_key="slice9d-create-reused",
    )
    first = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json=payload,
    )
    _assert_success(
        first,
        request_id="slice9d-create-reused",
    )

    conflict = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            **payload,
            "reason": "changed transfer command",
        },
    )
    error = _assert_error(
        conflict,
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        request_id="slice9d-create-reused",
    )
    assert error["details"]["retryable"] is False


def test_create_transfer_hides_cross_tenant_source(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    local = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="LOCAL",
    )
    foreign = _seed_inventory(
        session,
        tenant_id="tenant-b",
        suffix="FOREIGN",
    )
    payload = _create_payload(local)
    payload["lines"][0]["source_balance_id"] = foreign["source"].id
    payload["lines"][0]["spare_part_id"] = foreign["part"].id

    response = client.post(
        "/api/v1/inventory/transfers",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9d-create-cross-tenant",
            idempotency_key="slice9d-create-cross-tenant",
        ),
        json=payload,
    )
    _assert_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        request_id="slice9d-create-cross-tenant",
    )


def test_dispatch_preview_is_previewed_and_has_no_quantity_side_effects(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="DISPATCH-PREVIEW",
    )
    line = transfer["lines"][0]
    source_before = _balance(
        session,
        facts["source"].id,
    ).on_hand_quantity
    target_before = _balance(
        session,
        line["target_balance_id"],
    ).in_transit_quantity

    preview = _dispatch_preview(
        client,
        internal_auth_headers,
        transfer,
        suffix="DISPATCH-PREVIEW",
    )
    assert preview["status"] == "PREVIEWED"
    assert preview["operation_type"] == "TRANSFER_DISPATCH"
    assert preview["confirmation_token"]
    assert preview["transaction_version"] > 0
    assert "_extensions" not in preview

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
    assert (
        _balance(session, facts["source"].id).on_hand_quantity
        == source_before
    )
    assert (
        _balance(
            session,
            line["target_balance_id"],
        ).in_transit_quantity
        == target_before
    )


def test_dispatch_preview_replay_returns_plaintext_token_only_once(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="DISPATCH-PREVIEW-REPLAY",
    )
    path = _path_for(
        "dispatch_preview",
        transfer_id=transfer["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-dispatch-preview-replay",
        idempotency_key="slice9d-dispatch-preview-replay",
    )
    payload = {"expected_version": transfer["version"]}

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9d-dispatch-preview-replay",
    )
    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9d-dispatch-preview-replay",
    )
    assert first_data["confirmation_token"]
    assert replay_data["confirmation_token"] is None
    assert (
        replay_data["transaction_id"]
        == first_data["transaction_id"]
    )


def test_dispatch_execute_moves_quantity_to_in_transit(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="DISPATCH-EXECUTE",
    )
    preview = _dispatch_preview(
        client,
        internal_auth_headers,
        transfer,
        suffix="DISPATCH-EXECUTE",
    )
    dispatched = _dispatch_execute(
        client,
        internal_auth_headers,
        transfer,
        preview,
        suffix="DISPATCH-EXECUTE",
    )
    assert dispatched["status"] == "DISPATCHED"
    line = dispatched["lines"][0]
    assert line["dispatched_quantity"] == "2.0000"

    source = _balance(session, facts["source"].id)
    target = _balance(session, line["target_balance_id"])
    assert source.on_hand_quantity == Decimal("8.0000")
    assert target.on_hand_quantity == Decimal("0.0000")
    assert target.in_transit_quantity == Decimal("2.0000")


def test_dispatch_execute_replay_does_not_move_quantity_twice(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="DISPATCH-EXECUTE-REPLAY",
    )
    preview = _dispatch_preview(
        client,
        internal_auth_headers,
        transfer,
        suffix="DISPATCH-EXECUTE-REPLAY",
    )
    path = _path_for(
        "dispatch_execute",
        transfer_id=transfer["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-dispatch-execute-replay",
        idempotency_key="slice9d-dispatch-execute-replay",
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
        request_id="slice9d-dispatch-execute-replay",
    )
    source_after_first = _balance(
        session,
        facts["source"].id,
    ).on_hand_quantity
    target_id = first_data["lines"][0]["target_balance_id"]
    transit_after_first = _balance(
        session,
        target_id,
    ).in_transit_quantity
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
        request_id="slice9d-dispatch-execute-replay",
    )
    assert replay_data == first_data
    assert (
        _balance(
            session,
            facts["source"].id,
        ).on_hand_quantity
        == source_after_first
    )
    assert (
        _balance(session, target_id).in_transit_quantity
        == transit_after_first
    )
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_after_first


def _preview_for_error(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    phase: str,
    suffix: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if phase == "dispatch":
        _, transfer = _create_transfer(
            client,
            session,
            internal_auth_headers,
            suffix=f"{suffix}-DISPATCH",
        )
        preview = _dispatch_preview(
            client,
            internal_auth_headers,
            transfer,
            suffix=f"{suffix}-DISPATCH",
        )
        return transfer, preview

    assert phase == "receive"
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix=f"{suffix}-RECEIVE",
    )
    preview = _receive_preview(
        client,
        internal_auth_headers,
        dispatched,
        suffix=f"{suffix}-RECEIVE",
        quantity="1.0000",
    )
    return dispatched, preview


@pytest.mark.parametrize(
    "phase",
    ["dispatch", "receive"],
)
def test_execute_invalid_confirmation_token_is_stable(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    phase: str,
) -> None:
    transfer, preview = _preview_for_error(
        client,
        session,
        internal_auth_headers,
        phase=phase,
        suffix="TOKEN-INVALID",
    )
    operation = (
        "dispatch_execute"
        if phase == "dispatch"
        else "receive_execute"
    )
    request_id = f"slice9d-{phase}-token-invalid"
    response = client.post(
        _path_for(
            operation,
            transfer_id=transfer["id"],
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
                preview["transaction_version"]
            ),
            "confirmation_token": "definitely-wrong-token",
        },
    )
    error = _assert_error(
        response,
        status_code=409,
        code="INVENTORY_CONFIRMATION_TOKEN_INVALID",
        request_id=request_id,
    )
    assert error["details"]["retryable"] is False


@pytest.mark.parametrize(
    "phase",
    ["dispatch", "receive"],
)
def test_execute_expired_confirmation_is_stable(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    phase: str,
) -> None:
    transfer, preview = _preview_for_error(
        client,
        session,
        internal_auth_headers,
        phase=phase,
        suffix="TOKEN-EXPIRED",
    )
    stored = _transaction(
        session,
        preview["transaction_id"],
    )
    stored.confirmation_expires_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )
    session.commit()

    operation = (
        "dispatch_execute"
        if phase == "dispatch"
        else "receive_execute"
    )
    request_id = f"slice9d-{phase}-token-expired"
    response = client.post(
        _path_for(
            operation,
            transfer_id=transfer["id"],
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
                preview["transaction_version"]
            ),
            "confirmation_token": preview["confirmation_token"],
        },
    )
    error = _assert_error(
        response,
        status_code=409,
        code="INVENTORY_CONFIRMATION_EXPIRED",
        request_id=request_id,
    )
    assert error["details"]["retryable"] is False


@pytest.mark.parametrize(
    "phase",
    ["dispatch", "receive"],
)
def test_execute_transaction_version_conflict_is_stable(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    phase: str,
) -> None:
    transfer, preview = _preview_for_error(
        client,
        session,
        internal_auth_headers,
        phase=phase,
        suffix="TX-VERSION",
    )
    stored = _transaction(
        session,
        preview["transaction_id"],
    )
    stored.version += 1
    actual_version = stored.version
    session.commit()

    operation = (
        "dispatch_execute"
        if phase == "dispatch"
        else "receive_execute"
    )
    request_id = f"slice9d-{phase}-tx-version"
    response = client.post(
        _path_for(
            operation,
            transfer_id=transfer["id"],
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
                preview["transaction_version"]
            ),
            "confirmation_token": preview["confirmation_token"],
        },
    )
    error = _assert_error(
        response,
        status_code=409,
        code="INVENTORY_TRANSACTION_VERSION_CONFLICT",
        request_id=request_id,
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_transaction"
    assert details["expected_version"] == preview[
        "transaction_version"
    ]
    assert details["actual_version"] == actual_version
    assert details["retryable"] is False


def test_receive_preview_is_previewed_without_quantity_change(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="RECEIVE-PREVIEW",
    )
    line = dispatched["lines"][0]
    source_before = _balance(
        session,
        facts["source"].id,
    ).on_hand_quantity
    target_before = _balance(
        session,
        line["target_balance_id"],
    )
    on_hand_before = target_before.on_hand_quantity
    transit_before = target_before.in_transit_quantity

    preview = _receive_preview(
        client,
        internal_auth_headers,
        dispatched,
        suffix="RECEIVE-PREVIEW",
        quantity="1.5000",
    )
    assert preview["status"] == "PREVIEWED"
    assert preview["operation_type"] == "TRANSFER_RECEIVE"
    assert preview["confirmation_token"]

    assert (
        _balance(
            session,
            facts["source"].id,
        ).on_hand_quantity
        == source_before
    )
    target_after = _balance(
        session,
        line["target_balance_id"],
    )
    assert target_after.on_hand_quantity == on_hand_before
    assert target_after.in_transit_quantity == transit_before


def test_receive_preview_replay_returns_plaintext_token_only_once(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="RECEIVE-PREVIEW-REPLAY",
    )
    path = _path_for(
        "receive_preview",
        transfer_id=dispatched["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-receive-preview-replay",
        idempotency_key="slice9d-receive-preview-replay",
    )
    payload = {
        "expected_version": dispatched["version"],
        "lines": [
            {
                "transfer_line_id": dispatched["lines"][0]["id"],
                "quantity": "1.0000",
            }
        ],
    }

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9d-receive-preview-replay",
    )
    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9d-receive-preview-replay",
    )
    assert first_data["confirmation_token"]
    assert replay_data["confirmation_token"] is None
    assert (
        replay_data["transaction_id"]
        == first_data["transaction_id"]
    )


def test_receive_execute_supports_partial_receipt(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="RECEIVE-PARTIAL",
    )
    preview = _receive_preview(
        client,
        internal_auth_headers,
        dispatched,
        suffix="RECEIVE-PARTIAL",
        quantity="1.5000",
    )
    partial = _receive_execute(
        client,
        internal_auth_headers,
        dispatched,
        preview,
        suffix="RECEIVE-PARTIAL",
    )

    assert partial["status"] == "PARTIALLY_RECEIVED"
    line = partial["lines"][0]
    assert line["received_quantity"] == "1.5000"
    target = _balance(session, line["target_balance_id"])
    assert target.on_hand_quantity == Decimal("1.5000")
    assert target.in_transit_quantity == Decimal("0.5000")


def test_receive_execute_replay_does_not_receive_twice(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="RECEIVE-EXECUTE-REPLAY",
    )
    preview = _receive_preview(
        client,
        internal_auth_headers,
        dispatched,
        suffix="RECEIVE-EXECUTE-REPLAY",
        quantity="1.0000",
    )
    path = _path_for(
        "receive_execute",
        transfer_id=dispatched["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-receive-execute-replay",
        idempotency_key="slice9d-receive-execute-replay",
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
        request_id="slice9d-receive-execute-replay",
    )
    target_id = first_data["lines"][0]["target_balance_id"]
    target_after_first = _balance(session, target_id)
    on_hand_after_first = target_after_first.on_hand_quantity
    transit_after_first = target_after_first.in_transit_quantity
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
        request_id="slice9d-receive-execute-replay",
    )
    assert replay_data == first_data
    target_after_replay = _balance(session, target_id)
    assert target_after_replay.on_hand_quantity == on_hand_after_first
    assert (
        target_after_replay.in_transit_quantity
        == transit_after_first
    )
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_after_first


def test_second_receive_completes_transfer(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="RECEIVE-COMPLETE",
    )
    first_preview = _receive_preview(
        client,
        internal_auth_headers,
        dispatched,
        suffix="RECEIVE-COMPLETE-1",
        quantity="1.5000",
    )
    partial = _receive_execute(
        client,
        internal_auth_headers,
        dispatched,
        first_preview,
        suffix="RECEIVE-COMPLETE-1",
    )
    assert partial["status"] == "PARTIALLY_RECEIVED"

    second_preview = _receive_preview(
        client,
        internal_auth_headers,
        partial,
        suffix="RECEIVE-COMPLETE-2",
        quantity="0.5000",
    )
    completed = _receive_execute(
        client,
        internal_auth_headers,
        partial,
        second_preview,
        suffix="RECEIVE-COMPLETE-2",
    )
    assert completed["status"] == "COMPLETED"
    line = completed["lines"][0]
    assert line["received_quantity"] == "2.0000"
    target = _balance(session, line["target_balance_id"])
    assert target.on_hand_quantity == Decimal("2.0000")
    assert target.in_transit_quantity == Decimal("0.0000")


def test_receive_preview_rejects_over_receipt(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="OVER-RECEIPT",
    )
    request_id = "slice9d-over-receipt"
    response = client.post(
        _path_for(
            "receive_preview",
            transfer_id=dispatched["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={
            "expected_version": dispatched["version"],
            "lines": [
                {
                    "transfer_line_id": dispatched["lines"][0]["id"],
                    "quantity": "3.0000",
                }
            ],
        },
    )
    error = _assert_error(
        response,
        status_code=409,
        code="TRANSFER_RECEIPT_EXCEEDS_DISPATCH",
        request_id=request_id,
    )
    assert error["details"]["retryable"] is False


def test_admin_can_cancel_draft_without_inventory_mutation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    facts, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="CANCEL",
    )
    line = transfer["lines"][0]
    source_before = _balance(
        session,
        facts["source"].id,
    ).on_hand_quantity
    target_before = _balance(
        session,
        line["target_balance_id"],
    )
    target_on_hand_before = target_before.on_hand_quantity
    transit_before = target_before.in_transit_quantity
    ledger_before = session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    )

    request_id = "slice9d-cancel"
    response = client.post(
        _path_for(
            "cancel",
            transfer_id=transfer["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": transfer["version"]},
    )
    cancelled = _assert_success(
        response,
        request_id=request_id,
    )
    assert cancelled["status"] == "CANCELLED"
    assert (
        _balance(
            session,
            facts["source"].id,
        ).on_hand_quantity
        == source_before
    )
    target_after = _balance(
        session,
        line["target_balance_id"],
    )
    assert target_after.on_hand_quantity == target_on_hand_before
    assert target_after.in_transit_quantity == transit_before
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_before


def test_cancel_replay_returns_same_cancelled_snapshot(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="CANCEL-REPLAY",
    )
    path = _path_for(
        "cancel",
        transfer_id=transfer["id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9d-cancel-replay",
        idempotency_key="slice9d-cancel-replay",
    )
    payload = {"expected_version": transfer["version"]}

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9d-cancel-replay",
    )
    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9d-cancel-replay",
    )
    assert replay_data == first_data
    assert replay_data["status"] == "CANCELLED"


def test_cancel_after_dispatch_is_transfer_state_conflict(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, dispatched, _ = _dispatch_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="CANCEL-STATE",
    )
    request_id = "slice9d-cancel-state"
    response = client.post(
        _path_for(
            "cancel",
            transfer_id=dispatched["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": dispatched["version"]},
    )
    error = _assert_error(
        response,
        status_code=409,
        code="TRANSFER_STATE_CONFLICT",
        request_id=request_id,
    )
    assert error["details"]["retryable"] is False


def test_cross_tenant_transfer_is_hidden(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, transfer = _create_transfer(
        client,
        session,
        internal_auth_headers,
        suffix="CROSS-TENANT",
        tenant_id="tenant-a",
    )
    request_id = "slice9d-cross-tenant"
    response = client.post(
        _path_for(
            "dispatch_preview",
            transfer_id=transfer["id"],
        ),
        headers=_headers(
            internal_auth_headers,
            tenant_id="tenant-b",
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json={"expected_version": transfer["version"]},
    )
    _assert_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        request_id=request_id,
    )


def test_transfer_route_delegates_mutation_and_state_to_service(
) -> None:
    assert TRANSFERS_ROUTE_FILE.exists(), (
        "Task 9 Slice 9D requires "
        "app/api/v1/inventory/transfers.py"
    )

    source = TRANSFERS_ROUTE_FILE.read_text(
        encoding="utf-8",
    )
    tree = ast.parse(
        source,
        filename=str(TRANSFERS_ROUTE_FILE),
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

    assert "InventoryTransferService" in imported_names
    assert "InventoryMutationPlan" not in imported_names
    assert "InventoryBalanceMutation" not in imported_names
    assert "InventoryLedgerRepository" not in imported_names
    assert "InventoryTransactionService" not in imported_names
    assert "InventoryTransferRepository" not in imported_names
    assert all(
        not module.startswith("sqlalchemy")
        for module in imported_modules
    )

    forbidden_calls = {
        "apply_plan",
        "apply_plan_to_transaction",
        "_dispatch_plan",
        "_receive_plan",
        "_dispatch_state",
        "_receive_state",
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
        "in_transit_quantity",
        "dispatched_quantity",
        "received_quantity",
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
