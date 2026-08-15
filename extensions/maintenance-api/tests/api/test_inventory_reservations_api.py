from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryReservation,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_reservation import (
    CancelCommand,
    IssueCommand,
    ReservationQuantityLine,
    ReserveCommand,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_reservation_service import (
    InventoryReservationService,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

WRITE_ROUTES = {
    "create": (
        "post",
        "/api/v1/inventory/reservations",
    ),
    "issue": (
        "post",
        "/api/v1/inventory/reservations/{reservation_id}/issue",
    ),
    "release": (
        "post",
        "/api/v1/inventory/reservations/{reservation_id}/release",
    ),
    "return": (
        "post",
        "/api/v1/inventory/reservations/{reservation_id}/return",
    ),
    "cancel": (
        "post",
        "/api/v1/inventory/reservations/{reservation_id}/cancel",
    ),
}
EXPECTED_OPENAPI_OPERATIONS = {
    (method, path)
    for method, path in WRITE_ROUTES.values()
}
RESERVATIONS_ROUTE_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "inventory"
    / "reservations.py"
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


def _minimal_create_payload() -> dict[str, Any]:
    return {
        "owner_type": "MANUAL",
        "owner_id": "slice9b-minimal",
        "spare_part_id": 1,
        "warehouse_id": 1,
        "requested_quantity": "1.0000",
        "allow_partial": False,
        "expected_balance_versions": {"1": 1},
        "as_of": "2026-08-15",
    }


def _minimal_payload(operation: str) -> dict[str, Any]:
    if operation == "create":
        return _minimal_create_payload()
    if operation == "issue":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "reservation_line_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }
    if operation == "release":
        return {
            "expected_version": 1,
            "lines": [],
        }
    if operation == "return":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "reservation_line_id": 1,
                    "issue_transaction_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }
    if operation == "cancel":
        return {"expected_version": 1}
    raise AssertionError(f"unsupported operation: {operation}")


def _path_for(
    operation: str,
    *,
    reservation_id: int = 1,
) -> str:
    _, template = WRITE_ROUTES[operation]
    return template.format(reservation_id=reservation_id)


def _seed_inventory(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
    quantities: tuple[str, ...] = ("5.0000", "4.0000"),
) -> tuple[
    Warehouse,
    SparePart,
    list[InventoryBalance],
]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-API-RES-{suffix}",
        name=f"Reservation API Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-API-RES-{suffix}",
        name=f"Reservation API Spare {suffix}",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    balances: list[InventoryBalance] = []
    for index, quantity in enumerate(quantities):
        location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code=f"LOC-API-RES-{suffix}-{index}",
            name=f"Reservation API Location {suffix} {index}",
            location_type="SHELF",
            is_pickable=True,
            is_active=True,
        )
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare_part.id,
            lot_code=f"LOT-API-RES-{suffix}-{index}",
            received_date=date(2026, 8, index + 1),
            expiry_date=date(2026, 9, 20 + index),
            quality_status="AVAILABLE",
            is_frozen=False,
        )
        session.add_all([location, lot])
        session.flush()

        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare_part.id,
            lot_id=lot.id,
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
    return warehouse, spare_part, balances


def _create_payload(
    warehouse: Warehouse,
    spare_part: SparePart,
    balances: list[InventoryBalance],
    *,
    requested_quantity: str = "3.0000",
    owner_id: str = "slice9b",
    allow_partial: bool = False,
) -> dict[str, Any]:
    return {
        "owner_type": "MANUAL",
        "owner_id": owner_id,
        "spare_part_id": spare_part.id,
        "warehouse_id": warehouse.id,
        "requested_quantity": requested_quantity,
        "allow_partial": allow_partial,
        "expected_balance_versions": {
            str(balance.id): balance.version
            for balance in balances
        },
        "as_of": "2026-08-15",
    }


