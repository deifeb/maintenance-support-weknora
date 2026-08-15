from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryReservation,
    InventoryStocktake,
    InventoryTransaction,
    InventoryTransfer,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.schemas.inventory_reservation import ReserveCommand
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_operation_service import InventoryOperationService
from app.services.inventory_reservation_service import InventoryReservationService
from app.services.inventory_stocktake_service import InventoryStocktakeService
from app.services.inventory_transfer_service import InventoryTransferService
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

READ_LIST_PATHS = {
    "balances": "/api/v1/inventory/balances",
    "transactions": "/api/v1/inventory/transactions",
    "reservations": "/api/v1/inventory/reservations",
    "transfers": "/api/v1/inventory/transfers",
    "stocktakes": "/api/v1/inventory/stocktakes",
}
READ_DETAIL_PATHS = {
    resource: f"{path}/{{identifier}}"
    for resource, path in READ_LIST_PATHS.items()
}
EXPECTED_READ_PATHS = {
    *READ_LIST_PATHS.values(),
    *(f"{path}/{{identifier}}" for path in READ_LIST_PATHS.values()),
}
RESOURCE_MODELS = {
    "balances": InventoryBalance,
    "transactions": InventoryTransaction,
    "reservations": InventoryReservation,
    "transfers": InventoryTransfer,
    "stocktakes": InventoryStocktake,
}
PRIVATE_TRANSACTION_FIELDS = {
    "_extensions",
    "preview_command",
    "confirmation_token",
    "confirmation_token_hash",
    "confirmation_expires_at",
    "response_snapshot_json",
}


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    role: MaintenanceRole,
    tenant_id: str = "tenant-a",
    request_id: str,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{role.value}-{tenant_id}",
        role=role,
        request_id=request_id,
    )


def _seed_balance_facts(
    session: Session,
    *,
    tenant_id: str,
    suffix: str,
) -> dict[str, Any]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-READ-{suffix}",
        name=f"Inventory Read Warehouse {suffix}",
    )
    spare_part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-READ-{suffix}",
        name=f"Inventory Read Spare {suffix}",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, spare_part])
    session.flush()

    source_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"SRC-READ-{suffix}",
        name=f"Inventory Read Source {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    target_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"DST-READ-{suffix}",
        name=f"Inventory Read Target {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    lot = InventoryLot(
        tenant_id=tenant_id,
        spare_part_id=spare_part.id,
        lot_code=f"LOT-READ-{suffix}",
        received_date=date(2026, 8, 1),
        expiry_date=date(2026, 9, 30),
        quality_status="AVAILABLE",
        is_frozen=False,
    )
    session.add_all([source_location, target_location, lot])
    session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=source_location.id,
        spare_part_id=spare_part.id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("10.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add(balance)
    session.flush()

    return {
        "warehouse": warehouse,
        "spare_part": spare_part,
        "source_location": source_location,
        "target_location": target_location,
        "lot": lot,
        "balance": balance,
    }


def _seed_preview_transaction(
    session: Session,
    actor: ActorContext,
    *,
    tenant_id: str,
    suffix: str,
) -> int:
    facts = _seed_balance_facts(
        session,
        tenant_id=tenant_id,
        suffix=f"PREVIEW-{suffix}",
    )
    balance = facts["balance"]
    lot = facts["lot"]

    preview = InventoryOperationService().preview(
        session,
        actor,
        command={
            "operation_type": "FREEZE",
            "balance_id": balance.id,
            "expected_balance_version": balance.version,
            "lot_id": lot.id,
            "expected_lot_version": lot.version,
            "reason": "Task 9 read contract preview",
        },
        idempotency_key=f"slice9a-preview-{suffix}",
    )
    return preview.transaction_id


def _seed_tenant_surface(
    session: Session,
    actor_context: Callable[..., ActorContext],
    *,
    tenant_id: str,
    suffix: str,
    include_preview: bool,
) -> dict[str, int]:
    actor = actor_context(
        tenant_id=tenant_id,
        user_id=f"admin-{tenant_id}",
        role=MaintenanceRole.ADMIN,
        request_id=f"seed-slice9a-{suffix}",
        token_id=f"token-slice9a-{suffix}",
    )
    facts = _seed_balance_facts(
        session,
        tenant_id=tenant_id,
        suffix=suffix,
    )
    balance = facts["balance"]

    reservation = InventoryReservationService().reserve(
        session,
        actor,
        command=ReserveCommand(
            owner_type="MANUAL",
            owner_id=f"slice9a-{suffix}",
            spare_part_id=facts["spare_part"].id,
            warehouse_id=facts["warehouse"].id,
            requested_quantity="2.0000",
            allow_partial=False,
            expected_balance_versions={balance.id: balance.version},
            as_of=date(2026, 8, 15),
        ),
        idempotency_key=f"slice9a-reserve-{suffix}",
    )
    session.refresh(balance)

    transfer = InventoryTransferService().create(
        session,
        actor,
        command={
            "source_warehouse_id": facts["warehouse"].id,
            "source_location_id": facts["source_location"].id,
            "target_warehouse_id": facts["warehouse"].id,
            "target_location_id": facts["target_location"].id,
            "reference_type": "manual",
            "reference_id": f"slice9a-transfer-{suffix}",
            "reason": "Task 9 read contract transfer",
            "lines": [
                {
                    "spare_part_id": facts["spare_part"].id,
                    "source_balance_id": balance.id,
                    "lot_id": facts["lot"].id,
                    "serial_item_id": None,
                    "quantity": "1.0000",
                    "expected_source_version": balance.version,
                }
            ],
        },
        idempotency_key=f"slice9a-transfer-{suffix}",
    )

    stocktake = InventoryStocktakeService().create(
        session,
        actor,
        command={
            "warehouse_id": facts["warehouse"].id,
            "location_id": facts["source_location"].id,
        },
        idempotency_key=f"slice9a-stocktake-{suffix}",
    )

    reserve_transaction = session.scalar(
        select(InventoryTransaction)
        .where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.operation_type == "RESERVE",
        )
        .order_by(InventoryTransaction.id.desc())
    )
    assert reserve_transaction is not None

    preview_transaction_id = 0
    if include_preview:
        preview_transaction_id = _seed_preview_transaction(
            session,
            actor,
            tenant_id=tenant_id,
            suffix=suffix,
        )

    return {
        "balances": balance.id,
        "transactions": reserve_transaction.id,
        "reservations": reservation.id,
        "transfers": transfer.id,
        "stocktakes": stocktake.id,
        "preview_transaction": preview_transaction_id,
    }


