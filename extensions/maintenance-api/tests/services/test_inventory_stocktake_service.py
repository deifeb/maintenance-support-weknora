from __future__ import annotations

import hashlib
import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from app.core.exceptions import (
    AppException,
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryStocktake,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.security.actor import ActorContext, MaintenanceRole
from sqlalchemy import func, select


def _service_class():
    module = importlib.import_module(
        "app.services.inventory_stocktake_service"
    )
    return module.InventoryStocktakeService


def _actor(
    *,
    tenant_id: str = "tenant-a",
    role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
) -> ActorContext:
    return ActorContext(
        user_id="user-a",
        tenant_id=tenant_id,
        role=role,
        request_id="request-stocktake",
        token_id="token-stocktake",
    )


def _seed_scope(
    session,
    *,
    tenant_id: str,
    suffix: str,
    quantities: tuple[str, ...] = ("10.0000", "4.0000"),
):
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-STK-SVC-{suffix}",
        name=f"Stocktake Warehouse {suffix}",
    )
    session.add(warehouse)
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-STK-SVC-{suffix}",
        name=f"Stocktake Location {suffix}",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    balances: list[InventoryBalance] = []
    for index, quantity in enumerate(quantities, start=1):
        spare_part = SparePart(
            tenant_id=tenant_id,
            code=f"SP-STK-SVC-{suffix}-{index}",
            name=f"Stocktake Part {suffix} {index}",
            unit="EA",
            is_serialized=False,
        )
        session.add(spare_part)
        session.flush()

        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare_part.id,
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

    return warehouse, location, balances


def _create_command(warehouse, location) -> dict[str, int]:
    return {
        "warehouse_id": warehouse.id,
        "location_id": location.id,
    }


def _quantity_snapshot(
    balances: list[InventoryBalance],
) -> dict[int, tuple[Decimal, Decimal, Decimal, Decimal, Decimal, int]]:
    return {
        balance.id: (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )
        for balance in balances
    }


def _transaction_count(session) -> int:
    return int(
        session.scalar(
            select(func.count(InventoryTransaction.id))
        )
        or 0
    )


def _ledger_count(session) -> int:
    return int(
        session.scalar(
            select(func.count(InventoryLedgerEntry.id))
        )
        or 0
    )


def test_create_snapshots_each_scope_balance_once_in_draft(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, balances = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CREATE-SNAPSHOT",
    )
    expected = {
        balance.id: (
            balance.on_hand_quantity,
            balance.version,
        )
        for balance in balances
    }

    result = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-create-snapshot",
    )

    assert result.status == "DRAFT"
    assert result.warehouse_id == warehouse.id
    assert result.location_id == location.id
    assert result.snapshot_at is not None
    assert len(result.lines) == len(balances)
    assert len({line.balance_id for line in result.lines}) == len(
        balances
    )
    assert [line.balance_id for line in result.lines] == sorted(
        balance.id for balance in balances
    )

    for line in result.lines:
        system_quantity, snapshot_version = expected[line.balance_id]
        assert line.system_quantity == system_quantity
        assert line.snapshot_balance_version == snapshot_version
        assert line.counted_quantity is None
        assert line.variance_quantity is None
        assert line.resolution == "PENDING"


def test_create_has_no_inventory_or_ledger_side_effect(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, balances = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CREATE-SIDE-EFFECT",
    )
    before_quantities = _quantity_snapshot(balances)
    before_transactions = _transaction_count(session)
    before_ledger = _ledger_count(session)

    service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-create-side-effect",
    )
    session.flush()

    for balance in balances:
        session.refresh(balance)

    assert _quantity_snapshot(balances) == before_quantities
    assert _transaction_count(session) == before_transactions
    assert _ledger_count(session) == before_ledger


def test_create_same_key_same_command_replays_without_duplicate(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, balances = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CREATE-REPLAY",
    )
    command = _create_command(warehouse, location)

    first = service.create(
        session,
        actor,
        command=command,
        idempotency_key="stocktake-create-replay",
    )
    second = service.create(
        session,
        actor,
        command=command,
        idempotency_key="stocktake-create-replay",
    )

    stocktake_count = int(
        session.scalar(
            select(func.count(InventoryStocktake.id)).where(
                InventoryStocktake.tenant_id == actor.tenant_id
            )
        )
        or 0
    )

    assert second == first
    assert stocktake_count == 1
    assert len(second.lines) == len(balances)


def test_create_same_key_changed_scope_is_rejected(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse_a, location_a, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CREATE-REUSE-A",
        quantities=("3.0000",),
    )
    warehouse_b, location_b, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CREATE-REUSE-B",
        quantities=("2.0000",),
    )

    service.create(
        session,
        actor,
        command=_create_command(warehouse_a, location_a),
        idempotency_key="stocktake-create-reused",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.create(
            session,
            actor,
            command=_create_command(warehouse_b, location_b),
            idempotency_key="stocktake-create-reused",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_start_moves_draft_to_counting_once_and_replays(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="START-REPLAY",
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-start-create",
    )

    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-start",
    )
    replayed = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-start",
    )

    assert started.status == "COUNTING"
    assert started.version == created.version + 1
    assert replayed == started

    persisted = session.get(InventoryStocktake, created.id)
    assert persisted is not None
    assert persisted.status == "COUNTING"
    assert persisted.version == started.version