def _seed_reservation(
    session: Session,
    actor_context: Callable[..., ActorContext],
    *,
    suffix: str,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
    requested_quantity: str = "3.0000",
) -> tuple[
    ActorContext,
    InventoryReservationService,
    Any,
    list[InventoryBalance],
]:
    actor = actor_context(
        tenant_id=tenant_id,
        user_id=f"seed-{role.value}-{suffix}",
        role=role,
        request_id=f"seed-slice9b-{suffix}",
        token_id=f"seed-token-slice9b-{suffix}",
    )
    warehouse, spare_part, balances = _seed_inventory(
        session,
        tenant_id=tenant_id,
        suffix=suffix,
    )
    service = InventoryReservationService()
    reservation = service.reserve(
        session,
        actor,
        command=ReserveCommand(
            owner_type="MANUAL",
            owner_id=f"seed-{suffix}",
            spare_part_id=spare_part.id,
            warehouse_id=warehouse.id,
            requested_quantity=requested_quantity,
            allow_partial=False,
            expected_balance_versions={
                balance.id: balance.version
                for balance in balances
            },
            as_of=date(2026, 8, 15),
        ),
        idempotency_key=f"seed-reserve-{suffix}",
    )
    session.commit()
    return actor, service, reservation, balances


def _assert_success(
    response,
    *,
    request_id: str,
    tenant_id: str = "tenant-a",
) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
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


def test_inventory_reservation_write_routes_are_registered(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    missing = sorted(
        f"{method.upper()} {path}"
        for method, path in EXPECTED_OPENAPI_OPERATIONS
        if method not in openapi_paths.get(path, {})
    )

    assert missing == [], (
        "Task 9 Slice 9B missing reservation write routes: "
        f"{missing}"
    )


def test_inventory_reservation_write_routes_require_authentication(
    client: TestClient,
) -> None:
    failures: list[tuple[str, int]] = []

    for operation in WRITE_ROUTES:
        response = client.post(
            _path_for(operation),
            headers={"Idempotency-Key": f"unauth-{operation}"},
            json=_minimal_payload(operation),
        )
        if response.status_code != 401:
            failures.append(
                (operation, response.status_code)
            )

    assert failures == []


def test_inventory_reservation_write_routes_reject_viewer(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int]] = []

    for operation in WRITE_ROUTES:
        request_id = f"slice9b-viewer-{operation}"
        response = client.post(
            _path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.VIEWER,
                request_id=request_id,
                idempotency_key=f"viewer-{operation}",
            ),
            json=_minimal_payload(operation),
        )
        if response.status_code != 403:
            failures.append(
                (operation, response.status_code)
            )

    assert failures == []


def test_all_reservation_writes_require_idempotency_key(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, int, str | None]] = []

    for operation in WRITE_ROUTES:
        request_id = f"slice9b-missing-key-{operation}"
        response = client.post(
            _path_for(operation),
            headers=_headers(
                internal_auth_headers,
                role=MaintenanceRole.CONTRIBUTOR,
                request_id=request_id,
            ),
            json=_minimal_payload(operation),
        )
        if response.status_code != 422:
            failures.append(
                (operation, response.status_code, None)
            )
            continue

        payload = response.json()
        error = payload.get("error", {})
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


def test_reservation_writes_reject_tenant_id_query_or_body(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[tuple[str, str, int]] = []

    for operation in WRITE_ROUTES:
        path = _path_for(operation)
        request_id = f"slice9b-tenant-{operation}"
        headers = _headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key=f"tenant-{operation}",
        )
        payload = _minimal_payload(operation)

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
    "role",
    [
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ],
)
def test_create_reservation_allows_contributor_and_admin(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    role: MaintenanceRole,
) -> None:
    suffix = f"CREATE-{role.value}"
    warehouse, spare_part, balances = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix=suffix,
    )
    request_id = f"slice9b-create-{role.value}"
    response = client.post(
        "/api/v1/inventory/reservations",
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=f"create-{role.value}",
        ),
        json=_create_payload(
            warehouse,
            spare_part,
            balances,
            owner_id=f"create-{role.value}",
        ),
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["status"] == "ACTIVE"
    assert data["tenant_id"] == "tenant-a"
    assert data["reserved_quantity"] == "3.0000"


