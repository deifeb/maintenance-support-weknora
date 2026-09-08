from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from app.core.exceptions import BusinessValidationError
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_operation_service import (
    InventoryOperationService,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

WRITE_ROUTES = {
    "preview": (
        "post",
        "/api/v1/inventory/operations/preview",
    ),
    "execute": (
        "post",
        "/api/v1/inventory/operations/{transaction_id}/execute",
    ),
    "reverse_preview": (
        "post",
        "/api/v1/inventory/operations/{transaction_id}/reverse/preview",
    ),
    "reverse_execute": (
        "post",
        "/api/v1/inventory/operations/{transaction_id}/reverse/execute",
    ),
}
EXPECTED_OPENAPI_OPERATIONS = {
    (method, path)
    for method, path in WRITE_ROUTES.values()
}
OPERATIONS_ROUTE_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "inventory"
    / "operations.py"
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
    transaction_id: int = 1,
) -> str:
    _, template = WRITE_ROUTES[operation]
    return template.format(transaction_id=transaction_id)


def _minimal_preview_payload(
    operation_type: str = "ADJUST",
) -> dict[str, Any]:
    if operation_type == "ADJUST":
        return {
            "operation_type": "ADJUST",
            "balance_id": 1,
            "expected_balance_version": 1,
            "reason": "slice9c adjustment",
            "deltas": {
                "on_hand": "1.0000",
                "reserved": "0.0000",
                "damaged": "0.0000",
                "quarantined": "0.0000",
                "in_transit": "0.0000",
            },
        }
    if operation_type in {"FREEZE", "UNFREEZE"}:
        return {
            "operation_type": operation_type,
            "balance_id": 1,
            "expected_balance_version": 1,
            "lot_id": 1,
            "expected_lot_version": 1,
            "reason": f"slice9c {operation_type.lower()}",
        }
    raise AssertionError(
        f"unsupported operation type: {operation_type}"
    )


def _minimal_execute_payload() -> dict[str, Any]:
    return {
        "expected_transaction_version": 1,
        "confirmation_token": "slice9c-token",
    }


def _minimal_reverse_preview_payload() -> dict[str, Any]:
    return {
        "expected_transaction_version": 1,
        "reason": "slice9c reverse",
    }


def _payload_for_route(operation: str) -> dict[str, Any]:
    if operation == "preview":
        return _minimal_preview_payload()
    if operation in {"execute", "reverse_execute"}:
        return _minimal_execute_payload()
    if operation == "reverse_preview":
        return _minimal_reverse_preview_payload()
    raise AssertionError(f"unsupported route: {operation}")


