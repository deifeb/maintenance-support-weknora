from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryPolicy,
    InventoryReservation,
    InventoryStocktake,
    InventoryTransaction,
    InventoryTransfer,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.services.inventory_query_service import (
    InventoryQueryService,
    inventory_query_service,
)
from sqlalchemy import event, select


def seed_balance(
    session,
    *,
    tenant_id: str,
    suffix: str,
    warehouse: Warehouse | None = None,
    part: SparePart | None = None,
    on_hand: str = "8",
    reserved: str = "0",
    damaged: str = "0",
    quarantined: str = "0",
    in_transit: str = "0",
    with_serial: bool = False,
) -> tuple[InventoryBalance, SerializedItem | None]:
    warehouse = warehouse or Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    part = part or SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()
    lot = None
    if with_serial:
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=part.id,
            lot_code=f"LOT-{suffix}",
        )
        session.add(lot)
        session.flush()
    if session.scalar(
        select(InventoryPolicy.id).where(
            InventoryPolicy.tenant_id == tenant_id,
            InventoryPolicy.warehouse_id == warehouse.id,
            InventoryPolicy.spare_part_id == part.id,
        )
    ) is None:
        session.add(
            InventoryPolicy(
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                spare_part_id=part.id,
                safety_stock=Decimal("2"),
                reorder_point=Decimal("4"),
                maximum_stock=Decimal("12"),
            )
        )
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=part.id,
        lot_id=lot.id if lot else None,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        damaged_quantity=Decimal(damaged),
        quarantined_quantity=Decimal(quarantined),
        in_transit_quantity=Decimal(in_transit),
    )
    session.add(balance)
    session.flush()
    serial = None
    if with_serial:
        serial = SerializedItem(
            tenant_id=tenant_id,
            spare_part_id=part.id,
            serial_number=f"SER-{suffix}",
            lot_id=lot.id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            status="IN_STOCK",
        )
        session.add(serial)
        session.flush()
    return balance, serial


def test_summary_aggregates_only_actor_tenant(session, actor_context) -> None:
    seed_balance(session, tenant_id="tenant-a", suffix="A", on_hand="8")
    seed_balance(session, tenant_id="tenant-b", suffix="B", on_hand="99")

    page = inventory_query_service.list_summaries(
        session,
        actor_context(tenant_id="tenant-a"),
        page=1,
        page_size=20,
    )

    assert page.total == 1
    assert page.pages == 1
    assert page.items[0].on_hand_quantity == Decimal("8")


def test_summary_aggregates_balance_quantities_and_legacy_policy(session, actor_context) -> None:
    warehouse = Warehouse(tenant_id="tenant-a", code="WH-AGG", name="Aggregate")
    part = SparePart(tenant_id="tenant-a", code="SP-AGG", name="Aggregate part")
    first, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="AGG-ONE",
        warehouse=warehouse,
        part=part,
        on_hand="8",
        reserved="1",
        damaged="2",
        quarantined="1",
        in_transit="3",
    )
    second, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="AGG-TWO",
        warehouse=warehouse,
        part=part,
        on_hand="5",
        reserved="1",
        damaged="0",
        quarantined="0",
        in_transit="2",
    )

    page = inventory_query_service.list_summaries(
        session,
        actor_context(),
        page=1,
        page_size=20,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
    )

    assert page.total == 1
    summary = page.items[0]
    assert second.warehouse_id == summary.warehouse_id
    assert summary.on_hand_quantity == Decimal("13")
    assert summary.reserved_quantity == Decimal("2")
    assert summary.damaged_quantity == Decimal("2")
    assert summary.quarantined_quantity == Decimal("1")
    assert summary.in_transit_quantity == Decimal("5")
    assert summary.available_quantity == Decimal("8")
    assert summary.safety_stock == Decimal("2")
    assert summary.reorder_point == Decimal("4")
    assert summary.maximum_stock == Decimal("12")


def test_balance_page_filters_by_serial_and_paginates(session, actor_context) -> None:
    first, serial = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="SERIAL",
        with_serial=True,
    )
    second, _ = seed_balance(session, tenant_id="tenant-a", suffix="SECOND")
    seed_balance(session, tenant_id="tenant-b", suffix="OTHER")

    page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
        location_id=first.location_id,
        lot_id=first.lot_id,
        serial_item_id=serial.id,
    )

    assert second.id != first.id
    assert page.total == 1
    assert page.pages == 1
    assert page.items[0].id == first.id
    assert page.items[0].serial_item_ids == [serial.id]
    assert page.items[0].available_quantity == Decimal("8")
    assert page.items[0].version == 1