def _ids_for_tenant(
    session: Session,
    *,
    tenant_id: str,
) -> dict[str, set[int]]:
    return {
        resource: set(
            session.scalars(
                select(model.id).where(model.tenant_id == tenant_id)
            ).all()
        )
        for resource, model in RESOURCE_MODELS.items()
    }


def _seed_read_surface(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> dict[str, Any]:
    local = _seed_tenant_surface(
        session,
        actor_context,
        tenant_id="tenant-a",
        suffix="A",
        include_preview=True,
    )
    foreign = _seed_tenant_surface(
        session,
        actor_context,
        tenant_id="tenant-b",
        suffix="B",
        include_preview=False,
    )
    session.commit()

    return {
        "local": local,
        "foreign": foreign,
        "local_ids": _ids_for_tenant(session, tenant_id="tenant-a"),
        "foreign_ids": _ids_for_tenant(session, tenant_id="tenant-b"),
    }


def _assert_success_meta(
    payload: dict[str, Any],
    *,
    tenant_id: str,
    request_id: str,
) -> None:
    assert payload["success"] is True
    assert payload["meta"]["tenant_id"] == tenant_id
    assert payload["meta"]["request_id"] == request_id


def test_inventory_router_exposes_exact_slice9a_read_paths(
    client: TestClient,
) -> None:
    actual_paths = set(client.app.openapi()["paths"])
    missing = sorted(EXPECTED_READ_PATHS - actual_paths)

    assert missing == [], (
        "Task 9 Slice 9A missing Inventory read paths: "
        f"{missing}"
    )


def test_inventory_read_routes_require_authentication(
    client: TestClient,
) -> None:
    paths = [
        *READ_LIST_PATHS.values(),
        *(
            template.format(identifier=1)
            for template in READ_DETAIL_PATHS.values()
        ),
    ]
    failures: list[tuple[str, int]] = []
    for path in paths:
        response = client.get(path)
        if response.status_code != 401:
            failures.append((path, response.status_code))

    assert failures == []


def test_inventory_list_routes_allow_all_roles_with_page_and_meta(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    seeded = _seed_read_surface(session, actor_context)

    for role in (
        MaintenanceRole.VIEWER,
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ):
        for resource, path in READ_LIST_PATHS.items():
            request_id = f"slice9a-{role.value}-{resource}"
            response = client.get(
                path,
                params={"page": 1, "page_size": 100},
                headers=_headers(
                    internal_auth_headers,
                    role=role,
                    request_id=request_id,
                ),
            )
            assert response.status_code == 200, (
                f"{role.value} GET {path}: {response.text}"
            )
            payload = response.json()
            _assert_success_meta(
                payload,
                tenant_id="tenant-a",
                request_id=request_id,
            )
            data = payload["data"]
            assert data["page"] == 1
            assert data["page_size"] == 100
            assert data["total"] == len(seeded["local_ids"][resource])
            assert data["pages"] == 1
            actual_ids = {item["id"] for item in data["items"]}
            assert actual_ids == seeded["local_ids"][resource]
            assert actual_ids.isdisjoint(
                seeded["foreign_ids"][resource]
            )


def test_inventory_detail_routes_are_tenant_scoped(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    seeded = _seed_read_surface(session, actor_context)
    request_id = "slice9a-detail-tenant-a"
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
        request_id=request_id,
    )

    for resource, template in READ_DETAIL_PATHS.items():
        local_id = seeded["local"][resource]
        foreign_id = seeded["foreign"][resource]

        visible = client.get(
            template.format(identifier=local_id),
            headers=headers,
        )
        assert visible.status_code == 200, (
            f"tenant-a {resource} detail: {visible.text}"
        )
        payload = visible.json()
        _assert_success_meta(
            payload,
            tenant_id="tenant-a",
            request_id=request_id,
        )
        assert payload["data"]["id"] == local_id

        hidden = client.get(
            template.format(identifier=foreign_id),
            headers=headers,
        )
        assert hidden.status_code == 404, (
            f"cross-tenant {resource} detail leaked: {hidden.text}"
        )


def test_inventory_read_routes_reject_tenant_id_in_query_or_body(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
        request_id="slice9a-tenant-injection",
    )
    failures: list[tuple[str, str, int]] = []

    for path in READ_LIST_PATHS.values():
        query_response = client.get(
            path,
            params={"tenant_id": "tenant-b"},
            headers=headers,
        )
        if query_response.status_code != 422:
            failures.append((path, "query", query_response.status_code))

        body_response = client.request(
            "GET",
            path,
            headers=headers,
            json={"tenant_id": "tenant-b"},
        )
        if body_response.status_code != 422:
            failures.append((path, "body", body_response.status_code))

    assert failures == []


def test_transaction_list_and_detail_hide_private_preview_storage(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    seeded = _seed_read_surface(session, actor_context)
    preview_id = seeded["local"]["preview_transaction"]
    assert preview_id > 0

    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
        request_id="slice9a-private-preview",
    )

    listed = client.get(
        READ_LIST_PATHS["transactions"],
        params={"page": 1, "page_size": 100},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    listed_payload = listed.json()
    _assert_success_meta(
        listed_payload,
        tenant_id="tenant-a",
        request_id="slice9a-private-preview",
    )
    preview_items = [
        item
        for item in listed_payload["data"]["items"]
        if item["id"] == preview_id
    ]
    assert len(preview_items) == 1

    detailed = client.get(
        READ_DETAIL_PATHS["transactions"].format(identifier=preview_id),
        headers=headers,
    )
    assert detailed.status_code == 200, detailed.text
    detailed_payload = detailed.json()
    _assert_success_meta(
        detailed_payload,
        tenant_id="tenant-a",
        request_id="slice9a-private-preview",
    )
    assert detailed_payload["data"]["id"] == preview_id

    for payload in (preview_items[0], detailed_payload["data"]):
        serialized = json.dumps(payload, sort_keys=True, default=str)
        for private_field in PRIVATE_TRANSACTION_FIELDS:
            assert private_field not in serialized
