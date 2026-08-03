from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryPolicy,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseInventory,
    WarehouseLocation,
)
from app.models.enums import WarehouseStatus
from app.schemas.inventory import InventoryAdjustment
from app.security.actor import MaintenanceRole
from app.services.inventory_service import inventory_service
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.ADMIN,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"{role.value}-{tenant_id}",
        role=role,
        request_id=f"inventory-{tenant_id}-{role.value}",
    )


def _seed_inventory(
    session: Session,
    *,
    tenant_id: str = "tenant-a",
    suffix: str = "A",
    with_extra_balance: bool = False,
) -> tuple[InventoryBalance, InventoryPolicy]:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-LEDGER-{suffix}",
        name=f"Ledger warehouse {suffix}",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-LEDGER-{suffix}",
        name=f"Ledger spare {suffix}",
    )
    session.add_all([warehouse, spare])
    session.flush()
    default_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code="DEFAULT",
        name="Default location",
        location_type="DEFAULT",
    )
    session.add(default_location)
    session.flush()
    policy = InventoryPolicy(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        safety_stock=Decimal("2"),
        reorder_point=Decimal("4"),
        maximum_stock=Decimal("20"),
        notes="ledger policy",
    )
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=default_location.id,
        spare_part_id=spare.id,
        on_hand_quantity=Decimal("5"),
        reserved_quantity=Decimal("1"),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("2"),
    )
    session.add_all([policy, balance])
    if with_extra_balance:
        extra_location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="SHELF-1",
            name="Shelf 1",
            location_type="SHELF",
        )
        session.add(extra_location)
        session.flush()
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                location_id=extra_location.id,
                spare_part_id=spare.id,
                on_hand_quantity=Decimal("3"),
                reserved_quantity=Decimal("0"),
                damaged_quantity=Decimal("1"),
                quarantined_quantity=Decimal("0"),
                in_transit_quantity=Decimal("0"),
            )
        )
    session.flush()
    session.add(
        WarehouseInventory(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            spare_part_id=spare.id,
            on_hand_quantity=Decimal("99"),
            reserved_quantity=Decimal("0"),
            damaged_quantity=Decimal("0"),
            quarantined_quantity=Decimal("0"),
            in_transit_quantity=Decimal("0"),
            safety_stock=Decimal("0"),
            reorder_point=Decimal("0"),
        )
    )
    session.commit()
    return balance, policy


def _seed_non_default_only_inventory(
    session: Session,
    *,
    tenant_id: str = "tenant-a",
    suffix: str,
) -> InventoryBalance:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-NON-DEFAULT-{suffix}",
        name=f"Non-default warehouse {suffix}",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-NON-DEFAULT-{suffix}",
        name=f"Non-default spare {suffix}",
    )
    session.add_all([warehouse, spare])
    session.flush()
    shelf = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"SHELF-{suffix}",
        name=f"Shelf {suffix}",
        location_type="SHELF",
    )
    session.add(shelf)
    session.flush()
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=shelf.id,
        spare_part_id=spare.id,
        on_hand_quantity=Decimal("11"),
    )
    session.add_all(
        [
            InventoryPolicy(
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                spare_part_id=spare.id,
                safety_stock=Decimal("1"),
                reorder_point=Decimal("2"),
            ),
            balance,
        ]
    )
    session.commit()
    return balance