def _seed_inventory(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
    frozen: bool = False,
) -> tuple[InventoryBalance, InventoryLot]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-API-OP-{suffix}",
        name=f"Operation API Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-API-OP-{suffix}",
        name=f"Operation API Spare {suffix}",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-API-OP-{suffix}",
        name=f"Operation API Location {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    lot = InventoryLot(
        tenant_id=tenant_id,
        spare_part_id=spare_part.id,
        lot_code=f"LOT-API-OP-{suffix}",
        received_date=date(2026, 8, 1),
        expiry_date=date(2026, 12, 31),
        quality_status="AVAILABLE",
        is_frozen=frozen,
        freeze_reason=(
            "pre-existing hold"
            if frozen
            else None
        ),
    )
    session.add_all([location, lot])
    session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_part.id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("5.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.commit()
    return balance, lot


def _preview_payload(
    operation_type: str,
    balance: InventoryBalance,
    lot: InventoryLot,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    if operation_type == "ADJUST":
        return {
            "operation_type": "ADJUST",
            "balance_id": balance.id,
            "expected_balance_version": balance.version,
            "reason": reason or "cycle correction",
            "deltas": {
                "on_hand": "1.0000",
                "reserved": "0.0000",
                "damaged": "0.0000",
                "quarantined": "0.0000",
                "in_transit": "0.0000",
            },
        }

    assert operation_type in {"FREEZE", "UNFREEZE"}
    return {
        "operation_type": operation_type,
        "balance_id": balance.id,
        "expected_balance_version": balance.version,
        "lot_id": lot.id,
        "expected_lot_version": lot.version,
        "reason": (
            reason
            or (
                "quality hold"
                if operation_type == "FREEZE"
                else "release quality hold"
            )
        ),
    }


def _execute_payload(
    preview: dict[str, Any],
    *,
    confirmation_token: str | None = None,
    expected_transaction_version: int | None = None,
) -> dict[str, Any]:
    token = (
        preview["confirmation_token"]
        if confirmation_token is None
        else confirmation_token
    )
    version = (
        preview["transaction_version"]
        if expected_transaction_version is None
        else expected_transaction_version
    )
    assert isinstance(token, str)
    assert token
    return {
        "expected_transaction_version": version,
        "confirmation_token": token,
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


def _seed_completed_adjust(
    session: Session,
    actor_context: Callable[..., ActorContext],
    *,
    suffix: str,
) -> tuple[
    InventoryBalance,
    InventoryLot,
    Any,
]:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix=suffix,
    )
    actor = actor_context(
        tenant_id="tenant-a",
        user_id=f"seed-admin-{suffix}",
        role=MaintenanceRole.ADMIN,
        request_id=f"seed-operation-{suffix}",
        token_id=f"seed-operation-token-{suffix}",
    )
    service = InventoryOperationService()
    preview = service.preview(
        session,
        actor,
        command=_preview_payload(
            "ADJUST",
            balance,
            lot,
            reason=f"seed adjust {suffix}",
        ),
        idempotency_key=f"seed-adjust-preview-{suffix}",
    )
    assert preview.confirmation_token
    completed = service.execute(
        session,
        actor,
        preview.transaction_id,
        command={
            "expected_transaction_version": (
                preview.transaction_version
            ),
            "confirmation_token": (
                preview.confirmation_token
            ),
        },
        idempotency_key=f"seed-adjust-execute-{suffix}",
    )
    session.commit()
    return balance, lot, completed


def test_inventory_operation_write_routes_are_registered(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    missing = sorted(
        f"{method.upper()} {path}"
        for method, path in EXPECTED_OPENAPI_OPERATIONS
        if method not in openapi_paths.get(path, {})
    )

    assert missing == [], (
        "Task 9 Slice 9C missing operation write routes: "
        f"{missing}"
    )


def test_inventory_operation_routes_require_authentication(
    client: TestClient,
) -> None:
    failures: list[tuple[str, int]] = []

    for operation in WRITE_ROUTES:
        response = client.post(
            _path_for(operation),
            headers={
                "Idempotency-Key": (
                    f"slice9c-unauth-{operation}"
                )
            },
            json=_payload_for_route(operation),
        )
        if response.status_code != 401:
            failures.append(
                (operation, response.status_code)
            )

    assert failures == []


def test_inventory_operation_routes_reject_viewer(
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
                request_id=f"slice9c-viewer-{operation}",
                idempotency_key=f"slice9c-viewer-{operation}",
            ),
            json=_payload_for_route(operation),
        )
        if response.status_code != 403:
            failures.append(
                (operation, response.status_code)
            )

    assert failures == []


@pytest.mark.parametrize(
    "operation_type",
    [
        "ADJUST",
        "FREEZE",
        "UNFREEZE",
    ],
)
def test_direct_high_risk_preview_rejects_contributor(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    operation_type: str,
) -> None:
    response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=(
                f"slice9c-contributor-{operation_type}"
            ),
            idempotency_key=(
                f"slice9c-contributor-{operation_type}"
            ),
        ),
        json=_minimal_preview_payload(operation_type),
    )

    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "operation",
    [
        "reverse_preview",
        "reverse_execute",
    ],
)
def test_reverse_routes_reject_contributor(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    operation: str,
) -> None:
    response = client.post(
        _path_for(operation),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=f"slice9c-contributor-{operation}",
            idempotency_key=f"slice9c-contributor-{operation}",
        ),
        json=_payload_for_route(operation),
    )

    assert response.status_code == 403, response.text


def test_all_operation_writes_require_idempotency_key(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int, str | None]] = []

    for operation in WRITE_ROUTES:
        request_id = f"slice9c-missing-key-{operation}"
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

        payload = response.json()
        error = payload.get("error", {})
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


def test_operation_writes_reject_tenant_id_query_or_body(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, str, int]] = []

    for operation in WRITE_ROUTES:
        path = _path_for(operation)
        headers = _headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=f"slice9c-tenant-{operation}",
            idempotency_key=f"slice9c-tenant-{operation}",
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