class _RecordingSummaryRepository:
    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def summaries_for_parts(
        self,
        _session,
        _tenant_id: str,
        spare_part_ids,
    ) -> list[dict]:
        self.calls.append(list(spare_part_ids))
        return []


def test_summaries_for_parts_short_circuits_empty_ids(
    session,
    actor_context,
) -> None:
    repository = _RecordingSummaryRepository()
    service = InventoryQueryService(repository)

    assert service.summaries_for_parts(session, actor_context(), []) == []
    assert repository.calls == []


def test_summaries_for_parts_chunks_large_deduplicated_id_sets(
    session,
    actor_context,
) -> None:
    repository = _RecordingSummaryRepository()
    service = InventoryQueryService(repository)
    requested_ids = list(range(1201, 0, -1)) + [1, 500, 1201]

    assert service.summaries_for_parts(
        session,
        actor_context(),
        requested_ids,
    ) == []

    assert [len(chunk) for chunk in repository.calls] == [500, 500, 201]
    assert [item for chunk in repository.calls for item in chunk] == list(
        range(1, 1202)
    )


def test_summaries_for_parts_returns_stable_warehouse_part_order(
    session,
    actor_context,
) -> None:
    first, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="ORDER-FIRST",
    )
    second, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="ORDER-SECOND",
    )
    session.commit()

    summaries = inventory_query_service.summaries_for_parts(
        session,
        actor_context(),
        [second.spare_part_id, first.spare_part_id, second.spare_part_id],
    )

    assert [
        (summary.warehouse_id, summary.spare_part_id)
        for summary in summaries
    ] == sorted(
        (
            (first.warehouse_id, first.spare_part_id),
            (second.warehouse_id, second.spare_part_id),
        )
    )


def test_low_stock_count_is_active_tenant_scoped_and_one_statement(
    session,
    actor_context,
) -> None:
    active_warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-RISK-ACTIVE",
        name="Active warehouse",
    )
    active_part = SparePart(
        tenant_id="tenant-a",
        code="SP-RISK-ACTIVE",
        name="Active part",
    )
    seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RISK-ACTIVE-ONE",
        warehouse=active_warehouse,
        part=active_part,
        on_hand="1",
    )
    seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RISK-ACTIVE-TWO",
        warehouse=active_warehouse,
        part=active_part,
        on_hand="1",
    )

    inactive_warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-RISK-INACTIVE",
        name="Inactive warehouse",
        is_active=False,
    )
    seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RISK-INACTIVE-WH",
        warehouse=inactive_warehouse,
        on_hand="0",
    )
    inactive_part = SparePart(
        tenant_id="tenant-a",
        code="SP-RISK-INACTIVE",
        name="Inactive part",
        is_active=False,
    )
    seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="RISK-INACTIVE-PART",
        part=inactive_part,
        on_hand="0",
    )
    seed_balance(
        session,
        tenant_id="tenant-b",
        suffix="RISK-FOREIGN",
        on_hand="0",
    )
    session.commit()

    inventory_statements: list[str] = []

    def count_inventory_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if "FROM inventory_balances" in statement:
            inventory_statements.append(statement)

    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        count_inventory_statement,
    )
    try:
        count = inventory_query_service.count_low_stock_spare_parts(
            session,
            actor_context(),
        )
    finally:
        event.remove(
            session.get_bind(),
            "before_cursor_execute",
            count_inventory_statement,
        )

    assert count == 1
    assert len(inventory_statements) == 1


def seed_transaction(
    session,
    *,
    tenant_id: str,
    suffix: str,
    operation_type: str,
    status: str,
    reference_type: str | None,
    reference_id: str | None,
    completed_at: datetime | None,
) -> InventoryTransaction:
    row = InventoryTransaction(
        tenant_id=tenant_id,
        operation_type=operation_type,
        status=status,
        idempotency_key=f"query-contract-{suffix}",
        request_hash=(suffix.encode("utf-8").hex() + "0" * 64)[:64],
        reference_type=reference_type,
        reference_id=reference_id,
        reason=f"Task 10.5 query contract {suffix}",
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        completed_at=completed_at,
    )
    session.add(row)
    session.flush()
    return row


def seed_reservation(
    session,
    *,
    tenant_id: str,
    suffix: str,
    status: str,
    owner_type: str,
    owner_id: str,
    expires_at: datetime | None,
) -> InventoryReservation:
    row = InventoryReservation(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        status=status,
        expires_at=expires_at,
        allow_partial=False,
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
    )
    session.add(row)
    session.flush()
    return row