def test_list_and_get_inventory_use_ledger_summary_and_tenant_balance_id(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, _ = _seed_inventory(
        session,
        with_extra_balance=True,
    )
    foreign_balance, _ = _seed_inventory(
        session,
        tenant_id="tenant-b",
        suffix="B",
    )

    listed = client.get(
        "/api/v1/master-data/inventories",
        headers=_headers(internal_auth_headers, role=MaintenanceRole.VIEWER),
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1
    summary = listed.json()["data"]["items"][0]
    assert summary["id"] == balance.id
    assert summary["version"] == balance.version
    assert summary["on_hand_quantity"] == "8.0000"
    assert summary["reserved_quantity"] == "1.0000"
    assert summary["damaged_quantity"] == "1.0000"
    assert summary["available_quantity"] == "6.0000"
    assert summary["safety_stock"] == "2.0000"
    assert summary["notes"] == "ledger policy"

    fetched = client.get(
        f"/api/v1/master-data/inventories/{balance.id}",
        headers=_headers(internal_auth_headers, role=MaintenanceRole.VIEWER),
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"] == summary

    hidden = client.get(
        f"/api/v1/master-data/inventories/{foreign_balance.id}",
        headers=_headers(internal_auth_headers, role=MaintenanceRole.VIEWER),
    )
    assert hidden.status_code == 404


def test_list_filters_compatibility_identity_before_count_and_pagination(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    hidden = _seed_non_default_only_inventory(
        session,
        suffix="PAGE-HIDDEN",
    )
    first_default, _ = _seed_inventory(
        session,
        suffix="PAGE-FIRST",
        with_extra_balance=True,
    )
    second_default, _ = _seed_inventory(
        session,
        suffix="PAGE-SECOND",
    )
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.VIEWER,
    )

    first_page = client.get(
        "/api/v1/master-data/inventories?page=1&page_size=1",
        headers=headers,
    )
    second_page = client.get(
        "/api/v1/master-data/inventories?page=2&page_size=1",
        headers=headers,
    )

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    first_data = first_page.json()["data"]
    second_data = second_page.json()["data"]
    assert (
        first_data["total"],
        first_data["pages"],
        len(first_data["items"]),
    ) == (2, 2, 1)
    assert (
        second_data["total"],
        second_data["pages"],
        len(second_data["items"]),
    ) == (2, 2, 1)
    assert first_data["items"][0]["id"] == first_default.id
    assert first_data["items"][0]["version"] == first_default.version
    assert first_data["items"][0]["on_hand_quantity"] == "8.0000"
    assert second_data["items"][0]["id"] == second_default.id
    assert hidden.id not in {
        first_data["items"][0]["id"],
        second_data["items"][0]["id"],
    }


def test_non_compatibility_balance_ids_are_hidden_from_detail_and_writes(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    default_balance, policy = _seed_inventory(
        session,
        suffix="CANONICAL",
        with_extra_balance=True,
    )
    shelf_balance = session.scalar(
        select(InventoryBalance)
        .join(WarehouseLocation)
        .where(
            InventoryBalance.tenant_id == "tenant-a",
            InventoryBalance.warehouse_id
            == default_balance.warehouse_id,
            InventoryBalance.spare_part_id
            == default_balance.spare_part_id,
            WarehouseLocation.code == "SHELF-1",
        )
    )
    assert shelf_balance is not None
    lot = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=default_balance.spare_part_id,
        lot_code="LOT-CANONICAL",
    )
    session.add(lot)
    session.flush()
    lot_balance = InventoryBalance(
        tenant_id="tenant-a",
        warehouse_id=default_balance.warehouse_id,
        location_id=default_balance.location_id,
        spare_part_id=default_balance.spare_part_id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("4"),
    )
    session.add(lot_balance)
    session.commit()
    policy_state = (
        policy.safety_stock,
        policy.reorder_point,
        policy.version,
    )
    balance_states = {
        balance.id: (
            balance.on_hand_quantity,
            balance.version,
        )
        for balance in (shelf_balance, lot_balance)
    }
    transaction_count = session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    )
    headers = _headers(internal_auth_headers)
    statuses: list[int] = []

    for balance in (shelf_balance, lot_balance):
        statuses.append(
            client.get(
                f"/api/v1/master-data/inventories/{balance.id}",
                headers=headers,
            ).status_code
        )
        statuses.append(
            client.put(
                f"/api/v1/master-data/inventories/{balance.id}",
                headers=headers,
                json={"safety_stock": "7", "reorder_point": "8"},
            ).status_code
        )
        statuses.append(
            client.post(
                f"/api/v1/master-data/inventories/{balance.id}/adjust",
                headers={
                    **headers,
                    "Idempotency-Key": f"hidden-balance-{balance.id}",
                },
                json={
                    "expected_version": balance.version,
                    "on_hand_delta": "1",
                    "reason": "must remain hidden",
                },
            ).status_code
        )

    assert statuses == [404, 404, 404, 404, 404, 404]
    session.expire_all()
    assert (
        policy.safety_stock,
        policy.reorder_point,
        policy.version,
    ) == policy_state
    assert {
        balance.id: (
            balance.on_hand_quantity,
            balance.version,
        )
        for balance in (shelf_balance, lot_balance)
    } == balance_states
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_count


def test_create_update_reject_physical_fields_and_preserve_state(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-CREATE",
        name="Create warehouse",
    )
    spare = SparePart(
        tenant_id="tenant-a",
        code="SP-CREATE",
        name="Create spare",
    )
    session.add_all([warehouse, spare])
    session.commit()
    headers = _headers(internal_auth_headers)

    rejected_create = client.post(
        "/api/v1/master-data/inventories",
        headers=headers,
        json={
            "warehouse_id": warehouse.id,
            "spare_part_id": spare.id,
            "on_hand_quantity": "9",
            "reserved_quantity": "2",
            "damaged_quantity": "1",
            "quarantined_quantity": "1",
            "in_transit_quantity": "3",
            "safety_stock": "1",
            "reorder_point": "3",
        },
    )
    assert rejected_create.status_code == 422
    assert session.scalar(
        select(func.count()).select_from(InventoryBalance)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(InventoryPolicy)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 0

    created = client.post(
        "/api/v1/master-data/inventories",
        headers=headers,
        json={
            "warehouse_id": warehouse.id,
            "spare_part_id": spare.id,
            "safety_stock": "1",
            "reorder_point": "3",
            "maximum_stock": "12",
            "notes": "created policy",
        },
    )
    assert created.status_code == 201, created.text
    created_data = created.json()["data"]
    assert created_data["on_hand_quantity"] == "0.0000"
    assert created_data["reserved_quantity"] == "0.0000"
    assert created_data["safety_stock"] == "1.0000"
    default_balance = session.get(InventoryBalance, created_data["id"])
    assert default_balance is not None
    assert default_balance.on_hand_quantity == Decimal("0.0000")
    assert session.scalar(
        select(WarehouseLocation).where(
            WarehouseLocation.tenant_id == "tenant-a",
            WarehouseLocation.warehouse_id == warehouse.id,
            WarehouseLocation.code == "DEFAULT",
        )
    ) is not None

    before_quantities = (
        default_balance.on_hand_quantity,
        default_balance.reserved_quantity,
        default_balance.damaged_quantity,
        default_balance.quarantined_quantity,
        default_balance.in_transit_quantity,
        default_balance.version,
    )
    rejected_update = client.put(
        f"/api/v1/master-data/inventories/{created_data['id']}",
        headers=headers,
        json={
            "on_hand_quantity": "99",
            "reserved_quantity": "3",
            "damaged_quantity": "2",
            "quarantined_quantity": "1",
            "in_transit_quantity": "4",
        },
    )
    assert rejected_update.status_code == 422
    session.expire_all()
    default_balance = session.get(InventoryBalance, created_data["id"])
    assert default_balance is not None
    assert (
        default_balance.on_hand_quantity,
        default_balance.reserved_quantity,
        default_balance.damaged_quantity,
        default_balance.quarantined_quantity,
        default_balance.in_transit_quantity,
        default_balance.version,
    ) == before_quantities
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 0

    updated = client.put(
        f"/api/v1/master-data/inventories/{created_data['id']}",
        headers=headers,
        json={
            "safety_stock": "2",
            "reorder_point": "4",
            "notes": "updated policy",
        },
    )
    assert updated.status_code == 200, updated.text
    updated_data = updated.json()["data"]
    assert updated_data["on_hand_quantity"] == "0.0000"
    assert updated_data["safety_stock"] == "2.0000"
    assert updated_data["reorder_point"] == "4.0000"
    assert updated_data["notes"] == "updated policy"
    session.refresh(default_balance)
    assert default_balance.on_hand_quantity == Decimal("0.0000")


def test_create_and_update_inventory_policy_require_admin(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-ADMIN-POLICY",
        name="Admin policy warehouse",
    )
    spare = SparePart(
        tenant_id="tenant-a",
        code="SP-ADMIN-POLICY",
        name="Admin policy spare",
    )
    session.add_all([warehouse, spare])
    session.commit()
    contributor_headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
    )
    admin_headers = _headers(internal_auth_headers)
    create_payload = {
        "warehouse_id": warehouse.id,
        "spare_part_id": spare.id,
        "safety_stock": "1",
        "reorder_point": "3",
        "maximum_stock": "12",
        "notes": "admin policy",
    }

    denied_create = client.post(
        "/api/v1/master-data/inventories",
        headers=contributor_headers,
        json=create_payload,
    )
    assert denied_create.status_code == 403

    created = client.post(
        "/api/v1/master-data/inventories",
        headers=admin_headers,
        json=create_payload,
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["data"]["id"]

    denied_update = client.put(
        f"/api/v1/master-data/inventories/{identifier}",
        headers=contributor_headers,
        json={"safety_stock": "2", "reorder_point": "4"},
    )
    assert denied_update.status_code == 403

    updated = client.put(
        f"/api/v1/master-data/inventories/{identifier}",
        headers=admin_headers,
        json={"safety_stock": "2", "reorder_point": "4"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["safety_stock"] == "2.0000"
    assert updated.json()["data"]["reorder_point"] == "4.0000"


def test_adjust_requires_admin_idempotency_and_expected_version(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, _ = _seed_inventory(session)
    payload = {
        "expected_version": balance.version,
        "on_hand_delta": "2",
        "reserved_delta": "1",
        "damaged_delta": "1",
        "quarantined_delta": "0.5",
        "in_transit_delta": "3",
        "reason": "cycle correction",
    }
    route = f"/api/v1/master-data/inventories/{balance.id}/adjust"

    missing_key = client.post(
        route,
        headers=_headers(internal_auth_headers),
        json=payload,
    )
    assert missing_key.status_code == 422

    contributor = client.post(
        route,
        headers={
            **_headers(
                internal_auth_headers,
                role=MaintenanceRole.CONTRIBUTOR,
            ),
            "Idempotency-Key": "inventory-adjust-contributor",
        },
        json=payload,
    )
    assert contributor.status_code == 403

    adjusted = client.post(
        route,
        headers={
            **_headers(internal_auth_headers),
            "Idempotency-Key": "inventory-adjust-admin",
        },
        json=payload,
    )

    assert adjusted.status_code == 200, adjusted.text
    data = adjusted.json()["data"]
    assert data["transaction"]["operation_type"] == "ADJUST"
    assert data["transaction"]["idempotency_key"] == (
        "inventory-adjust-admin"
    )
    assert data["transaction"]["entries"][0]["balance_id"] == balance.id
    assert data["summary"]["id"] == balance.id
    assert data["summary"]["version"] == balance.version + 1
    assert data["summary"]["on_hand_quantity"] == "7.0000"
    assert data["summary"]["reserved_quantity"] == "2.0000"
    assert data["summary"]["damaged_quantity"] == "1.0000"
    assert data["summary"]["quarantined_quantity"] == "0.5000"
    assert data["summary"]["in_transit_quantity"] == "5.0000"
    assert session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.tenant_id == "tenant-a",
            InventoryTransaction.id
            == data["transaction"]["id"],
        )
    ) is not None
    assert session.scalar(
        select(InventoryLedgerEntry).where(
            InventoryLedgerEntry.transaction_id
            == data["transaction"]["id"],
        )
    ) is not None


def test_adjust_hides_cross_tenant_balance(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    foreign_balance, _ = _seed_inventory(
        session,
        tenant_id="tenant-b",
        suffix="FOREIGN",
    )

    response = client.post(
        (
            "/api/v1/master-data/inventories/"
            f"{foreign_balance.id}/adjust"
        ),
        headers={
            **_headers(internal_auth_headers),
            "Idempotency-Key": "inventory-adjust-foreign",
        },
        json={
            "expected_version": foreign_balance.version,
            "on_hand_delta": "1",
            "reserved_delta": "0",
            "damaged_delta": "0",
            "quarantined_delta": "0",
            "in_transit_delta": "0",
            "reason": "foreign correction",
        },
    )

    assert response.status_code == 404


def test_inventory_service_replays_before_mutable_identity_validation(
    session: Session,
    actor_admin,
) -> None:
    balance, _ = _seed_inventory(session)
    payload = InventoryAdjustment(
        expected_version=balance.version,
        on_hand_delta="2",
        reason="stable wrapper replay",
    )
    first = inventory_service.adjust(
        session,
        actor_admin,
        balance.id,
        payload,
        idempotency_key="inventory-wrapper-replay",
    )
    warehouse = session.get(Warehouse, balance.warehouse_id)
    location = session.get(
        WarehouseLocation,
        balance.location_id,
    )
    assert warehouse is not None
    assert location is not None
    warehouse.status = WarehouseStatus.FROZEN
    location.code = "RENAMED"
    balance.version += 5
    session.commit()

    replay = inventory_service.adjust(
        session,
        actor_admin,
        balance.id,
        payload,
        idempotency_key="inventory-wrapper-replay",
    )
    assert replay == first

    with pytest.raises(ConflictError) as exc_info:
        inventory_service.adjust(
            session,
            actor_admin,
            balance.id,
            payload.model_copy(
                update={"reason": "different wrapper request"}
            ),
            idempotency_key="inventory-wrapper-replay",
        )
    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_adjust_api_receipt_precedes_mutable_identity_validation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    balance, _ = _seed_inventory(session)
    route = f"/api/v1/master-data/inventories/{balance.id}/adjust"
    headers = {
        **_headers(internal_auth_headers),
        "Idempotency-Key": "inventory-api-stable-replay",
    }
    payload = {
        "expected_version": balance.version,
        "on_hand_delta": "2",
        "reserved_delta": "0",
        "damaged_delta": "0",
        "quarantined_delta": "0",
        "in_transit_delta": "0",
        "reason": "stable API replay",
    }
    first = client.post(route, headers=headers, json=payload)
    assert first.status_code == 200, first.text
    warehouse = session.get(Warehouse, balance.warehouse_id)
    location = session.get(
        WarehouseLocation,
        balance.location_id,
    )
    assert warehouse is not None
    assert location is not None
    warehouse.status = WarehouseStatus.FROZEN
    location.code = "RENAMED"
    balance.version += 5
    session.commit()
    session.refresh(balance)
    balance_state = (
        balance.on_hand_quantity,
        balance.reserved_quantity,
        balance.damaged_quantity,
        balance.quarantined_quantity,
        balance.in_transit_quantity,
        balance.version,
    )
    transaction_count = session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    )
    ledger_count = session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    )

    replay = client.post(route, headers=headers, json=payload)
    different = client.post(
        route,
        headers=headers,
        json={**payload, "reason": "different API request"},
    )
    new_command = client.post(
        route,
        headers={
            **headers,
            "Idempotency-Key": "inventory-api-renamed-new",
        },
        json=payload,
    )

    assert (
        replay.status_code,
        different.status_code,
        new_command.status_code,
    ) == (200, 409, 404)
    assert replay.json() == first.json()
    assert different.status_code == 409
    assert different.json()["error"]["code"] == (
        "IDEMPOTENCY_KEY_REUSED"
    )
    session.expire_all()
    assert (
        balance.on_hand_quantity,
        balance.reserved_quantity,
        balance.damaged_quantity,
        balance.quarantined_quantity,
        balance.in_transit_quantity,
        balance.version,
    ) == balance_state
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_count
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == ledger_count