@pytest.mark.parametrize(
    "operation_type",
    [
        "ADJUST",
        "FREEZE",
        "UNFREEZE",
    ],
)
def test_admin_can_preview_direct_high_risk_operation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    operation_type: str,
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix=f"PREVIEW-{operation_type}",
        frozen=operation_type == "UNFREEZE",
    )
    request_id = f"slice9c-preview-{operation_type}"
    response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=(
                f"slice9c-preview-{operation_type}"
            ),
        ),
        json=_preview_payload(
            operation_type,
            balance,
            lot,
        ),
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["status"] == "PREVIEWED"
    assert data["operation_type"] == operation_type
    assert data["transaction_version"] > 0
    assert isinstance(data["confirmation_token"], str)
    assert data["confirmation_token"]
    assert data["confirmation_expires_at"]
    assert "_extensions" not in data
    assert "confirmation_token_hash" not in data
    assert "response_snapshot_json" not in data

    session.expire_all()
    stored = session.get(
        InventoryTransaction,
        data["transaction_id"],
    )
    assert stored is not None
    assert stored.status == "PREVIEWED"
    assert stored.confirmation_token_hash == hashlib.sha256(
        data["confirmation_token"].encode("utf-8")
    ).hexdigest()
    assert stored.confirmation_token_hash != data[
        "confirmation_token"
    ]
    assert data["confirmation_token"] not in str(
        stored.response_snapshot_json
    )


def test_preview_replay_returns_plaintext_token_only_once(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="PREVIEW-REPLAY",
    )
    payload = _preview_payload(
        "ADJUST",
        balance,
        lot,
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9c-preview-replay",
        idempotency_key="slice9c-preview-replay",
    )

    first = client.post(
        "/api/v1/inventory/operations/preview",
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9c-preview-replay",
    )
    replay = client.post(
        "/api/v1/inventory/operations/preview",
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9c-preview-replay",
    )

    assert first_data["confirmation_token"]
    assert replay_data["confirmation_token"] is None
    assert (
        replay_data["transaction_id"]
        == first_data["transaction_id"]
    )
    assert session.scalar(
        select(func.count(InventoryTransaction.id))
    ) == 1


def test_preview_reused_key_with_changed_request_is_stable_conflict(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="PREVIEW-REUSED",
    )
    payload = _preview_payload(
        "ADJUST",
        balance,
        lot,
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9c-preview-reused",
        idempotency_key="slice9c-preview-reused",
    )

    first = client.post(
        "/api/v1/inventory/operations/preview",
        headers=headers,
        json=payload,
    )
    _assert_success(
        first,
        request_id="slice9c-preview-reused",
    )

    conflict = client.post(
        "/api/v1/inventory/operations/preview",
        headers=headers,
        json={
            **payload,
            "reason": "changed reason",
        },
    )
    error = _assert_error(
        conflict,
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        request_id="slice9c-preview-reused",
    )
    assert error["details"]["retryable"] is False


def test_admin_can_execute_previewed_freeze(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="EXECUTE-FREEZE",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-execute-preview",
            idempotency_key="slice9c-execute-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-execute-preview",
    )

    execute_response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-execute-freeze",
            idempotency_key="slice9c-execute-freeze",
        ),
        json=_execute_payload(preview),
    )
    data = _assert_success(
        execute_response,
        request_id="slice9c-execute-freeze",
    )

    assert data["operation_type"] == "FREEZE"
    assert data["status"] == "COMPLETED"
    session.expire_all()
    current_lot = session.get(InventoryLot, lot.id)
    assert current_lot is not None
    assert current_lot.is_frozen is True
    assert current_lot.freeze_reason == "quality hold"


def test_execute_replay_does_not_apply_state_twice(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="EXECUTE-REPLAY",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-execute-replay-preview",
            idempotency_key="slice9c-execute-replay-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-execute-replay-preview",
    )
    path = _path_for(
        "execute",
        transaction_id=preview["transaction_id"],
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9c-execute-replay",
        idempotency_key="slice9c-execute-replay",
    )
    payload = _execute_payload(preview)

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9c-execute-replay",
    )
    session.expire_all()
    lot_after_first = session.get(InventoryLot, lot.id)
    assert lot_after_first is not None
    version_after_first = lot_after_first.version
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
        request_id="slice9c-execute-replay",
    )
    session.expire_all()
    lot_after_replay = session.get(InventoryLot, lot.id)
    assert lot_after_replay is not None

    assert replay_data == first_data
    assert lot_after_replay.version == version_after_first
    assert session.scalar(
        select(func.count(InventoryLedgerEntry.id))
    ) == ledger_after_first