def seed_transfer_parent(
    session,
    *,
    tenant_id: str,
    suffix: str,
    source: InventoryBalance,
    target: InventoryBalance,
    status: str,
    reference_type: str | None,
    reference_id: str | None,
    dispatched_at: datetime | None,
    completed_at: datetime | None,
) -> InventoryTransfer:
    row = InventoryTransfer(
        tenant_id=tenant_id,
        status=status,
        source_warehouse_id=source.warehouse_id,
        source_location_id=source.location_id,
        target_warehouse_id=target.warehouse_id,
        target_location_id=target.location_id,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=f"Task 10.5 transfer {suffix}",
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        dispatched_at=dispatched_at,
        completed_at=completed_at,
    )
    session.add(row)
    session.flush()
    return row


def seed_stocktake_parent(
    session,
    *,
    tenant_id: str,
    suffix: str,
    balance: InventoryBalance,
    status: str,
    snapshot_at: datetime,
    confirmed_at: datetime | None,
) -> InventoryStocktake:
    row = InventoryStocktake(
        tenant_id=tenant_id,
        warehouse_id=balance.warehouse_id,
        location_id=balance.location_id,
        status=status,
        snapshot_at=snapshot_at,
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        confirmed_at=confirmed_at,
    )
    session.add(row)
    session.flush()
    return row


def test_balance_query_contract_filters_and_sorts_before_pagination(
    session,
    actor_context,
) -> None:
    first, first_serial = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-1",
        on_hand="9",
        reserved="4",
        with_serial=True,
    )
    second, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-2",
        on_hand="8",
        reserved="1",
    )
    seed_balance(
        session,
        tenant_id="tenant-b",
        suffix="Q-BAL-FOREIGN",
        on_hand="100",
        reserved="0",
    )
    session.commit()

    assert first_serial is not None
    filtered = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
        location_id=first.location_id,
        lot_id=first.lot_id,
        serial_item_id=first_serial.id,
        sort_by="available_quantity",
        sort_order="desc",
    )

    assert second.id != first.id
    assert filtered.total == 1
    assert filtered.pages == 1
    assert [item.id for item in filtered.items] == [first.id]


def test_balance_query_contract_available_quantity_sort_precedes_page(
    session,
    actor_context,
) -> None:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-Q-BAL-SORT",
        name="Task 10.5 balance sort warehouse",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code="SP-Q-BAL-SORT",
        name="Task 10.5 balance sort part",
    )
    lower, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-LOW",
        warehouse=warehouse,
        part=part,
        on_hand="5",
        reserved="4",
    )
    higher, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-HIGH",
        warehouse=warehouse,
        part=part,
        on_hand="9",
        reserved="1",
    )
    session.commit()

    first_page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=warehouse.id,
        spare_part_id=part.id,
        sort_by="available_quantity",
        sort_order="desc",
    )
    second_page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=2,
        page_size=1,
        warehouse_id=warehouse.id,
        spare_part_id=part.id,
        sort_by="available_quantity",
        sort_order="desc",
    )

    assert first_page.total == second_page.total == 2
    assert [item.id for item in first_page.items] == [higher.id]
    assert [item.id for item in second_page.items] == [lower.id]


def test_transaction_query_contract_filters_before_count_and_page(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    matching = [
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"FAILED-{index}",
            operation_type="ADJUST",
            status="FAILED",
            reference_type="WORK_ORDER",
            reference_id="WO-10.5",
            completed_at=base + timedelta(minutes=index),
        )
        for index in range(3)
    ]
    for index in range(7):
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"OTHER-{index}",
            operation_type="RESERVE",
            status="COMPLETED",
            reference_type="MANUAL",
            reference_id=f"OTHER-{index}",
            completed_at=base + timedelta(hours=1, minutes=index),
        )
    seed_transaction(
        session,
        tenant_id="tenant-b",
        suffix="FOREIGN-FAILED",
        operation_type="ADJUST",
        status="FAILED",
        reference_type="WORK_ORDER",
        reference_id="WO-10.5",
        completed_at=base,
    )
    session.commit()

    page = inventory_query_service.list_transactions(
        session,
        actor_context(),
        page=2,
        page_size=2,
        operation_type="ADJUST",
        status="FAILED",
        reference_type="WORK_ORDER",
        reference_id="WO-10.5",
        sort_by="id",
        sort_order="asc",
    )

    assert page.total == 3
    assert page.pages == 2
    assert [item.id for item in page.items] == [matching[2].id]