def test_start_rejects_stale_stocktake_version(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="START-VERSION",
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-start-version-create",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.start(
            session,
            actor,
            created.id,
            expected_version=created.version + 1,
            idempotency_key="stocktake-start-stale",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"

def _persisted_stocktake(session, stocktake_id: int) -> InventoryStocktake:
    stocktake = session.get(InventoryStocktake, stocktake_id)
    assert stocktake is not None
    return stocktake


def _persisted_line(session, line_id: int):
    from app.models import InventoryStocktakeLine

    line = session.get(InventoryStocktakeLine, line_id)
    assert line is not None
    return line


def _force_status(session, stocktake_id: int, status: str) -> InventoryStocktake:
    stocktake = _persisted_stocktake(session, stocktake_id)
    stocktake.status = status
    session.flush()
    return stocktake


def _force_counted_lines(session, result) -> None:
    for result_line in result.lines:
        line = _persisted_line(session, result_line.id)
        line.counted_quantity = line.system_quantity
        line.variance_quantity = Decimal("0.0000")
    session.flush()


def _count_command(
    result,
    line,
    *,
    quantity: str,
    stocktake_version: int | None = None,
    line_version: int | None = None,
) -> dict[str, object]:
    return {
        "expected_version": (
            result.version if stocktake_version is None else stocktake_version
        ),
        "expected_line_version": (
            line.version if line_version is None else line_version
        ),
        "counted_quantity": quantity,
    }


@pytest.mark.parametrize(
    "role",
    [MaintenanceRole.CONTRIBUTOR, MaintenanceRole.ADMIN],
)
def test_slice2_record_count_allows_contributor_and_admin(
    session,
    role: MaintenanceRole,
) -> None:
    service = _service_class()()
    actor = _actor(role=role)
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix=f"COUNT-ROLE-{role.value}",
        quantities=("5.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key=f"stocktake-count-role-create-{role.value}",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key=f"stocktake-count-role-start-{role.value}",
    )
    line = started.lines[0]

    result = service.record_count(
        session,
        actor,
        started.id,
        line.id,
        command=_count_command(started, line, quantity="4.0000"),
        idempotency_key=f"stocktake-count-role-{role.value}",
    )

    assert result.status == "COUNTING"
    assert result.lines[0].counted_quantity == Decimal("4.0000")


def test_slice2_record_count_updates_counted_quantity_and_variance(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-VARIANCE",
        quantities=("10.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-variance-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-variance-start",
    )
    line = started.lines[0]

    result = service.record_count(
        session,
        actor,
        started.id,
        line.id,
        command=_count_command(started, line, quantity="7.5000"),
        idempotency_key="stocktake-count-variance",
    )

    updated = result.lines[0]
    assert updated.counted_quantity == Decimal("7.5000")
    assert updated.variance_quantity == Decimal("-2.5000")
    assert updated.version == line.version + 1
    assert result.version == started.version + 1


def test_slice2_record_count_requires_counting_status(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-STATE",
        quantities=("3.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-state-create",
    )
    line = created.lines[0]

    with pytest.raises(ConflictError) as exc_info:
        service.record_count(
            session,
            actor,
            created.id,
            line.id,
            command=_count_command(created, line, quantity="2.0000"),
            idempotency_key="stocktake-count-state",
        )

    assert exc_info.value.code == "INVENTORY_OPERATION_STATE_CONFLICT"


def test_slice2_record_count_checks_stocktake_version(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-STOCKTAKE-VERSION",
        quantities=("6.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-stocktake-version-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-stocktake-version-start",
    )
    line = started.lines[0]

    with pytest.raises(ConflictError) as exc_info:
        service.record_count(
            session,
            actor,
            started.id,
            line.id,
            command=_count_command(
                started,
                line,
                quantity="5.0000",
                stocktake_version=started.version + 1,
            ),
            idempotency_key="stocktake-count-stocktake-version",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"
    assert exc_info.value.details["conflict_object"] == "inventory_stocktake"


def test_slice2_record_count_checks_line_version(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-LINE-VERSION",
        quantities=("6.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-line-version-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-line-version-start",
    )
    line = started.lines[0]

    with pytest.raises(ConflictError) as exc_info:
        service.record_count(
            session,
            actor,
            started.id,
            line.id,
            command=_count_command(
                started,
                line,
                quantity="5.0000",
                line_version=line.version + 1,
            ),
            idempotency_key="stocktake-count-line-version",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"
    assert exc_info.value.details["conflict_object"] == "inventory_stocktake_line"


def test_slice2_record_count_is_tenant_scoped(session) -> None:
    service = _service_class()()
    actor_a = _actor(tenant_id="tenant-a")
    actor_b = _actor(tenant_id="tenant-b")
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor_a.tenant_id,
        suffix="COUNT-TENANT",
        quantities=("4.0000",),
    )
    created = service.create(
        session,
        actor_a,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-tenant-create",
    )
    started = service.start(
        session,
        actor_a,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-tenant-start",
    )
    line = started.lines[0]

    with pytest.raises(NotFoundError):
        service.record_count(
            session,
            actor_b,
            started.id,
            line.id,
            command=_count_command(started, line, quantity="3.0000"),
            idempotency_key="stocktake-count-tenant",
        )


def test_slice2_record_count_same_key_replays(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-REPLAY",
        quantities=("8.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-replay-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-replay-start",
    )
    line = started.lines[0]
    command = _count_command(started, line, quantity="7.0000")

    first = service.record_count(
        session,
        actor,
        started.id,
        line.id,
        command=command,
        idempotency_key="stocktake-count-replay",
    )
    second = service.record_count(
        session,
        actor,
        started.id,
        line.id,
        command=command,
        idempotency_key="stocktake-count-replay",
    )

    assert second == first
    persisted = _persisted_line(session, line.id)
    assert persisted.version == first.lines[0].version
    assert persisted.counted_quantity == Decimal("7.0000")


def test_slice2_record_count_same_key_changed_payload_is_rejected(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-KEY-REUSE",
        quantities=("8.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-key-reuse-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-key-reuse-start",
    )
    line = started.lines[0]

    service.record_count(
        session,
        actor,
        started.id,
        line.id,
        command=_count_command(started, line, quantity="7.0000"),
        idempotency_key="stocktake-count-key-reuse",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.record_count(
            session,
            actor,
            started.id,
            line.id,
            command=_count_command(started, line, quantity="6.0000"),
            idempotency_key="stocktake-count-key-reuse",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_slice2_record_count_rejects_adjusted_line(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="COUNT-ADJUSTED",
        quantities=("8.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-count-adjusted-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-count-adjusted-start",
    )
    line = _persisted_line(session, started.lines[0].id)
    line.resolution = "ADJUSTED"
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.record_count(
            session,
            actor,
            started.id,
            line.id,
            command={
                "expected_version": started.version,
                "expected_line_version": line.version,
                "counted_quantity": "8.0000",
            },
            idempotency_key="stocktake-count-adjusted",
        )

    assert exc_info.value.code == "STOCKTAKE_LINE_ALREADY_CONFIRMED"


def test_slice2_review_requires_all_unresolved_lines_counted(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="REVIEW-INCOMPLETE",
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-review-incomplete-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-review-incomplete-start",
    )
    first = _persisted_line(session, started.lines[0].id)
    first.counted_quantity = first.system_quantity
    first.variance_quantity = Decimal("0.0000")
    session.flush()

    with pytest.raises(BusinessValidationError):
        service.review(
            session,
            actor,
            started.id,
            expected_version=started.version,
            idempotency_key="stocktake-review-incomplete",
        )


def test_slice2_review_moves_counting_to_reviewing(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="REVIEW-TRANSITION",
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-review-transition-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-review-transition-start",
    )
    _force_counted_lines(session, started)

    result = service.review(
        session,
        actor,
        started.id,
        expected_version=started.version,
        idempotency_key="stocktake-review-transition",
    )

    assert result.status == "REVIEWING"
    assert result.version == started.version + 1


def test_slice2_review_checks_stocktake_version(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="REVIEW-VERSION",
        quantities=("2.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-review-version-create",
    )
    started = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="stocktake-review-version-start",
    )
    _force_counted_lines(session, started)

    with pytest.raises(ConflictError) as exc_info:
        service.review(
            session,
            actor,
            started.id,
            expected_version=started.version + 1,
            idempotency_key="stocktake-review-version",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"


@pytest.mark.parametrize("status", ["DRAFT", "COUNTING", "REVIEWING"])
def test_slice2_cancel_allows_preconfirmation_statuses(
    session,
    status: str,
) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix=f"CANCEL-{status}",
        quantities=("1.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key=f"stocktake-cancel-create-{status}",
    )
    stocktake = _force_status(session, created.id, status)
    expected_version = stocktake.version

    result = service.cancel(
        session,
        actor,
        created.id,
        expected_version=expected_version,
        idempotency_key=f"stocktake-cancel-{status}",
    )

    assert result.status == "CANCELLED"
    assert result.cancelled_at is not None
    assert result.version == expected_version + 1


def test_slice2_cancel_rejects_confirmed_stocktake(session) -> None:
    service = _service_class()()
    actor = _actor()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="CANCEL-CONFIRMED",
        quantities=("1.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="stocktake-cancel-confirmed-create",
    )
    stocktake = _force_status(session, created.id, "CONFIRMED")

    with pytest.raises(ConflictError) as exc_info:
        service.cancel(
            session,
            actor,
            created.id,
            expected_version=stocktake.version,
            idempotency_key="stocktake-cancel-confirmed",
        )

    assert exc_info.value.code == "INVENTORY_OPERATION_STATE_CONFLICT"

def _slice3_reviewed_stocktake(
    session,
    *,
    actor: ActorContext,
    suffix: str,
    quantities: tuple[str, ...] = ("10.0000", "4.0000"),
):
    service = _service_class()()
    warehouse, location, balances = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix=f"SLICE3-{suffix}",
        quantities=quantities,
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key=f"slice3-{suffix}-create",
    )
    current = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key=f"slice3-{suffix}-start",
    )

    for original_line in tuple(current.lines):
        current_line = next(
            line
            for line in current.lines
            if line.id == original_line.id
        )
        counted = (
            current_line.system_quantity
            - Decimal("1.0000")
        )
        current = service.record_count(
            session,
            actor,
            current.id,
            current_line.id,
            command={
                "expected_version": current.version,
                "expected_line_version": current_line.version,
                "counted_quantity": str(counted),
            },
            idempotency_key=(
                f"slice3-{suffix}-count-{current_line.id}"
            ),
        )

    reviewed = service.review(
        session,
        actor,
        current.id,
        expected_version=current.version,
        idempotency_key=f"slice3-{suffix}-review",
    )
    return service, balances, reviewed


def _slice3_preview_command(reviewed, *, expected_version: int | None = None):
    return {
        "expected_version": (
            reviewed.version
            if expected_version is None
            else expected_version
        ),
    }


def _slice3_transaction(session, transaction_id: int) -> InventoryTransaction:
    transaction = session.get(
        InventoryTransaction,
        transaction_id,
    )
    assert transaction is not None
    return transaction


def _slice3_private_preview_command(transaction: InventoryTransaction):
    snapshot = transaction.response_snapshot_json
    assert isinstance(snapshot, dict)
    extensions = snapshot.get("_extensions")
    assert isinstance(extensions, dict)
    preview_command = extensions.get("preview_command")
    assert isinstance(preview_command, dict)
    return preview_command


def test_slice3_preview_confirm_requires_admin(session) -> None:
    actor = _actor(role=MaintenanceRole.CONTRIBUTOR)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="ADMIN",
        quantities=("5.0000",),
    )

    with pytest.raises(InsufficientMaintenanceRoleError):
        service.preview_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice3_preview_command(reviewed),
            idempotency_key="slice3-preview-admin",
        )


def test_slice3_preview_confirm_requires_reviewing_state(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service = _service_class()()
    warehouse, location, _ = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix="SLICE3-STATE",
        quantities=("5.0000",),
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key="slice3-state-create",
    )
    counting = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key="slice3-state-start",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.preview_confirm(
            session,
            actor,
            counting.id,
            command=_slice3_preview_command(counting),
            idempotency_key="slice3-preview-state",
        )

    assert exc_info.value.code == "INVENTORY_OPERATION_STATE_CONFLICT"


def test_slice3_preview_confirm_checks_stocktake_version(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="VERSION",
        quantities=("5.0000",),
    )

    with pytest.raises(ConflictError) as exc_info:
        service.preview_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice3_preview_command(
                reviewed,
                expected_version=reviewed.version + 1,
            ),
            idempotency_key="slice3-preview-version",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"


def test_slice3_preview_confirm_is_tenant_scoped(session) -> None:
    actor_a = _actor(
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
    )
    actor_b = _actor(
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
    )
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor_a,
        suffix="TENANT",
        quantities=("5.0000",),
    )

    with pytest.raises(NotFoundError):
        service.preview_confirm(
            session,
            actor_b,
            reviewed.id,
            command=_slice3_preview_command(reviewed),
            idempotency_key="slice3-preview-tenant",
        )


def test_slice3_preview_confirm_orders_only_unresolved_lines_stably(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="ORDER",
        quantities=("7.0000", "5.0000", "3.0000"),
    )
    middle = _persisted_line(session, reviewed.lines[1].id)
    middle.resolution = "ADJUSTED"
    session.flush()

    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice3-preview-order",
    )

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    private_command = _slice3_private_preview_command(
        transaction
    )
    line_payloads = private_command["lines"]
    line_ids = [
        item["stocktake_line_id"]
        for item in line_payloads
    ]
    expected_ids = sorted(
        [
            reviewed.lines[0].id,
            reviewed.lines[2].id,
        ]
    )

    assert line_ids == expected_ids
    assert middle.id not in line_ids
    assert [
        item["balance_id"]
        for item in line_payloads
    ] == [
        next(
            line.balance_id
            for line in reviewed.lines
            if line.id == line_id
        )
        for line_id in expected_ids
    ]


def test_slice3_preview_confirm_persists_preview_transaction_and_token_contract(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="TOKEN",
        quantities=("5.0000",),
    )

    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice3-preview-token",
    )

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert preview.operation_type == "STOCKTAKE_CONFIRM"
    assert preview.status == "PREVIEWED"
    assert transaction.operation_type == "STOCKTAKE_CONFIRM"
    assert transaction.status == "PREVIEWED"
    assert transaction.completed_at is None
    assert preview.transaction_version == transaction.version

    token = preview.confirmation_token
    assert isinstance(token, str)
    assert token
    assert transaction.confirmation_token_hash == hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()
    assert transaction.confirmation_token_hash != token
    assert preview.confirmation_expires_at is not None
    persisted_expiry = transaction.confirmation_expires_at
    assert persisted_expiry is not None
    if persisted_expiry.tzinfo is None:
        persisted_expiry = persisted_expiry.replace(
            tzinfo=preview.confirmation_expires_at.tzinfo
        )
    assert preview.confirmation_expires_at == persisted_expiry


def test_slice3_preview_confirm_stores_public_snapshot_and_private_command(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="SNAPSHOT",
        quantities=("5.0000",),
    )

    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice3-preview-snapshot",
    )
    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )

    snapshot = transaction.response_snapshot_json
    assert isinstance(snapshot, dict)
    assert snapshot["transaction_id"] == preview.transaction_id
    assert snapshot["operation_type"] == "STOCKTAKE_CONFIRM"
    assert snapshot["status"] == "PREVIEWED"
    assert snapshot["transaction_version"] == preview.transaction_version
    assert snapshot["confirmation_token"] is None
    assert preview.confirmation_token not in str(snapshot)

    private_command = _slice3_private_preview_command(
        transaction
    )
    assert private_command["operation_type"] == "STOCKTAKE_CONFIRM"
    assert private_command["stocktake_id"] == reviewed.id
    assert private_command["expected_version"] == reviewed.version

    public_payload = preview.model_dump(mode="json")
    assert "_extensions" not in public_payload
    assert "preview_command" not in public_payload


def test_slice3_preview_confirm_same_key_replays_without_plaintext_token(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="REPLAY",
        quantities=("5.0000",),
    )
    command = _slice3_preview_command(reviewed)

    first = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=command,
        idempotency_key="slice3-preview-replay",
    )
    replay = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=command,
        idempotency_key="slice3-preview-replay",
    )

    assert replay.transaction_id == first.transaction_id
    assert replay.transaction_version == first.transaction_version
    assert first.confirmation_token
    assert replay.confirmation_token is None
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == 0


def test_slice3_preview_confirm_same_key_changed_payload_is_rejected(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="KEY-REUSE",
        quantities=("5.0000",),
    )

    service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice3-preview-key-reuse",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.preview_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice3_preview_command(
                reviewed,
                expected_version=reviewed.version + 1,
            ),
            idempotency_key="slice3-preview-key-reuse",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_slice3_preview_confirm_has_no_inventory_or_stocktake_side_effects(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed = _slice3_reviewed_stocktake(
        session,
        actor=actor,
        suffix="NO-SIDE-EFFECT",
        quantities=("9.0000", "6.0000"),
    )

    balance_state = {
        balance.id: (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )
        for balance in balances
    }
    stocktake_before = _persisted_stocktake(
        session,
        reviewed.id,
    )
    stocktake_state = (
        stocktake_before.status,
        stocktake_before.version,
        stocktake_before.confirmed_at,
        stocktake_before.cancelled_at,
    )
    line_state = {
        line.id: (
            line.counted_quantity,
            line.variance_quantity,
            line.resolution,
            line.version,
            line.confirmed_transaction_id,
        )
        for line in (
            _persisted_line(session, item.id)
            for item in reviewed.lines
        )
    }
    ledger_before = session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    )
    transaction_before = session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    )

    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice3-preview-no-side-effect",
    )

    assert preview.status == "PREVIEWED"
    for balance in balances:
        session.refresh(balance)
        assert balance_state[balance.id] == (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )

    stocktake_after = _persisted_stocktake(
        session,
        reviewed.id,
    )
    assert stocktake_state == (
        stocktake_after.status,
        stocktake_after.version,
        stocktake_after.confirmed_at,
        stocktake_after.cancelled_at,
    )
    assert stocktake_after.status == "REVIEWING"

    for item in reviewed.lines:
        line = _persisted_line(session, item.id)
        assert line_state[line.id] == (
            line.counted_quantity,
            line.variance_quantity,
            line.resolution,
            line.version,
            line.confirmed_transaction_id,
        )

    assert session.scalar(
        select(func.count()).select_from(InventoryLedgerEntry)
    ) == ledger_before
    assert session.scalar(
        select(func.count()).select_from(InventoryTransaction)
    ) == transaction_before + 1

