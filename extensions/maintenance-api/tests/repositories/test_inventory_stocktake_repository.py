from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

from app.models import (
    InventoryBalance,
    InventoryStocktake,
    InventoryStocktakeLine,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from sqlalchemy.dialects import postgresql


def _repository_class():
    module = importlib.import_module(
        "app.repositories.inventory_stocktake_repository"
    )
    return module.InventoryStocktakeRepository


def _seed_scope(session, *, tenant_id: str, suffix: str):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-STK-{suffix}",
        name=f"Warehouse {suffix}",
    )
    spare_a = SparePart(
        tenant_id=tenant_id,
        code=f"SP-STK-{suffix}-A",
        name=f"Stocktake Part {suffix} A",
        unit="EA",
        is_serialized=False,
    )
    spare_b = SparePart(
        tenant_id=tenant_id,
        code=f"SP-STK-{suffix}-B",
        name=f"Stocktake Part {suffix} B",
        unit="EA",
        is_serialized=False,
    )
    session.add_all([warehouse, spare_a, spare_b])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-STK-{suffix}",
        name=f"Stocktake Location {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    balance_a = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_a.id,
        lot_id=None,
        on_hand_quantity=Decimal("10.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    balance_b = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare_b.id,
        lot_id=None,
        on_hand_quantity=Decimal("4.0000"),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
    )
    session.add_all([balance_a, balance_b])
    session.flush()
    return warehouse, location, balance_a, balance_b


def _seed_stocktake(session, *, tenant_id: str, suffix: str):
    warehouse, location, balance_a, balance_b = _seed_scope(
        session,
        tenant_id=tenant_id,
        suffix=suffix,
    )
    stocktake = InventoryStocktake(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        status="DRAFT",
        snapshot_at=datetime.now(timezone.utc),
        actor_user_id="user-a",
        actor_roles_json=["contributor"],
        request_id=f"request-{suffix}",
    )
    session.add(stocktake)
    session.flush()

    first = InventoryStocktakeLine(
        tenant_id=tenant_id,
        stocktake_id=stocktake.id,
        balance_id=balance_b.id,
        spare_part_id=balance_b.spare_part_id,
        lot_id=balance_b.lot_id,
        serial_item_id=None,
        system_quantity=balance_b.on_hand_quantity,
        counted_quantity=None,
        variance_quantity=None,
        snapshot_balance_version=balance_b.version,
        resolution="PENDING",
    )
    second = InventoryStocktakeLine(
        tenant_id=tenant_id,
        stocktake_id=stocktake.id,
        balance_id=balance_a.id,
        spare_part_id=balance_a.spare_part_id,
        lot_id=balance_a.lot_id,
        serial_item_id=None,
        system_quantity=balance_a.on_hand_quantity,
        counted_quantity=None,
        variance_quantity=None,
        snapshot_balance_version=balance_a.version,
        resolution="PENDING",
    )
    session.add_all([first, second])
    session.flush()
    return stocktake, first, second


def test_stocktake_repository_get_is_tenant_scoped(session) -> None:
    repository = _repository_class()()
    stocktake, _, _ = _seed_stocktake(
        session,
        tenant_id="tenant-a",
        suffix="REPO-GET",
    )

    visible = repository.get(
        session,
        "tenant-a",
        stocktake.id,
    )
    hidden = repository.get(
        session,
        "tenant-b",
        stocktake.id,
    )

    assert visible is not None
    assert visible.id == stocktake.id
    assert hidden is None


def test_stocktake_repository_lock_is_tenant_scoped(session) -> None:
    repository = _repository_class()()
    stocktake, _, _ = _seed_stocktake(
        session,
        tenant_id="tenant-a",
        suffix="REPO-LOCK",
    )

    visible = repository.lock(
        session,
        "tenant-a",
        stocktake.id,
    )
    hidden = repository.lock(
        session,
        "tenant-b",
        stocktake.id,
    )

    assert visible is not None
    assert visible.id == stocktake.id
    assert hidden is None


def test_stocktake_repository_lists_lines_in_stable_id_order(session) -> None:
    repository = _repository_class()()
    stocktake, first, second = _seed_stocktake(
        session,
        tenant_id="tenant-a",
        suffix="REPO-LINES",
    )

    lines = repository.list_lines(
        session,
        "tenant-a",
        stocktake.id,
    )

    assert [line.id for line in lines] == sorted(
        [first.id, second.id]
    )

def test_slice2_stocktake_repository_lock_line_is_tenant_scoped(session) -> None:
    repository = _repository_class()()
    stocktake, first, _ = _seed_stocktake(
        session,
        tenant_id="tenant-a",
        suffix="REPO-LINE-LOCK",
    )

    visible = repository.lock_line(
        session,
        "tenant-a",
        stocktake.id,
        first.id,
    )
    hidden = repository.lock_line(
        session,
        "tenant-b",
        stocktake.id,
        first.id,
    )

    assert visible is not None
    assert visible.id == first.id
    assert hidden is None

def test_slice3_stocktake_repository_lists_unresolved_lines_stably_and_tenant_scoped(
    session,
) -> None:
    repository = _repository_class()()
    stocktake, first, second = _seed_stocktake(
        session,
        tenant_id="tenant-a",
        suffix="REPO-UNRESOLVED",
    )
    first.resolution = "CONFLICTED"
    second.resolution = "PENDING"
    session.flush()

    visible = repository.list_unresolved_lines(
        session,
        "tenant-a",
        stocktake.id,
    )
    hidden = repository.list_unresolved_lines(
        session,
        "tenant-b",
        stocktake.id,
    )

    assert [line.id for line in visible] == sorted(
        [first.id, second.id]
    )
    assert hidden == []

class _ClosureStabilizationScalarResult:
    def all(self):
        return []


class _ClosureStabilizationStatementCapture:
    def __init__(self) -> None:
        self.statement = None

    def scalars(self, statement):
        self.statement = statement
        return _ClosureStabilizationScalarResult()


def test_closure_stabilization_scope_balances_are_locked_in_stable_order() -> None:
    repository = _repository_class()()
    session = _ClosureStabilizationStatementCapture()

    balances = repository.list_scope_balances(
        session,
        "tenant-a",
        warehouse_id=11,
        location_id=22,
    )

    assert balances == []
    assert session.statement is not None

    compiled = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert "ORDER BY INVENTORY_BALANCES.ID" in compiled
    assert "FOR UPDATE" in compiled