@pytest.mark.parametrize(
    "role",
    [
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ],
)
def test_issue_reservation_allows_contributor_and_admin(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
    role: MaintenanceRole,
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix=f"ISSUE-{role.value}",
        role=role,
    )
    line = reservation.lines[0]
    request_id = f"slice9b-issue-{role.value}"

    response = client.post(
        _path_for(
            "issue",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=f"issue-{role.value}",
        ),
        json={
            "expected_version": reservation.version,
            "lines": [
                {
                    "reservation_line_id": line.id,
                    "quantity": "1.0000",
                }
            ],
        },
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["issued_quantity"] == "1.0000"
    assert data["status"] == "PARTIALLY_ISSUED"


@pytest.mark.parametrize(
    "role",
    [
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ],
)
def test_release_reservation_allows_contributor_and_admin(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
    role: MaintenanceRole,
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix=f"RELEASE-{role.value}",
        role=role,
    )
    request_id = f"slice9b-release-{role.value}"

    response = client.post(
        _path_for(
            "release",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=f"release-{role.value}",
        ),
        json={
            "expected_version": reservation.version,
            "lines": [],
        },
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["status"] == "RELEASED"
    assert data["released_quantity"] == "3.0000"


@pytest.mark.parametrize(
    "role",
    [
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ],
)
def test_cancel_reservation_allows_contributor_and_admin(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
    role: MaintenanceRole,
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix=f"CANCEL-{role.value}",
        role=role,
    )
    request_id = f"slice9b-cancel-{role.value}"

    response = client.post(
        _path_for(
            "cancel",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=f"cancel-{role.value}",
        ),
        json={"expected_version": reservation.version},
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["status"] == "CANCELLED"


@pytest.mark.parametrize(
    "role",
    [
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ],
)
def test_return_reservation_allows_contributor_and_admin(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
    role: MaintenanceRole,
) -> None:
    actor, service, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix=f"RETURN-{role.value}",
        role=role,
    )
    line = reservation.lines[0]
    issued = service.issue(
        session,
        actor,
        reservation.id,
        command=IssueCommand(
            expected_version=reservation.version,
            lines=(
                ReservationQuantityLine(
                    reservation_line_id=line.id,
                    quantity="1.0000",
                ),
            ),
        ),
        idempotency_key=f"seed-issue-return-{role.value}",
    )
    issue_transaction = session.scalar(
        select(InventoryTransaction)
        .where(
            InventoryTransaction.tenant_id == "tenant-a",
            InventoryTransaction.operation_type == "ISSUE",
        )
        .order_by(InventoryTransaction.id.desc())
    )
    assert issue_transaction is not None
    session.commit()

    request_id = f"slice9b-return-{role.value}"
    response = client.post(
        _path_for(
            "return",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=role,
            request_id=request_id,
            idempotency_key=f"return-{role.value}",
        ),
        json={
            "expected_version": issued.version,
            "lines": [
                {
                    "reservation_line_id": line.id,
                    "issue_transaction_id": issue_transaction.id,
                    "quantity": "1.0000",
                }
            ],
        },
    )

    data = _assert_success(
        response,
        request_id=request_id,
    )
    assert data["issued_quantity"] == "1.0000"


def test_create_reservation_replays_same_idempotency_key(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    warehouse, spare_part, balances = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REPLAY",
    )
    payload = _create_payload(
        warehouse,
        spare_part,
        balances,
        requested_quantity="2.0000",
        owner_id="create-replay",
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="slice9b-create-replay",
        idempotency_key="slice9b-create-replay",
    )

    first = client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9b-create-replay",
    )
    session.expire_all()
    reserved_after_first = session.get(
        InventoryBalance,
        balances[0].id,
    ).reserved_quantity

    replay = client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9b-create-replay",
    )
    session.expire_all()
    reserved_after_replay = session.get(
        InventoryBalance,
        balances[0].id,
    ).reserved_quantity

    assert replay_data == first_data
    assert reserved_after_replay == reserved_after_first
    assert session.scalar(
        select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.operation_type == "RESERVE"
        )
    ) == 1