def _slice4_reviewed_stocktake(
    session,
    *,
    actor: ActorContext,
    suffix: str,
    quantities: tuple[str, ...] = ("10.0000", "4.0000"),
    count_offsets: tuple[str, ...] | None = None,
):
    service = _service_class()()
    warehouse, location, balances = _seed_scope(
        session,
        tenant_id=actor.tenant_id,
        suffix=f"SLICE4-{suffix}",
        quantities=quantities,
    )
    created = service.create(
        session,
        actor,
        command=_create_command(warehouse, location),
        idempotency_key=f"slice4-{suffix}-create",
    )
    current = service.start(
        session,
        actor,
        created.id,
        expected_version=created.version,
        idempotency_key=f"slice4-{suffix}-start",
    )

    offsets = count_offsets or tuple(
        "-1.0000"
        for _ in current.lines
    )
    assert len(offsets) == len(current.lines)

    for index, original_line in enumerate(tuple(current.lines)):
        current_line = next(
            line
            for line in current.lines
            if line.id == original_line.id
        )
        counted = (
            current_line.system_quantity
            + Decimal(offsets[index])
        )
        current = service.record_count(
            session,
            actor,
            current.id,
            current_line.id,
            command={
                "expected_version": current.version,
                "expected_line_version": current_line.version,
                "counted_quantity": str(counted),
            },
            idempotency_key=(
                f"slice4-{suffix}-count-{current_line.id}"
            ),
        )

    reviewed = service.review(
        session,
        actor,
        current.id,
        expected_version=current.version,
        idempotency_key=f"slice4-{suffix}-review",
    )
    return service, balances, reviewed


