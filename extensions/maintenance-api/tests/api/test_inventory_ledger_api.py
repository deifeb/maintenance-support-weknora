from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryPolicy,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseInventory,
    WarehouseLocation,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import select
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


def test_create_and_update_only_manage_policy_and_default_identity(
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
    headers = _headers(
        internal_auth_headers,
        role=MaintenanceRole.CONTRIBUTOR,
    )

    created = client.post(
        "/api/v1/master-data/inventories",
        headers=headers,
        json={
            "warehouse_id": warehouse.id,
            "spare_part_id": spare.id,
            "on_hand_quantity": "9",
            "reserved_quantity": "2",
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

    updated = client.put(
        f"/api/v1/master-data/inventories/{created_data['id']}",
        headers=headers,
        json={
            "on_hand_quantity": "99",
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