def test_execute_wrong_confirmation_token_uses_stable_error(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="TOKEN-INVALID",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-token-preview",
            idempotency_key="slice9c-token-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-token-preview",
    )

    response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-token-invalid",
            idempotency_key="slice9c-token-invalid",
        ),
        json=_execute_payload(
            preview,
            confirmation_token="definitely-wrong-token",
        ),
    )

    error = _assert_error(
        response,
        status_code=422,
        code="INVENTORY_CONFIRMATION_TOKEN_INVALID",
        request_id="slice9c-token-invalid",
    )
    assert error["details"]["retryable"] is False


def test_execute_expired_confirmation_uses_stable_error(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="TOKEN-EXPIRED",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-expired-preview",
            idempotency_key="slice9c-expired-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-expired-preview",
    )

    session.expire_all()
    transaction = session.get(
        InventoryTransaction,
        preview["transaction_id"],
    )
    assert transaction is not None
    transaction.confirmation_expires_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )
    session.commit()

    response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-token-expired",
            idempotency_key="slice9c-token-expired",
        ),
        json=_execute_payload(preview),
    )

    error = _assert_error(
        response,
        status_code=422,
        code="INVENTORY_CONFIRMATION_EXPIRED",
        request_id="slice9c-token-expired",
    )
    assert error["details"]["retryable"] is False


def test_execute_transaction_version_conflict_uses_stable_contract(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="TX-VERSION",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-version-preview",
            idempotency_key="slice9c-version-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-version-preview",
    )

    session.expire_all()
    transaction = session.get(
        InventoryTransaction,
        preview["transaction_id"],
    )
    assert transaction is not None
    transaction.version += 1
    actual_version = transaction.version
    session.commit()

    response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-version-conflict",
            idempotency_key="slice9c-version-conflict",
        ),
        json=_execute_payload(preview),
    )

    error = _assert_error(
        response,
        status_code=409,
        code="INVENTORY_TRANSACTION_VERSION_CONFLICT",
        request_id="slice9c-version-conflict",
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_transaction"
    assert details["object_id"] == preview["transaction_id"]
    assert (
        details["expected_version"]
        == preview["transaction_version"]
    )
    assert details["actual_version"] == actual_version
    assert details["affected_lines"] == []
    assert details["retryable"] is False
    assert details["suggested_action"]


def test_execute_operation_state_conflict_uses_stable_contract(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="OP-STATE",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-state-preview",
            idempotency_key="slice9c-state-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-state-preview",
    )

    session.expire_all()
    transaction = session.get(
        InventoryTransaction,
        preview["transaction_id"],
    )
    assert transaction is not None
    transaction.status = "COMPLETED"
    session.commit()

    response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-state-conflict",
            idempotency_key="slice9c-state-conflict",
        ),
        json=_execute_payload(preview),
    )

    error = _assert_error(
        response,
        status_code=409,
        code="INVENTORY_OPERATION_STATE_CONFLICT",
        request_id="slice9c-state-conflict",
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_transaction"
    assert details["object_id"] == preview["transaction_id"]
    assert details["affected_lines"] == []
    assert details["retryable"] is False
    assert details["suggested_action"]


def test_cross_tenant_operation_execute_is_not_found(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, lot = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="CROSS-TENANT",
    )
    preview_response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            tenant_id="tenant-a",
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-cross-preview",
            idempotency_key="slice9c-cross-preview",
        ),
        json=_preview_payload(
            "FREEZE",
            balance,
            lot,
        ),
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-cross-preview",
    )

    response = client.post(
        _path_for(
            "execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            tenant_id="tenant-b",
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-cross-tenant",
            idempotency_key="slice9c-cross-tenant",
        ),
        json=_execute_payload(preview),
    )

    error = _assert_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        request_id="slice9c-cross-tenant",
    )
    assert error["details"] == {
        "resource": "inventory_transaction",
        "identifier": preview["transaction_id"],
    }


@pytest.mark.parametrize(
    "stable_code",
    [
        "FEFO_OVERRIDE_REASON_REQUIRED",
        "LOT_EXPIRED",
        "LOT_FROZEN",
        "LOT_QUARANTINED",
    ],
)
def test_operation_preview_preserves_stable_domain_error(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    stable_code: str,
) -> None:
    def fail_preview(
        self,
        session,
        actor,
        *,
        command,
        idempotency_key,
    ):
        del self, session, command, idempotency_key
        error = BusinessValidationError(
            "stable operation validation failure",
            code=stable_code,
            details={"retryable": False},
        )
        error.request_id = actor.request_id
        raise error

    monkeypatch.setattr(
        InventoryOperationService,
        "preview",
        fail_preview,
    )
    request_id = f"slice9c-stable-{stable_code}"

    response = client.post(
        "/api/v1/inventory/operations/preview",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key=request_id,
        ),
        json=_minimal_preview_payload(),
    )

    error = _assert_error(
        response,
        status_code=422,
        code=stable_code,
        request_id=request_id,
    )
    assert error["details"]["retryable"] is False