def test_transaction_query_contract_stable_tie_break_follows_sort_direction(
    session,
    actor_context,
) -> None:
    rows = [
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"TIE-{index}",
            operation_type="RESERVE",
            status="COMPLETED",
            reference_type="MANUAL",
            reference_id=f"TIE-{index}",
            completed_at=None,
        )
        for index in range(3)
    ]
    session.commit()

    ids = []
    for page_number in (1, 2, 3):
        page = inventory_query_service.list_transactions(
            session,
            actor_context(),
            page=page_number,
            page_size=1,
            status="COMPLETED",
            sort_by="status",
            sort_order="desc",
        )
        ids.extend(item.id for item in page.items)

    assert ids == sorted((row.id for row in rows), reverse=True)


def test_transaction_query_contract_completed_at_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    early = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-EARLY",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT", completed_at=base,
    )
    late = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-LATE",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT",
        completed_at=base + timedelta(hours=1),
    )
    null_completed = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-NULL",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT", completed_at=None,
    )
    session.commit()

    asc_page = inventory_query_service.list_transactions(
        session, actor_context(), page=1, page_size=20,
        reference_id="TX-NULL-SORT", sort_by="completed_at", sort_order="asc",
    )
    desc_page = inventory_query_service.list_transactions(
        session, actor_context(), page=1, page_size=20,
        reference_id="TX-NULL-SORT", sort_by="completed_at", sort_order="desc",
    )

    assert [item.id for item in asc_page.items] == [early.id, late.id, null_completed.id]
    assert [item.id for item in desc_page.items] == [late.id, early.id, null_completed.id]


def test_reservation_query_contract_filters_and_keeps_null_expiry_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    early = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-EARLY",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base,
    )
    late = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-LATE",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base + timedelta(hours=1),
    )
    null_expiry = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-NULL",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=None,
    )
    seed_reservation(
        session,
        tenant_id="tenant-b",
        suffix="RES-FOREIGN",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base - timedelta(hours=1),
    )
    session.commit()

    asc_page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        sort_by="expires_at",
        sort_order="asc",
    )
    desc_page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        sort_by="expires_at",
        sort_order="desc",
    )

    assert [item.id for item in asc_page.items] == [early.id, late.id, null_expiry.id]
    assert [item.id for item in desc_page.items] == [late.id, early.id, null_expiry.id]
    assert asc_page.total == desc_page.total == 3


def test_inventory_list_default_order_remains_id_ascending(
    session,
    actor_context,
) -> None:
    rows = [
        seed_reservation(
            session,
            tenant_id="tenant-a",
            suffix=f"DEFAULT-{index}",
            status="ACTIVE",
            owner_type="MANUAL",
            owner_id=f"DEFAULT-{index}",
            expires_at=None,
        )
        for index in range(3)
    ]
    session.commit()

    page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
    )

    assert [item.id for item in page.items] == sorted(row.id for row in rows)


def test_transfer_query_contract_filters_and_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    source, _ = seed_balance(session, tenant_id="tenant-a", suffix="TR-SRC")
    target, _ = seed_balance(session, tenant_id="tenant-a", suffix="TR-DST")
    first = seed_transfer_parent(
        session,
        tenant_id="tenant-a",
        suffix="TR-FIRST",
        source=source,
        target=target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base,
        completed_at=base + timedelta(hours=1),
    )
    null_completed = seed_transfer_parent(
        session,
        tenant_id="tenant-a",
        suffix="TR-NULL",
        source=source,
        target=target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base + timedelta(minutes=1),
        completed_at=None,
    )
    foreign_source, _ = seed_balance(session, tenant_id="tenant-b", suffix="TR-FSRC")
    foreign_target, _ = seed_balance(session, tenant_id="tenant-b", suffix="TR-FDST")
    seed_transfer_parent(
        session,
        tenant_id="tenant-b",
        suffix="TR-FOREIGN",
        source=foreign_source,
        target=foreign_target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base - timedelta(hours=1),
        completed_at=base - timedelta(minutes=30),
    )
    session.commit()

    page = inventory_query_service.list_transfers(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="DISPATCHED",
        source_warehouse_id=source.warehouse_id,
        source_location_id=source.location_id,
        target_warehouse_id=target.warehouse_id,
        target_location_id=target.location_id,
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        sort_by="completed_at",
        sort_order="asc",
    )

    assert page.total == 2
    assert [item.id for item in page.items] == [first.id, null_completed.id]