def _slice4_preview(
    session,
    *,
    actor: ActorContext,
    suffix: str,
    quantities: tuple[str, ...] = ("10.0000", "4.0000"),
    count_offsets: tuple[str, ...] | None = None,
):
    service, balances, reviewed = _slice4_reviewed_stocktake(
        session,
        actor=actor,
        suffix=suffix,
        quantities=quantities,
        count_offsets=count_offsets,
    )
    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key=f"slice4-{suffix}-preview",
    )
    return service, balances, reviewed, preview


def _slice4_execute_command(
    preview,
    *,
    confirmation_token: str | None = None,
    expected_transaction_version: int | None = None,
) -> dict[str, object]:
    token = (
        preview.confirmation_token
        if confirmation_token is None
        else confirmation_token
    )
    assert token is not None
    return {
        "transaction_id": preview.transaction_id,
        "expected_transaction_version": (
            preview.transaction_version
            if expected_transaction_version is None
            else expected_transaction_version
        ),
        "confirmation_token": token,
    }


def _slice4_transaction_entry_count(
    session,
    transaction_id: int,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.transaction_id
                == transaction_id
            )
        )
        or 0
    )


def _slice4_line_by_balance(session, reviewed, balance_id: int):
    result_line = next(
        line
        for line in reviewed.lines
        if line.balance_id == balance_id
    )
    return _persisted_line(session, result_line.id)