def test_admin_can_preview_reverse_completed_transaction(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, original = _seed_completed_adjust(
        session,
        actor_context,
        suffix="REVERSE-PREVIEW",
    )
    request_id = "slice9c-reverse-preview"

    response = client.post(
        _path_for(
            "reverse_preview",
            transaction_id=original.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id=request_id,
            idempotency_key="slice9c-reverse-preview",
        ),
        json={
            "expected_transaction_version": original.version,
            "reason": "reverse completed adjustment",
        },
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["status"] == "PREVIEWED"
    assert data["operation_type"] == "REVERSE"
    assert data["confirmation_token"]
    assert data["transaction_id"] != original.id


def test_reverse_preview_replay_returns_token_only_once(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, original = _seed_completed_adjust(
        session,
        actor_context,
        suffix="REVERSE-REPLAY",
    )
    path = _path_for(
        "reverse_preview",
        transaction_id=original.id,
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.ADMIN,
        request_id="slice9c-reverse-replay",
        idempotency_key="slice9c-reverse-replay",
    )
    payload = {
        "expected_transaction_version": original.version,
        "reason": "reverse replay",
    }

    first = client.post(
        path,
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9c-reverse-replay",
    )
    replay = client.post(
        path,
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9c-reverse-replay",
    )

    assert first_data["confirmation_token"]
    assert replay_data["confirmation_token"] is None
    assert (
        replay_data["transaction_id"]
        == first_data["transaction_id"]
    )


def test_admin_can_execute_reverse_preview(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, _, original = _seed_completed_adjust(
        session,
        actor_context,
        suffix="REVERSE-EXECUTE",
    )
    session.expire_all()
    adjusted = session.get(
        InventoryBalance,
        balance.id,
    )
    assert adjusted is not None
    adjusted_quantity = adjusted.on_hand_quantity

    preview_response = client.post(
        _path_for(
            "reverse_preview",
            transaction_id=original.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-reverse-execute-preview",
            idempotency_key="slice9c-reverse-execute-preview",
        ),
        json={
            "expected_transaction_version": original.version,
            "reason": "reverse completed adjustment",
        },
    )
    preview = _assert_success(
        preview_response,
        request_id="slice9c-reverse-execute-preview",
    )

    execute_response = client.post(
        _path_for(
            "reverse_execute",
            transaction_id=preview["transaction_id"],
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.ADMIN,
            request_id="slice9c-reverse-execute",
            idempotency_key="slice9c-reverse-execute",
        ),
        json=_execute_payload(preview),
    )
    data = _assert_success(
        execute_response,
        request_id="slice9c-reverse-execute",
    )

    assert data["operation_type"] == "REVERSE"
    assert data["status"] == "COMPLETED"
    session.expire_all()
    current_balance = session.get(
        InventoryBalance,
        balance.id,
    )
    current_original = session.get(
        InventoryTransaction,
        original.id,
    )
    assert current_balance is not None
    assert current_original is not None
    assert current_balance.on_hand_quantity < adjusted_quantity
    assert (
        current_original.reversed_transaction_id
        == data["id"]
    )


def test_operation_route_delegates_planning_and_mutation_to_service(
) -> None:
    assert OPERATIONS_ROUTE_FILE.exists(), (
        "Task 9 Slice 9C requires "
        "app/api/v1/inventory/operations.py"
    )

    source = OPERATIONS_ROUTE_FILE.read_text(
        encoding="utf-8",
    )
    tree = ast.parse(
        source,
        filename=str(OPERATIONS_ROUTE_FILE),
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

    assert "InventoryOperationService" in imported_names
    assert "InventoryMutationPlan" not in imported_names
    assert "InventoryBalanceMutation" not in imported_names
    assert "InventoryStateMutation" not in imported_names
    assert "InventoryLedgerRepository" not in imported_names
    assert "InventoryTransactionService" not in imported_names
    assert all(
        not module.startswith("sqlalchemy")
        for module in imported_modules
    )

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }
    forbidden_route_logic = {
        "_adjust_plan",
        "_lot_freeze_state_plan",
        "_reverse_plan",
        "apply_plan",
        "apply_plan_to_transaction",
        "select_fefo",
    }
    assert forbidden_route_logic.isdisjoint(
        called_names | called_attributes
    )