def test_stocktake_query_contract_filters_and_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    balance, _ = seed_balance(session, tenant_id="tenant-a", suffix="STK")
    confirmed = seed_stocktake_parent(
        session,
        tenant_id="tenant-a",
        suffix="STK-CONFIRMED",
        balance=balance,
        status="CONFIRMED",
        snapshot_at=base,
        confirmed_at=base + timedelta(hours=1),
    )
    null_confirmed = seed_stocktake_parent(
        session,
        tenant_id="tenant-a",
        suffix="STK-NULL",
        balance=balance,
        status="CONFIRMED",
        snapshot_at=base + timedelta(minutes=1),
        confirmed_at=None,
    )
    foreign_balance, _ = seed_balance(session, tenant_id="tenant-b", suffix="STK-FOREIGN")
    seed_stocktake_parent(
        session,
        tenant_id="tenant-b",
        suffix="STK-FOREIGN",
        balance=foreign_balance,
        status="CONFIRMED",
        snapshot_at=base,
        confirmed_at=base,
    )
    session.commit()

    asc_page = inventory_query_service.list_stocktakes(
        session, actor_context(), page=1, page_size=20,
        status="CONFIRMED", warehouse_id=balance.warehouse_id,
        location_id=balance.location_id, sort_by="confirmed_at", sort_order="asc",
    )
    desc_page = inventory_query_service.list_stocktakes(
        session, actor_context(), page=1, page_size=20,
        status="CONFIRMED", warehouse_id=balance.warehouse_id,
        location_id=balance.location_id, sort_by="confirmed_at", sort_order="desc",
    )

    assert asc_page.total == desc_page.total == 2
    assert [item.id for item in asc_page.items] == [confirmed.id, null_confirmed.id]
    assert [item.id for item in desc_page.items] == [confirmed.id, null_confirmed.id]


def test_transfer_query_contract_dispatched_at_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    source, _ = seed_balance(session, tenant_id="tenant-a", suffix="TRD-SRC")
    target, _ = seed_balance(session, tenant_id="tenant-a", suffix="TRD-DST")
    dispatched = seed_transfer_parent(
        session, tenant_id="tenant-a", suffix="TRD-DISPATCHED",
        source=source, target=target, status="DRAFT",
        reference_type="MANUAL", reference_id="TRD-NULL-SORT",
        dispatched_at=base, completed_at=None,
    )
    null_dispatched = seed_transfer_parent(
        session, tenant_id="tenant-a", suffix="TRD-NULL",
        source=source, target=target, status="DRAFT",
        reference_type="MANUAL", reference_id="TRD-NULL-SORT",
        dispatched_at=None, completed_at=None,
    )
    session.commit()

    for sort_order in ("asc", "desc"):
        page = inventory_query_service.list_transfers(
            session, actor_context(), page=1, page_size=20,
            reference_id="TRD-NULL-SORT",
            sort_by="dispatched_at", sort_order=sort_order,
        )
        assert page.total == 2
        assert [item.id for item in page.items][-1] == null_dispatched.id
        assert dispatched.id in {item.id for item in page.items[:-1]}


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("list_transactions", {}),
        ("list_reservations", {}),
        ("list_transfers", {}),
        ("list_stocktakes", {}),
    ],
)
def test_inventory_query_service_rejects_unknown_sort_field(
    session,
    actor_context,
    method_name,
    kwargs,
) -> None:
    method = getattr(inventory_query_service, method_name)
    with pytest.raises(ValueError, match="unsupported sort_by"):
        method(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="tenant_id",
            sort_order="asc",
            **kwargs,
        )


@pytest.mark.parametrize(
    "method_name",
    ["list_transactions", "list_reservations", "list_transfers", "list_stocktakes"],
)
def test_inventory_query_service_rejects_unknown_sort_order(
    session,
    actor_context,
    method_name,
) -> None:
    method = getattr(inventory_query_service, method_name)
    with pytest.raises(ValueError, match="unsupported sort_order"):
        method(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="id",
            sort_order="sideways",
        )


def test_balance_query_service_rejects_unknown_sort_field(
    session,
    actor_context,
) -> None:
    with pytest.raises(ValueError, match="unsupported sort_by"):
        inventory_query_service.list_balances(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="tenant_id",
            sort_order="asc",
        )


def test_balance_query_service_rejects_unknown_sort_order(
    session,
    actor_context,
) -> None:
    with pytest.raises(ValueError, match="unsupported sort_order"):
        inventory_query_service.list_balances(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="id",
            sort_order="sideways",
        )