def test_create_reservation_reused_key_with_changed_payload_is_stable_conflict(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    warehouse, spare_part, balances = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="CREATE-REUSED",
    )
    payload = _create_payload(
        warehouse,
        spare_part,
        balances,
        requested_quantity="2.0000",
        owner_id="create-reused",
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="slice9b-create-reused",
        idempotency_key="slice9b-create-reused",
    )

    first = client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json=payload,
    )
    _assert_success(
        first,
        request_id="slice9b-create-reused",
    )

    changed = {
        **payload,
        "requested_quantity": "3.0000",
    }
    conflict = client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json=changed,
    )
    error = _assert_error(
        conflict,
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        request_id="slice9b-create-reused",
    )
    assert error["details"]["retryable"] is False


def test_issue_replay_does_not_mutate_inventory_twice(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, reservation, balances = _seed_reservation(
        session,
        actor_context,
        suffix="ISSUE-REPLAY",
    )
    line = reservation.lines[0]
    payload = {
        "expected_version": reservation.version,
        "lines": [
            {
                "reservation_line_id": line.id,
                "quantity": "1.0000",
            }
        ],
    }
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="slice9b-issue-replay",
        idempotency_key="slice9b-issue-replay",
    )

    first = client.post(
        _path_for(
            "issue",
            reservation_id=reservation.id,
        ),
        headers=headers,
        json=payload,
    )
    first_data = _assert_success(
        first,
        request_id="slice9b-issue-replay",
    )
    session.expire_all()
    balance_after_first = session.get(
        InventoryBalance,
        balances[0].id,
    )
    quantities_after_first = (
        balance_after_first.on_hand_quantity,
        balance_after_first.reserved_quantity,
        balance_after_first.version,
    )

    replay = client.post(
        _path_for(
            "issue",
            reservation_id=reservation.id,
        ),
        headers=headers,
        json=payload,
    )
    replay_data = _assert_success(
        replay,
        request_id="slice9b-issue-replay",
    )
    session.expire_all()
    balance_after_replay = session.get(
        InventoryBalance,
        balances[0].id,
    )
    quantities_after_replay = (
        balance_after_replay.on_hand_quantity,
        balance_after_replay.reserved_quantity,
        balance_after_replay.version,
    )

    assert replay_data == first_data
    assert quantities_after_replay == quantities_after_first
    assert session.scalar(
        select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.operation_type == "ISSUE"
        )
    ) == 1


def test_cross_tenant_reservation_write_is_not_found(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix="CROSS-TENANT",
        tenant_id="tenant-a",
    )
    request_id = "slice9b-cross-tenant"

    response = client.post(
        _path_for(
            "release",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            tenant_id="tenant-b",
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key="slice9b-cross-tenant",
        ),
        json={
            "expected_version": reservation.version,
            "lines": [],
        },
    )

    error = _assert_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        request_id=request_id,
    )
    assert error["details"] == {
        "resource": "inventory_reservation",
        "identifier": reservation.id,
    }