def _slice4_assert_transaction_still_previewed(
    session,
    transaction_id: int,
) -> None:
    transaction = _slice3_transaction(
        session,
        transaction_id,
    )
    assert transaction.status == "PREVIEWED"
    assert transaction.completed_at is None
    assert _slice4_transaction_entry_count(
        session,
        transaction_id,
    ) == 0


class _Slice4RecordingLedgerRepository:
    def __init__(self) -> None:
        from app.repositories.inventory_ledger_repository import (
            InventoryLedgerRepository,
        )

        self._inner = InventoryLedgerRepository()
        self.lock_calls: list[list[int]] = []

    def lock_balances(
        self,
        session,
        tenant_id: str,
        balance_ids,
    ):
        ids = list(balance_ids)
        self.lock_calls.append(ids)
        return self._inner.lock_balances(
            session,
            tenant_id,
            ids,
        )

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def test_slice4_execute_confirm_requires_admin(session) -> None:
    actor_admin = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor_admin,
        suffix="ADMIN",
        quantities=("5.0000",),
    )
    contributor = _actor(role=MaintenanceRole.CONTRIBUTOR)

    with pytest.raises(InsufficientMaintenanceRoleError):
        service.execute_confirm(
            session,
            contributor,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-admin",
        )

    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_checks_transaction_version(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="TX-VERSION",
        quantities=("5.0000",),
    )
    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    transaction.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-tx-version",
        )

    assert exc_info.value.code == "INVENTORY_TRANSACTION_VERSION_CONFLICT"
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == 0


def test_slice4_execute_confirm_rejects_invalid_token(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="TOKEN",
        quantities=("5.0000",),
    )

    with pytest.raises(AppException) as exc_info:
        service.execute_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice4_execute_command(
                preview,
                confirmation_token="wrong-stocktake-token",
            ),
            idempotency_key="slice4-execute-token",
        )

    assert exc_info.value.code == "INVENTORY_CONFIRMATION_TOKEN_INVALID"
    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_rejects_expired_token(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="EXPIRED",
        quantities=("5.0000",),
    )
    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert transaction.confirmation_expires_at is not None
    transaction.confirmation_expires_at = (
        transaction.confirmation_expires_at
        - timedelta(hours=1)
    )
    session.flush()

    with pytest.raises(AppException) as exc_info:
        service.execute_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-expired",
        )

    assert exc_info.value.code == "INVENTORY_CONFIRMATION_EXPIRED"
    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_rereads_reviewing_stocktake_state(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="STATE-REREAD",
        quantities=("5.0000",),
    )
    stocktake = _persisted_stocktake(
        session,
        reviewed.id,
    )
    stocktake.status = "COUNTING"
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-state-reread",
        )

    assert exc_info.value.code == "INVENTORY_OPERATION_STATE_CONFLICT"
    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_rereads_stocktake_version(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="STOCKTAKE-VERSION",
        quantities=("5.0000",),
    )
    stocktake = _persisted_stocktake(
        session,
        reviewed.id,
    )
    stocktake.version += 1
    session.flush()

    with pytest.raises(ConflictError) as exc_info:
        service.execute_confirm(
            session,
            actor,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-stocktake-version",
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"
    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_is_tenant_scoped(session) -> None:
    actor_a = _actor(
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
    )
    actor_b = _actor(
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
    )
    service, _, reviewed, preview = _slice4_preview(
        session,
        actor=actor_a,
        suffix="TENANT",
        quantities=("5.0000",),
    )

    with pytest.raises(NotFoundError):
        service.execute_confirm(
            session,
            actor_b,
            reviewed.id,
            command=_slice4_execute_command(preview),
            idempotency_key="slice4-execute-tenant",
        )

    _slice4_assert_transaction_still_previewed(
        session,
        preview.transaction_id,
    )


def test_slice4_execute_confirm_locks_balances_in_stable_id_order(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed = _slice4_reviewed_stocktake(
        session,
        actor=actor,
        suffix="LOCK-ORDER",
        quantities=("5.0000", "5.0000", "5.0000"),
    )
    persisted_lines = [
        _persisted_line(session, item.id)
        for item in reviewed.lines
    ]
    persisted_lines[0].balance_id = balances[2].id
    persisted_lines[2].balance_id = balances[0].id
    session.flush()

    preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice4-lock-order-preview",
    )
    recording = _Slice4RecordingLedgerRepository()
    service.ledger_repository = recording

    service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key="slice4-lock-order-execute",
    )

    assert recording.lock_calls
    assert all(
        ids == sorted(ids)
        for ids in recording.lock_calls
    )
    assert sorted(
        {
            balance.id
            for balance in balances
        }
    ) in recording.lock_calls


def test_slice4_partial_confirm_adjusts_success_and_persists_conflict(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="PARTIAL",
    )
    success_balance, conflict_balance = balances
    success_before = success_balance.on_hand_quantity
    conflict_before = conflict_balance.on_hand_quantity

    conflict_balance.version += 1
    session.flush()
    conflict_actual_version = conflict_balance.version

    result = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key="slice4-execute-partial",
    )

    session.refresh(success_balance)
    session.refresh(conflict_balance)
    assert success_balance.on_hand_quantity == (
        success_before - Decimal("1.0000")
    )
    assert conflict_balance.on_hand_quantity == conflict_before

    success_line = _slice4_line_by_balance(
        session,
        reviewed,
        success_balance.id,
    )
    conflict_line = _slice4_line_by_balance(
        session,
        reviewed,
        conflict_balance.id,
    )
    assert success_line.resolution == "ADJUSTED"
    assert success_line.confirmed_transaction_id == preview.transaction_id

    assert conflict_line.resolution == "CONFLICTED"
    assert conflict_line.confirmed_transaction_id is None
    details = conflict_line.conflict_details_json
    assert isinstance(details, dict)
    assert details["code"] == "STOCKTAKE_VERSION_CONFLICT"
    assert details["balance_id"] == conflict_balance.id
    assert details["expected_version"] == (
        conflict_line.snapshot_balance_version
    )
    assert details["actual_version"] == conflict_actual_version

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert transaction.status == "PARTIALLY_COMPLETED"
    assert transaction.completed_at is not None
    assert result.status == "CONFLICTED"
    assert _persisted_stocktake(
        session,
        reviewed.id,
    ).status == "CONFLICTED"
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == 1


def test_slice4_partial_confirm_replay_does_not_adjust_success_twice(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="PARTIAL-REPLAY",
    )
    conflict_balance = balances[1]
    conflict_balance.version += 1
    session.flush()

    command = _slice4_execute_command(preview)
    first = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=command,
        idempotency_key="slice4-execute-partial-replay",
    )
    success_balance = balances[0]
    session.refresh(success_balance)
    success_after_first = success_balance.on_hand_quantity
    success_line = _slice4_line_by_balance(
        session,
        reviewed,
        success_balance.id,
    )
    success_line_version = success_line.version
    entry_count = _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    )

    replay = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=command,
        idempotency_key="slice4-execute-partial-replay",
    )

    session.refresh(success_balance)
    success_line = _persisted_line(
        session,
        success_line.id,
    )
    assert first.status == "CONFLICTED"
    assert replay.status == "CONFLICTED"
    assert success_balance.on_hand_quantity == success_after_first
    assert success_line.version == success_line_version
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == entry_count == 1


