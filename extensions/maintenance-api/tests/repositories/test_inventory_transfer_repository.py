from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from app.models import (
    InventoryBalance,
    InventoryTransfer,
    InventoryTransferLine,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from sqlalchemy import select


def _repository_class():
    try:
        module = importlib.import_module(
            "app.repositories.inventory_transfer_repository"
        )
    except ModuleNotFoundError as exc:
        if exc.name == "app.repositories.inventory_transfer_repository":
            pytest.fail(
                "InventoryTransferRepository is not implemented",
                pytrace=False,
            )
        raise

    repository_class = getattr(
        module,
        "InventoryTransferRepository",
        None,
    )
    if repository_class is None:
        pytest.fail(
            "InventoryTransferRepository is not implemented",
            pytrace=False,
        )
    return repository_class


def _seed_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    on_hand: str = "10",
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-TR-{suffix}",
        name=f"Transfer Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-TR-{suffix}",
        name=f"Transfer Part {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()

    source_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"SRC-{suffix}",
        name=f"Source {suffix}",
        location_type="SHELF",
    )
    target_location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"DST-{suffix}",
        name=f"Target {suffix}",
        location_type="SHELF",
    )
    session.add_all(
        [source_location, target_location]
    )
    session.flush()

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=source_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal("0"),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("0"),
    )
    session.add(balance)
    session.flush()

    return (
        warehouse,
        part,
        source_location,
        target_location,
        balance,
    )


def _seed_transfer(
    session,
    actor_admin,
    *,
    suffix: str,
):
    (
        warehouse,
        part,
        source_location,
        target_location,
        source_balance,
    ) = _seed_balance(
        session,
        tenant_id=actor_admin.tenant_id,
        suffix=suffix,
    )

    target_balance = InventoryBalance(
        tenant_id=actor_admin.tenant_id,
        warehouse_id=warehouse.id,
        location_id=target_location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal("0"),
        reserved_quantity=Decimal("0"),
        damaged_quantity=Decimal("0"),
        quarantined_quantity=Decimal("0"),
        in_transit_quantity=Decimal("0"),
    )
    session.add(target_balance)
    session.flush()

    transfer = InventoryTransfer(
        tenant_id=actor_admin.tenant_id,
        status="DRAFT",
        source_warehouse_id=warehouse.id,
        source_location_id=source_location.id,
        target_warehouse_id=warehouse.id,
        target_location_id=target_location.id,
        reason="repository fixture",
        actor_user_id=actor_admin.user_id,
        actor_roles_json=[actor_admin.role.value],
        request_id=actor_admin.request_id,
    )
    session.add(transfer)
    session.flush()

    first = InventoryTransferLine(
        tenant_id=actor_admin.tenant_id,
        transfer_id=transfer.id,
        spare_part_id=part.id,
        source_balance_id=source_balance.id,
        target_balance_id=target_balance.id,
        requested_quantity=Decimal("1.0000"),
        dispatched_quantity=Decimal("0.0000"),
        received_quantity=Decimal("0.0000"),
        expected_source_version=source_balance.version,
        expected_target_version=target_balance.version,
    )
    second = InventoryTransferLine(
        tenant_id=actor_admin.tenant_id,
        transfer_id=transfer.id,
        spare_part_id=part.id,
        source_balance_id=source_balance.id,
        target_balance_id=target_balance.id,
        requested_quantity=Decimal("2.0000"),
        dispatched_quantity=Decimal("0.0000"),
        received_quantity=Decimal("0.0000"),
        expected_source_version=source_balance.version,
        expected_target_version=target_balance.version,
    )
    session.add_all([first, second])
    session.flush()

    return transfer, first, second


def test_transfer_repository_get_is_tenant_scoped(
    session,
    actor_admin,
) -> None:
    transfer, _, _ = _seed_transfer(
        session,
        actor_admin,
        suffix="GET",
    )

    repository = _repository_class()()

    visible = repository.get_transfer(
        session,
        actor_admin.tenant_id,
        transfer.id,
    )
    hidden = repository.get_transfer(
        session,
        "tenant-b",
        transfer.id,
    )

    assert visible is not None
    assert visible.id == transfer.id
    assert hidden is None


def test_transfer_repository_lock_is_tenant_scoped(
    session,
    actor_admin,
) -> None:
    transfer, _, _ = _seed_transfer(
        session,
        actor_admin,
        suffix="LOCK",
    )

    repository = _repository_class()()

    locked = repository.lock_transfer(
        session,
        actor_admin.tenant_id,
        transfer.id,
    )
    hidden = repository.lock_transfer(
        session,
        "tenant-b",
        transfer.id,
    )

    assert locked is not None
    assert locked.id == transfer.id
    assert hidden is None


def test_transfer_repository_lists_lines_in_stable_id_order(
    session,
    actor_admin,
) -> None:
    transfer, first, second = _seed_transfer(
        session,
        actor_admin,
        suffix="LINES",
    )

    repository = _repository_class()()

    lines = repository.list_lines(
        session,
        actor_admin.tenant_id,
        transfer.id,
    )

    assert [line.id for line in lines] == [
        first.id,
        second.id,
    ]

    persisted = list(
        session.scalars(
            select(InventoryTransferLine)
            .where(
                InventoryTransferLine.transfer_id
                == transfer.id
            )
            .order_by(InventoryTransferLine.id)
        )
    )
    assert [line.id for line in lines] == [
        line.id for line in persisted
    ]