def test_reservation_version_conflict_uses_stable_contract(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix="VERSION-CONFLICT",
    )
    request_id = "slice9b-version-conflict"
    expected_version = reservation.version + 1

    response = client.post(
        _path_for(
            "release",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key="slice9b-version-conflict",
        ),
        json={
            "expected_version": expected_version,
            "lines": [],
        },
    )

    error = _assert_error(
        response,
        status_code=409,
        code="RESERVATION_STATE_CONFLICT",
        request_id=request_id,
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_reservation"
    assert details["object_id"] == reservation.id
    assert details["expected_version"] == expected_version
    assert details["actual_version"] == reservation.version
    assert details["retryable"] is False
    assert "affected_lines" in details
    assert "suggested_action" in details


def test_terminal_reservation_uses_stable_state_conflict(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    actor, service, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix="STATE-CONFLICT",
    )
    cancelled = service.cancel(
        session,
        actor,
        reservation.id,
        command=CancelCommand(
            expected_version=reservation.version,
        ),
        idempotency_key="seed-cancel-state-conflict",
    )
    session.commit()
    line = cancelled.lines[0]
    request_id = "slice9b-state-conflict"

    response = client.post(
        _path_for(
            "issue",
            reservation_id=cancelled.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key="slice9b-state-conflict",
        ),
        json={
            "expected_version": cancelled.version,
            "lines": [
                {
                    "reservation_line_id": line.id,
                    "quantity": "1.0000",
                }
            ],
        },
    )

    error = _assert_error(
        response,
        status_code=409,
        code="RESERVATION_STATE_CONFLICT",
        request_id=request_id,
    )
    details = error["details"]
    assert details["conflict_object"] == "inventory_reservation"
    assert details["object_id"] == cancelled.id
    assert details["retryable"] is False
    assert "suggested_action" in details


def test_expired_reservation_preserves_stable_error(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _, _, reservation, _ = _seed_reservation(
        session,
        actor_context,
        suffix="EXPIRED",
    )
    stored = session.get(
        InventoryReservation,
        reservation.id,
    )
    stored.expires_at = datetime(
        2000,
        1,
        1,
        tzinfo=timezone.utc,
    )
    session.commit()
    line = reservation.lines[0]
    request_id = "slice9b-expired"

    response = client.post(
        _path_for(
            "issue",
            reservation_id=reservation.id,
        ),
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key="slice9b-expired",
        ),
        json={
            "expected_version": reservation.version,
            "lines": [
                {
                    "reservation_line_id": line.id,
                    "quantity": "1.0000",
                }
            ],
        },
    )

    _assert_error(
        response,
        status_code=422,
        code="RESERVATION_EXPIRED",
        request_id=request_id,
    )


def test_fefo_insufficient_inventory_preserves_stable_error(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    warehouse, spare_part, balances = _seed_inventory(
        session,
        tenant_id="tenant-a",
        suffix="FEFO-INSUFFICIENT",
        quantities=("1.0000",),
    )
    request_id = "slice9b-fefo-insufficient"

    response = client.post(
        "/api/v1/inventory/reservations",
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            idempotency_key="slice9b-fefo-insufficient",
        ),
        json=_create_payload(
            warehouse,
            spare_part,
            balances,
            requested_quantity="2.0000",
            owner_id="fefo-insufficient",
        ),
    )

    error = _assert_error(
        response,
        status_code=422,
        code="INSUFFICIENT_AVAILABLE_INVENTORY",
        request_id=request_id,
    )
    assert error["details"] == {
        "requested_quantity": "2.0000",
        "unfilled_quantity": "1.0000",
    }


def test_reservation_route_delegates_fefo_to_service() -> None:
    assert RESERVATIONS_ROUTE_FILE.exists(), (
        "Task 9 Slice 9B requires "
        "app/api/v1/inventory/reservations.py"
    )

    source = RESERVATIONS_ROUTE_FILE.read_text(
        encoding="utf-8",
    )
    tree = ast.parse(
        source,
        filename=str(RESERVATIONS_ROUTE_FILE),
    )
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "InventoryReservationService" in imported_names
    assert all(
        "inventory_fefo_service" not in module
        for module in imported_modules
    )
    assert "select_fefo" not in imported_names
    assert "InventoryLedgerRepository" not in imported_names
    assert "InventoryMutationPlan" not in imported_names
    assert "sqlalchemy" not in source