def test_slice4_full_success_completes_transaction_and_stocktake(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="FULL-SUCCESS",
    )
    before = {
        balance.id: balance.on_hand_quantity
        for balance in balances
    }

    result = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key="slice4-execute-full-success",
    )

    for balance in balances:
        session.refresh(balance)
        assert balance.on_hand_quantity == (
            before[balance.id] - Decimal("1.0000")
        )

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert transaction.status == "COMPLETED"
    assert transaction.completed_at is not None
    assert result.status == "CONFIRMED"
    assert _persisted_stocktake(
        session,
        reviewed.id,
    ).status == "CONFIRMED"
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == len(balances)

    for item in reviewed.lines:
        line = _persisted_line(session, item.id)
        assert line.resolution == "ADJUSTED"
        assert line.confirmed_transaction_id == preview.transaction_id


def test_slice4_all_zero_terminalizes_without_ledger_entries(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="ALL-ZERO",
        quantities=("5.0000", "3.0000"),
        count_offsets=("0.0000", "0.0000"),
    )
    before = {
        balance.id: (
            balance.on_hand_quantity,
            balance.version,
        )
        for balance in balances
    }

    result = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key="slice4-execute-all-zero",
    )

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert transaction.status == "COMPLETED"
    assert transaction.completed_at is not None
    assert result.status == "CONFIRMED"
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == 0

    for balance in balances:
        session.refresh(balance)
        assert before[balance.id] == (
            balance.on_hand_quantity,
            balance.version,
        )

    for item in reviewed.lines:
        line = _persisted_line(session, item.id)
        assert line.resolution == "ADJUSTED"
        assert line.confirmed_transaction_id == preview.transaction_id


def test_slice4_all_conflict_terminalizes_without_ledger_entries(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix="ALL-CONFLICT",
    )
    quantities_before = {
        balance.id: balance.on_hand_quantity
        for balance in balances
    }

    for balance in balances:
        balance.version += 1
    session.flush()

    result = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key="slice4-execute-all-conflict",
    )

    transaction = _slice3_transaction(
        session,
        preview.transaction_id,
    )
    assert transaction.status == "PARTIALLY_COMPLETED"
    assert transaction.completed_at is not None
    assert result.status == "CONFLICTED"
    assert _persisted_stocktake(
        session,
        reviewed.id,
    ).status == "CONFLICTED"
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == 0

    for balance in balances:
        session.refresh(balance)
        assert balance.on_hand_quantity == quantities_before[balance.id]

    for item in reviewed.lines:
        line = _persisted_line(session, item.id)
        assert line.resolution == "CONFLICTED"
        assert line.confirmed_transaction_id is None
        assert isinstance(line.conflict_details_json, dict)
        assert (
            line.conflict_details_json["code"]
            == "STOCKTAKE_VERSION_CONFLICT"
        )

def _slice5_conflicted_stocktake(
    session,
    *,
    actor: ActorContext,
    suffix: str,
):
    service, balances, reviewed, preview = _slice4_preview(
        session,
        actor=actor,
        suffix=f"SLICE5-{suffix}",
    )
    conflict_balance = balances[-1]
    conflict_balance.version += 1
    session.flush()

    conflicted = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(preview),
        idempotency_key=f"slice5-{suffix}-execute",
    )
    assert conflicted.status == "CONFLICTED"

    adjusted = next(
        line
        for line in conflicted.lines
        if line.balance_id == balances[0].id
    )
    conflict = next(
        line
        for line in conflicted.lines
        if line.balance_id == conflict_balance.id
    )
    assert adjusted.resolution == "ADJUSTED"
    assert conflict.resolution == "CONFLICTED"

    return (
        service,
        balances,
        reviewed,
        preview,
        conflicted,
        adjusted,
        conflict,
    )


def _slice5_rebase_command(
    stocktake,
    *,
    line_id: int,
    action: str,
) -> dict[str, object]:
    return {
        "expected_version": stocktake.version,
        "lines": [
            {
                "line_id": line_id,
                "action": action,
            }
        ],
    }


def test_slice5_rebase_requires_conflicted_stocktake(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    service, _, reviewed = _slice4_reviewed_stocktake(
        session,
        actor=actor,
        suffix="SLICE5-STATE",
        quantities=("5.0000",),
    )

    with pytest.raises(ConflictError) as exc_info:
        service.rebase_lines(
            session,
            actor,
            reviewed.id,
            command=_slice5_rebase_command(
                reviewed,
                line_id=reviewed.lines[0].id,
                action="RECOUNT",
            ),
            idempotency_key="slice5-rebase-state",
        )

    assert exc_info.value.code == "INVENTORY_OPERATION_STATE_CONFLICT"


def test_slice5_rebase_is_tenant_scoped(session) -> None:
    actor_a = _actor(
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
    )
    actor_b = _actor(
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
    )
    (
        service,
        _,
        _,
        _,
        conflicted,
        _,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor_a,
        suffix="TENANT",
    )

    with pytest.raises(NotFoundError):
        service.rebase_lines(
            session,
            actor_b,
            conflicted.id,
            command=_slice5_rebase_command(
                conflicted,
                line_id=conflict_line.id,
                action="RECOUNT",
            ),
            idempotency_key="slice5-rebase-tenant",
        )


def test_slice5_rebase_rejects_adjusted_line(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        _,
        _,
        _,
        conflicted,
        adjusted_line,
        _,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="ADJUSTED",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.rebase_lines(
            session,
            actor,
            conflicted.id,
            command=_slice5_rebase_command(
                conflicted,
                line_id=adjusted_line.id,
                action="RECOUNT",
            ),
            idempotency_key="slice5-rebase-adjusted",
        )

    assert exc_info.value.code == "STOCKTAKE_LINE_ALREADY_CONFIRMED"


@pytest.mark.parametrize(
    "role",
    (
        MaintenanceRole.CONTRIBUTOR,
        MaintenanceRole.ADMIN,
    ),
)
def test_slice5_recount_refreshes_baseline_without_inventory_side_effect(
    session,
    role: MaintenanceRole,
) -> None:
    admin = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        balances,
        _,
        _,
        conflicted,
        adjusted_line,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=admin,
        suffix=f"RECOUNT-{role.value}",
    )
    actor = _actor(role=role)

    conflict_persisted = _persisted_line(
        session,
        conflict_line.id,
    )
    conflict_line_version = conflict_persisted.version
    conflict_balance = balances[-1]
    adjusted_persisted = _persisted_line(
        session,
        adjusted_line.id,
    )
    adjusted_before = (
        adjusted_persisted.resolution,
        adjusted_persisted.version,
        adjusted_persisted.confirmed_transaction_id,
        adjusted_persisted.counted_quantity,
        adjusted_persisted.variance_quantity,
    )
    balance_before = {
        balance.id: (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )
        for balance in balances
    }
    ledger_before = int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )

    result = service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=_slice5_rebase_command(
            conflicted,
            line_id=conflict_line.id,
            action="RECOUNT",
        ),
        idempotency_key=(
            f"slice5-rebase-recount-{role.value}"
        ),
    )

    assert result.status == "COUNTING"
    assert result.version == conflicted.version + 1
    recovered = next(
        line
        for line in result.lines
        if line.id == conflict_line.id
    )
    session.refresh(conflict_balance)
    assert recovered.system_quantity == (
        conflict_balance.on_hand_quantity
    )
    assert recovered.snapshot_balance_version == (
        conflict_balance.version
    )
    assert recovered.counted_quantity is None
    assert recovered.variance_quantity is None
    assert recovered.conflict_details is None
    assert recovered.resolution == "RECOUNT_REQUIRED"
    assert recovered.version == conflict_line_version + 1

    for balance in balances:
        session.refresh(balance)
        assert balance_before[balance.id] == (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )

    assert int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    ) == ledger_before

    adjusted_after = _persisted_line(
        session,
        adjusted_line.id,
    )
    assert adjusted_before == (
        adjusted_after.resolution,
        adjusted_after.version,
        adjusted_after.confirmed_transaction_id,
        adjusted_after.counted_quantity,
        adjusted_after.variance_quantity,
    )


def test_slice5_baseline_accept_requires_admin(session) -> None:
    admin = _actor(role=MaintenanceRole.ADMIN)
    contributor = _actor(
        role=MaintenanceRole.CONTRIBUTOR
    )
    (
        service,
        _,
        _,
        _,
        conflicted,
        _,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=admin,
        suffix="BASELINE-ROLE",
    )

    with pytest.raises(InsufficientMaintenanceRoleError):
        service.rebase_lines(
            session,
            contributor,
            conflicted.id,
            command=_slice5_rebase_command(
                conflicted,
                line_id=conflict_line.id,
                action="BASELINE_ACCEPT",
            ),
            idempotency_key=(
                "slice5-rebase-baseline-contributor"
            ),
        )


def test_slice5_baseline_accept_refreshes_and_recomputes_variance(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        balances,
        _,
        _,
        conflicted,
        adjusted_line,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="BASELINE",
    )
    conflict_balance = balances[-1]
    conflict_persisted = _persisted_line(
        session,
        conflict_line.id,
    )
    counted_before = conflict_persisted.counted_quantity
    line_version_before = conflict_persisted.version
    adjusted_persisted = _persisted_line(
        session,
        adjusted_line.id,
    )
    adjusted_before = (
        adjusted_persisted.resolution,
        adjusted_persisted.version,
        adjusted_persisted.confirmed_transaction_id,
    )

    conflict_balance.on_hand_quantity += Decimal("2.0000")
    conflict_balance.version += 1
    session.flush()
    quantity_before_rebase = (
        conflict_balance.on_hand_quantity
    )
    balance_version_before_rebase = (
        conflict_balance.version
    )
    ledger_before = int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )

    result = service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=_slice5_rebase_command(
            conflicted,
            line_id=conflict_line.id,
            action="BASELINE_ACCEPT",
        ),
        idempotency_key="slice5-rebase-baseline",
    )

    assert result.status == "COUNTING"
    recovered = next(
        line
        for line in result.lines
        if line.id == conflict_line.id
    )
    assert recovered.resolution == "BASELINE_ACCEPTED"
    assert recovered.system_quantity == quantity_before_rebase
    assert recovered.snapshot_balance_version == (
        balance_version_before_rebase
    )
    assert recovered.counted_quantity == counted_before
    assert recovered.variance_quantity == (
        counted_before - quantity_before_rebase
    )
    assert recovered.conflict_details is None
    assert recovered.version == line_version_before + 1

    session.refresh(conflict_balance)
    assert conflict_balance.on_hand_quantity == (
        quantity_before_rebase
    )
    assert conflict_balance.version == (
        balance_version_before_rebase
    )
    assert int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    ) == ledger_before

    adjusted_after = _persisted_line(
        session,
        adjusted_line.id,
    )
    assert adjusted_before == (
        adjusted_after.resolution,
        adjusted_after.version,
        adjusted_after.confirmed_transaction_id,
    )


def test_slice5_rebase_same_key_replays(session) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        _,
        _,
        _,
        conflicted,
        _,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="REPLAY",
    )
    command = _slice5_rebase_command(
        conflicted,
        line_id=conflict_line.id,
        action="RECOUNT",
    )

    first = service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=command,
        idempotency_key="slice5-rebase-replay",
    )
    first_line = next(
        line
        for line in first.lines
        if line.id == conflict_line.id
    )
    ledger_after_first = int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )

    replay = service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=command,
        idempotency_key="slice5-rebase-replay",
    )
    replay_line = next(
        line
        for line in replay.lines
        if line.id == conflict_line.id
    )

    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )
    assert replay_line.version == first_line.version
    assert int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    ) == ledger_after_first


def test_slice5_rebase_same_key_changed_payload_is_rejected(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        _,
        _,
        _,
        conflicted,
        _,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="KEY-REUSE",
    )

    service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=_slice5_rebase_command(
            conflicted,
            line_id=conflict_line.id,
            action="RECOUNT",
        ),
        idempotency_key="slice5-rebase-key-reuse",
    )

    with pytest.raises(ConflictError) as exc_info:
        service.rebase_lines(
            session,
            actor,
            conflicted.id,
            command=_slice5_rebase_command(
                conflicted,
                line_id=conflict_line.id,
                action="BASELINE_ACCEPT",
            ),
            idempotency_key="slice5-rebase-key-reuse",
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_slice5_recovery_reconfirms_without_readjusting_success(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        balances,
        _,
        original_preview,
        conflicted,
        adjusted_line,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="RECONFIRM",
    )

    success_balance = balances[0]
    session.refresh(success_balance)
    success_quantity_after_first = (
        success_balance.on_hand_quantity
    )
    adjusted_persisted = _persisted_line(
        session,
        adjusted_line.id,
    )
    adjusted_version_after_first = (
        adjusted_persisted.version
    )
    original_entries = _slice4_transaction_entry_count(
        session,
        original_preview.transaction_id,
    )
    assert original_entries == 1

    rebased = service.rebase_lines(
        session,
        actor,
        conflicted.id,
        command=_slice5_rebase_command(
            conflicted,
            line_id=conflict_line.id,
            action="RECOUNT",
        ),
        idempotency_key="slice5-reconfirm-rebase",
    )
    recovered = next(
        line
        for line in rebased.lines
        if line.id == conflict_line.id
    )

    counted = recovered.system_quantity - Decimal("1.0000")
    counted_result = service.record_count(
        session,
        actor,
        rebased.id,
        recovered.id,
        command={
            "expected_version": rebased.version,
            "expected_line_version": recovered.version,
            "counted_quantity": str(counted),
        },
        idempotency_key="slice5-reconfirm-count",
    )
    reviewed = service.review(
        session,
        actor,
        counted_result.id,
        expected_version=counted_result.version,
        idempotency_key="slice5-reconfirm-review",
    )
    second_preview = service.preview_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice3_preview_command(reviewed),
        idempotency_key="slice5-reconfirm-preview",
    )
    confirmed = service.execute_confirm(
        session,
        actor,
        reviewed.id,
        command=_slice4_execute_command(second_preview),
        idempotency_key="slice5-reconfirm-execute",
    )

    assert confirmed.status == "CONFIRMED"
    session.refresh(success_balance)
    assert success_balance.on_hand_quantity == (
        success_quantity_after_first
    )

    adjusted_after = _persisted_line(
        session,
        adjusted_line.id,
    )
    assert adjusted_after.resolution == "ADJUSTED"
    assert adjusted_after.version == adjusted_version_after_first
    assert adjusted_after.confirmed_transaction_id == (
        original_preview.transaction_id
    )
    assert _slice4_transaction_entry_count(
        session,
        original_preview.transaction_id,
    ) == original_entries

    recovered_after = _persisted_line(
        session,
        conflict_line.id,
    )
    assert recovered_after.resolution == "ADJUSTED"
    assert recovered_after.confirmed_transaction_id == (
        second_preview.transaction_id
    )
    assert _slice4_transaction_entry_count(
        session,
        second_preview.transaction_id,
    ) == 1


def test_slice5_cancel_conflicted_does_not_rollback_adjusted_inventory(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        balances,
        _,
        preview,
        conflicted,
        adjusted_line,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="CANCEL",
    )

    success_balance = balances[0]
    session.refresh(success_balance)
    success_quantity = success_balance.on_hand_quantity
    ledger_before = int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )
    transaction_entries = _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    )
    adjusted_before = _persisted_line(
        session,
        adjusted_line.id,
    )
    adjusted_state = (
        adjusted_before.resolution,
        adjusted_before.version,
        adjusted_before.confirmed_transaction_id,
    )

    cancelled = service.cancel(
        session,
        actor,
        conflicted.id,
        expected_version=conflicted.version,
        idempotency_key="slice5-cancel-conflicted",
    )

    assert cancelled.status == "CANCELLED"
    session.refresh(success_balance)
    assert success_balance.on_hand_quantity == success_quantity
    assert _slice4_transaction_entry_count(
        session,
        preview.transaction_id,
    ) == transaction_entries
    assert int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    ) == ledger_before

    adjusted_after = _persisted_line(
        session,
        adjusted_line.id,
    )
    assert adjusted_state == (
        adjusted_after.resolution,
        adjusted_after.version,
        adjusted_after.confirmed_transaction_id,
    )
    conflict_after = _persisted_line(
        session,
        conflict_line.id,
    )
    assert conflict_after.resolution == "CONFLICTED"

def test_closure_stabilization_rebase_stale_version_is_atomic(
    session,
) -> None:
    actor = _actor(role=MaintenanceRole.ADMIN)
    (
        service,
        balances,
        _,
        _,
        conflicted,
        adjusted_line,
        conflict_line,
    ) = _slice5_conflicted_stocktake(
        session,
        actor=actor,
        suffix="STALE-VERSION",
    )

    stocktake_before = _persisted_stocktake(
        session,
        conflicted.id,
    )
    stocktake_state = (
        stocktake_before.status,
        stocktake_before.version,
        stocktake_before.confirmed_at,
    )

    adjusted_before = _persisted_line(
        session,
        adjusted_line.id,
    )
    adjusted_state = (
        adjusted_before.system_quantity,
        adjusted_before.counted_quantity,
        adjusted_before.variance_quantity,
        adjusted_before.snapshot_balance_version,
        adjusted_before.confirmed_transaction_id,
        adjusted_before.resolution,
        adjusted_before.conflict_details_json,
        adjusted_before.version,
    )

    conflict_before = _persisted_line(
        session,
        conflict_line.id,
    )
    conflict_state = (
        conflict_before.system_quantity,
        conflict_before.counted_quantity,
        conflict_before.variance_quantity,
        conflict_before.snapshot_balance_version,
        conflict_before.confirmed_transaction_id,
        conflict_before.resolution,
        conflict_before.conflict_details_json,
        conflict_before.version,
    )

    balance_state = {
        balance.id: (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )
        for balance in balances
    }
    ledger_before = int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    )

    stale_command = _slice5_rebase_command(
        conflicted,
        line_id=conflict_line.id,
        action="RECOUNT",
    )
    stale_command["expected_version"] = (
        conflicted.version - 1
    )

    with pytest.raises(ConflictError) as exc_info:
        service.rebase_lines(
            session,
            actor,
            conflicted.id,
            command=stale_command,
            idempotency_key=(
                "closure-stabilization-rebase-stale-version"
            ),
        )

    assert exc_info.value.code == "STOCKTAKE_VERSION_CONFLICT"

    stocktake_after = _persisted_stocktake(
        session,
        conflicted.id,
    )
    assert stocktake_state == (
        stocktake_after.status,
        stocktake_after.version,
        stocktake_after.confirmed_at,
    )

    adjusted_after = _persisted_line(
        session,
        adjusted_line.id,
    )
    assert adjusted_state == (
        adjusted_after.system_quantity,
        adjusted_after.counted_quantity,
        adjusted_after.variance_quantity,
        adjusted_after.snapshot_balance_version,
        adjusted_after.confirmed_transaction_id,
        adjusted_after.resolution,
        adjusted_after.conflict_details_json,
        adjusted_after.version,
    )

    conflict_after = _persisted_line(
        session,
        conflict_line.id,
    )
    assert conflict_state == (
        conflict_after.system_quantity,
        conflict_after.counted_quantity,
        conflict_after.variance_quantity,
        conflict_after.snapshot_balance_version,
        conflict_after.confirmed_transaction_id,
        conflict_after.resolution,
        conflict_after.conflict_details_json,
        conflict_after.version,
    )

    for balance in balances:
        session.refresh(balance)
        assert balance_state[balance.id] == (
            balance.on_hand_quantity,
            balance.reserved_quantity,
            balance.damaged_quantity,
            balance.quarantined_quantity,
            balance.in_transit_quantity,
            balance.version,
        )

    assert int(
        session.scalar(
            select(func.count()).select_from(
                InventoryLedgerEntry
            )
        )
        or 0
    ) == ledger_before
