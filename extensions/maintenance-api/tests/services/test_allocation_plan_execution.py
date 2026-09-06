from __future__ import annotations

import importlib
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from app.core.exceptions import AppException, ConflictError
from app.models import (
    AllocationPlanEvent,
    AllocationPlanLine,
    AllocationRuleVersion,
    CalculationGroup,
    DemandList,
    DemandListItem,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryLot,
    InventoryPolicy,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import DemandListStatus
from sqlalchemy import func, select

TASK5_FEATURE_MISSING = "PLAN05_4D_TASK5_FEATURE_MISSING"
TASK5_CONTRACT_MISSING = "PLAN05_4D_TASK5_CONTRACT_MISSING"
ZERO4 = Decimal("0.0000")


def _allocation_modules():
    schema_api = importlib.import_module("app.schemas.allocation")
    service_api = importlib.import_module("app.services.allocation_plan_service")
    return schema_api, service_api


def _reservation_modules():
    schema_api = importlib.import_module("app.schemas.inventory_reservation")
    service_api = importlib.import_module("app.services.inventory_reservation_service")
    return schema_api, service_api


def _require_members(owner: Any, names: tuple[str, ...], *, area: str) -> None:
    missing = [name for name in names if not hasattr(owner, name)]
    if missing:
        pytest.fail(
            f"{TASK5_FEATURE_MISSING}: missing {area}: {', '.join(missing)}",
            pytrace=False,
        )


def _confirm_api():
    schema_api, service_api = _allocation_modules()
    _require_members(
        schema_api,
        ("AllocationPlanConfirmCommand", "AllocationPlanActionResult"),
        area="Task 5 confirm schema API",
    )
    _require_members(
        service_api.AllocationPlanService,
        ("confirm",),
        area="AllocationPlanService.confirm",
    )
    return schema_api, service_api


def _execute_api():
    schema_api, service_api = _allocation_modules()
    _require_members(
        schema_api,
        (
            "AllocationPlanConfirmCommand",
            "AllocationPlanExecuteCommand",
            "AllocationPlanActionResult",
            "AllocationPlanExecutionLineResult",
            "AllocationPlanExecutionResult",
        ),
        area="Task 5 execution schema API",
    )
    _require_members(
        service_api.AllocationPlanService,
        ("confirm", "execute"),
        area="AllocationPlanService confirm/execute",
    )
    return schema_api, service_api


def _strict_api():
    schema_api, service_api = _reservation_modules()
    _require_members(
        service_api.InventoryReservationService,
        ("reserve_for_allocation_line",),
        area="InventoryReservationService.reserve_for_allocation_line",
    )
    return schema_api, service_api


def _row_snapshot(row) -> dict[str, object]:
    return {
        column.name: deepcopy(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _inventory_facts(session, tenant_id: str) -> dict[str, list[dict[str, object]]]:
    models = (
        InventoryBalance,
        InventoryTransaction,
        InventoryLedgerEntry,
        InventoryReservation,
        InventoryReservationLine,
    )
    result: dict[str, list[dict[str, object]]] = {}
    for model in models:
        rows = list(
            session.scalars(
                select(model)
                .where(model.tenant_id == tenant_id)
                .order_by(model.id.asc())
            ).all()
        )
        result[model.__tablename__] = [_row_snapshot(row) for row in rows]
    return result


def _events(session, tenant_id: str, plan_id: int) -> list[AllocationPlanEvent]:
    return list(
        session.scalars(
            select(AllocationPlanEvent)
            .where(
                AllocationPlanEvent.tenant_id == tenant_id,
                AllocationPlanEvent.plan_id == plan_id,
            )
            .order_by(AllocationPlanEvent.id.asc())
        ).all()
    )


def _plan_lines(session, tenant_id: str, plan_id: int) -> list[AllocationPlanLine]:
    return list(
        session.scalars(
            select(AllocationPlanLine)
            .where(
                AllocationPlanLine.tenant_id == tenant_id,
                AllocationPlanLine.plan_id == plan_id,
            )
            .order_by(AllocationPlanLine.id.asc())
        ).all()
    )


def _seed_plan_context(
    session,
    actor,
    *,
    suffix: str = "task5",
    preview: bool = True,
    source_status: DemandListStatus = DemandListStatus.PUBLISHED,
    source_is_current: bool = True,
    demand_quantities: tuple[str, ...] = ("2.000000",),
    balance_quantities: tuple[str, ...] = ("6.0000", "6.0000"),
    safety_stock: str = "0.0000",
    service=None,
):
    tenant_id = actor.tenant_id
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"scenario-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()

    scenario = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"v1-{suffix}",
        version_name=f"Version {suffix}",
    )
    session.add(scenario)
    session.flush()

    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=scenario.id,
        primary_candidate_key=f"primary-{suffix}",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id="seed-user",
        created_by_request_id=f"seed-request-{suffix}",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
        unit="EA",
        category="critical",
        is_critical=True,
    )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    session.add_all([group, spare, warehouse])
    session.flush()

    source = DemandList(
        tenant_id=tenant_id,
        name=f"Demand {suffix}",
        lineage_id=f"demand-{suffix}",
        version_number=1,
        scenario_version_id=scenario.id,
        calculation_group_id=group.id,
        status=source_status,
        is_current=source_is_current,
        created_by_user_id="seed-user",
        created_by_request_id=f"seed-request-{suffix}",
    )
    session.add(source)
    session.flush()

    # DemandListItem is unique per (tenant, demand_list, spare_part). Multi-line
    # execution cases therefore use one legal demand item and add extra
    # AllocationPlanLine rows before preview instead of violating source-domain
    # uniqueness merely to construct execution/concurrency edge cases.
    item = DemandListItem(
        tenant_id=tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
        criticality_level_snapshot="CRITICAL",
        original_quantity=Decimal(demand_quantities[0]),
        final_quantity=Decimal(demand_quantities[0]),
        source_snapshot_json={"seed": suffix, "line": 1},
    )
    session.add(item)
    session.flush()
    items = [item]

    balances: list[InventoryBalance] = []
    lots: list[InventoryLot] = []
    locations: list[WarehouseLocation] = []
    for index, quantity in enumerate(balance_quantities, start=1):
        location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code=f"PICK-{suffix}-{index}",
            name=f"Pick {suffix} {index}",
            location_type="PICK",
            is_pickable=True,
            is_active=True,
        )
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare.id,
            lot_code=f"LOT-{suffix}-{index}",
            received_date=date(2026, 7, index),
            expiry_date=date(2026, 9, index),
            quality_status="AVAILABLE",
            is_frozen=False,
        )
        session.add_all([location, lot])
        session.flush()
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare.id,
            lot_id=lot.id,
            on_hand_quantity=Decimal(quantity),
            reserved_quantity=ZERO4,
            damaged_quantity=ZERO4,
            quarantined_quantity=ZERO4,
            in_transit_quantity=ZERO4,
            version=2 + index,
        )
        session.add(balance)
        session.flush()
        locations.append(location)
        lots.append(lot)
        balances.append(balance)

    policy = InventoryPolicy(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        safety_stock=Decimal(safety_stock),
        reorder_point=max(Decimal(safety_stock), Decimal("0.0000")),
        maximum_stock=None,
        version=1,
    )
    rule = AllocationRuleVersion(
        tenant_id=tenant_id,
        lineage_id=f"rule-{suffix}",
        version_number=1,
        status="PUBLISHED",
        scope_json={
            "warehouse_ids": [warehouse.id],
            "spare_part_ids": [spare.id],
        },
        effective_from=None,
        effective_to=None,
        hard_rules_json={
            "exclude_frozen": True,
            "exclude_expired": True,
            "require_available": True,
        },
        weights_json={"criticality": "1.000000"},
        normalization_json={"criticality": {"min": "0", "max": "4"}},
        change_reason="Task 5 RED seed",
        published_by_user_id="admin-a",
        published_by_request_id=f"publish-{suffix}",
        version=2,
    )
    session.add_all([policy, rule])
    session.flush()

    if service is None:
        _, service_api = _allocation_modules()
        service = service_api.AllocationPlanService()

    plan = service.create(
        session,
        actor,
        source.id,
        idempotency_key=f"task5-create-{suffix}",
    )

    if len(demand_quantities) > 1:
        base_line = _plan_lines(session, tenant_id, plan.id)[0]
        balance_by_id = {balance.id: balance for balance in balances}
        recommended_balance = balance_by_id.get(base_line.recommended_balance_id)
        available = (
            max(recommended_balance.available_quantity, ZERO4)
            if recommended_balance is not None
            else ZERO4
        )
        for quantity_text in demand_quantities[1:]:
            demand_quantity = Decimal(quantity_text)
            allocated_quantity = min(demand_quantity, available)
            session.add(
                AllocationPlanLine(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    demand_list_item_id=item.id,
                    spare_part_id=spare.id,
                    recommended_balance_id=base_line.recommended_balance_id,
                    recommended_lot_id=base_line.recommended_lot_id,
                    recommended_serial_item_id=base_line.recommended_serial_item_id,
                    demand_quantity=demand_quantity,
                    allocated_quantity=allocated_quantity,
                    gap_quantity=max(
                        demand_quantity - allocated_quantity,
                        Decimal("0"),
                    ),
                    risks_json=deepcopy(base_line.risks_json),
                    manual_override_json=None,
                    expected_balance_version=base_line.expected_balance_version,
                    reservation_id=None,
                    result_json=None,
                    version=1,
                )
            )
        session.flush()

    if preview:
        schema_api, _ = _allocation_modules()
        plan = service.preview(
            session,
            actor,
            plan.id,
            command=schema_api.AllocationPlanPreviewCommand(
                expected_version=plan.version,
            ),
        )
    return {
        "service": service,
        "source": source,
        "items": items,
        "spare": spare,
        "warehouse": warehouse,
        "locations": locations,
        "lots": lots,
        "balances": balances,
        "policy": policy,
        "rule": rule,
        "plan": plan,
        "lines": _plan_lines(session, tenant_id, plan.id),
    }


def _confirm_context(
    session,
    actor,
    *,
    suffix: str = "confirm",
    service=None,
    **seed_kwargs,
):
    schema_api, service_api = _confirm_api()
    service = service or service_api.AllocationPlanService()
    context = _seed_plan_context(
        session,
        actor,
        suffix=suffix,
        service=service,
        **seed_kwargs,
    )
    plan = context["plan"]
    result = service.confirm(
        session,
        actor,
        plan.id,
        command=schema_api.AllocationPlanConfirmCommand(
            expected_version=plan.version,
        ),
        idempotency_key=f"task5-confirm-{suffix}",
    )
    context["plan"] = session.get(type(plan), plan.id)
    context["lines"] = _plan_lines(session, actor.tenant_id, plan.id)
    context["confirm_result"] = result
    return context


def _inventory_conflict(
    *,
    code: str = "INVENTORY_VERSION_CONFLICT",
    retryable: bool = True,
    details: dict[str, Any] | None = None,
) -> AppException:
    payload = {"retryable": retryable}
    if details:
        payload.update(details)
    return ConflictError("inventory state conflict", code=code, details=payload)


class RecordingReservationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failures: dict[int, Exception] = {}
        self.next_id = 10000
        self.release_calls = 0
        self.cancel_calls = 0

    def fail_line(self, line_id: int, exc: Exception) -> None:
        self.failures[line_id] = exc

    def reserve_for_allocation_line(
        self,
        session,
        actor,
        *,
        command,
        required_balance_id: int,
        required_serial_item_id: int | None,
        allocation_context: dict[str, Any],
        idempotency_key: str,
    ):
        call = {
            "command": command,
            "required_balance_id": required_balance_id,
            "required_serial_item_id": required_serial_item_id,
            "allocation_context": deepcopy(allocation_context),
            "idempotency_key": idempotency_key,
        }
        self.calls.append(call)
        line_id = int(allocation_context["allocation_plan_line_id"])
        if line_id in self.failures:
            raise self.failures[line_id]

        reservation_schema, _ = _reservation_modules()
        reservation_id = self.next_id
        self.next_id += 1
        expected_version = command.expected_balance_versions[required_balance_id]
        return reservation_schema.InventoryReservationRead(
            id=reservation_id,
            tenant_id=actor.tenant_id,
            owner_type=command.owner_type,
            owner_id=command.owner_id,
            status="ACTIVE",
            expires_at=command.expires_at,
            allow_partial=command.allow_partial,
            actor_user_id=actor.user_id,
            actor_roles=[actor.role.value],
            request_id=actor.request_id,
            version=1,
            requested_quantity=command.requested_quantity,
            reserved_quantity=command.requested_quantity,
            issued_quantity=ZERO4,
            released_quantity=ZERO4,
            unfilled_quantity=ZERO4,
            line_errors=(),
            lines=(
                reservation_schema.InventoryReservationLineRead(
                    id=reservation_id * 10,
                    reservation_id=reservation_id,
                    spare_part_id=command.spare_part_id,
                    balance_id=required_balance_id,
                    lot_id=command.lot_id,
                    serial_item_id=required_serial_item_id,
                    requested_quantity=command.requested_quantity,
                    reserved_quantity=command.requested_quantity,
                    issued_quantity=ZERO4,
                    released_quantity=ZERO4,
                    expected_balance_version=expected_version,
                    fefo_rank=1,
                    fefo_override_reason=command.fefo_override_reason,
                    version=1,
                ),
            ),
        )

    def release(self, *args, **kwargs):
        self.release_calls += 1
        raise AssertionError("allocation execution must not call release")

    def cancel(self, *args, **kwargs):
        self.cancel_calls += 1
        raise AssertionError("allocation execution must not call cancel")


class ReserveThenConflictService:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def reserve_for_allocation_line(self, session, actor, **kwargs):
        self.calls.append(deepcopy(kwargs))
        self.inner.reserve_for_allocation_line(session, actor, **kwargs)
        raise _inventory_conflict(
            code="INVENTORY_VERSION_CONFLICT",
            retryable=True,
            details={"injected_after_reserve": True},
        )


def _service_with_fake(service_api, fake: RecordingReservationService):
    try:
        return service_api.AllocationPlanService(reservation_service=fake)
    except TypeError as exc:
        pytest.fail(
            f"{TASK5_FEATURE_MISSING}: AllocationPlanService must accept reservation_service dependency: {exc}",
            pytrace=False,
        )


def _execute_context(
    session,
    actor,
    *,
    suffix: str = "execute",
    fake: RecordingReservationService | None = None,
    **seed_kwargs,
):
    schema_api, service_api = _execute_api()
    fake = fake or RecordingReservationService()
    service = _service_with_fake(service_api, fake)
    context = _confirm_context(
        session,
        actor,
        suffix=suffix,
        service=service,
        **seed_kwargs,
    )
    context["fake"] = fake
    context["schema_api"] = schema_api
    return context


def _execute(context, session, actor, *, key: str | None = None, expected_version=None):
    plan = context["plan"]
    schema_api = context["schema_api"]
    command = schema_api.AllocationPlanExecuteCommand(
        expected_version=(plan.version if expected_version is None else expected_version),
    )
    return context["service"].execute(
        session,
        actor,
        plan.id,
        command=command,
        idempotency_key=key or f"task5-execute-{plan.id}",
    )


def _seed_strict_inventory(
    session,
    actor,
    *,
    suffix: str,
    quantities: tuple[str, ...] = ("4.0000", "4.0000"),
    safety_stock: str = "0.0000",
    serial_on_first: bool = False,
):
    tenant_id = actor.tenant_id
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-STRICT-{suffix}",
        name=f"Strict warehouse {suffix}",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-STRICT-{suffix}",
        name=f"Strict spare {suffix}",
        unit="EA",
    )
    session.add_all([warehouse, spare])
    session.flush()

    balances: list[InventoryBalance] = []
    lots: list[InventoryLot] = []
    serials: list[SerializedItem] = []
    for index, quantity in enumerate(quantities, start=1):
        location = WarehouseLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code=f"LOC-STRICT-{suffix}-{index}",
            name=f"Strict location {suffix} {index}",
            location_type="SHELF",
            is_pickable=True,
            is_active=True,
        )
        lot = InventoryLot(
            tenant_id=tenant_id,
            spare_part_id=spare.id,
            lot_code=f"LOT-STRICT-{suffix}-{index}",
            received_date=date(2026, 7, index),
            expiry_date=date(2026, 9, index),
            quality_status="AVAILABLE",
            is_frozen=False,
        )
        session.add_all([location, lot])
        session.flush()
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            location_id=location.id,
            spare_part_id=spare.id,
            lot_id=lot.id,
            on_hand_quantity=Decimal(quantity),
            reserved_quantity=ZERO4,
            damaged_quantity=ZERO4,
            quarantined_quantity=ZERO4,
            in_transit_quantity=ZERO4,
            version=1 + index,
        )
        session.add(balance)
        session.flush()
        if serial_on_first and index == 1:
            serial = SerializedItem(
                tenant_id=tenant_id,
                spare_part_id=spare.id,
                serial_number=f"SER-STRICT-{suffix}",
                lot_id=lot.id,
                warehouse_id=warehouse.id,
                location_id=location.id,
                status="IN_STOCK",
                version=1,
            )
            session.add(serial)
            session.flush()
            serials.append(serial)
        balances.append(balance)
        lots.append(lot)

    policy = InventoryPolicy(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        safety_stock=Decimal(safety_stock),
        reorder_point=Decimal(safety_stock),
        maximum_stock=None,
        version=1,
    )
    session.add(policy)
    session.flush()
    return {
        "warehouse": warehouse,
        "spare": spare,
        "balances": balances,
        "lots": lots,
        "serials": serials,
        "policy": policy,
    }


def _reserve_command(schema_api, seeded, *, quantity: str, as_of: date | None = None, **overrides):
    values = {
        "owner_type": "ALLOCATION_PLAN",
        "owner_id": "123",
        "spare_part_id": seeded["spare"].id,
        "warehouse_id": seeded["warehouse"].id,
        "requested_quantity": quantity,
        "allow_partial": False,
        "expected_balance_versions": {
            balance.id: balance.version for balance in seeded["balances"]
        },
        "as_of": as_of or date(2026, 8, 26),
        "expires_at": None,
    }
    values.update(overrides)
    return schema_api.ReserveCommand(**values)


def _strict_reserve(
    session,
    actor,
    *,
    seeded,
    quantity: str,
    required_balance_id: int,
    required_serial_item_id: int | None = None,
    context: dict[str, Any] | None = None,
    key: str = "allocation-plan:123:line:456:execute:789",
):
    schema_api, service_api = _strict_api()
    service = service_api.InventoryReservationService()
    command = _reserve_command(
        schema_api,
        seeded,
        quantity=quantity,
        serial_item_id=required_serial_item_id,
    )
    allocation_context = context or {
        "allocation_plan_id": 123,
        "allocation_plan_line_id": 456,
        "allocation_execution_id": 789,
        "execution_as_of": "2026-08-26",
        "source_demand_list_id": 11,
        "rule_id": 22,
    }
    return service.reserve_for_allocation_line(
        session,
        actor,
        command=command,
        required_balance_id=required_balance_id,
        required_serial_item_id=required_serial_item_id,
        allocation_context=allocation_context,
        idempotency_key=key,
    )


# ---------------------------------------------------------------------------
# 9.1 Schema and RBAC
# ---------------------------------------------------------------------------


def test_confirm_command_requires_positive_expected_version() -> None:
    schema_api, _ = _confirm_api()
    with pytest.raises(Exception):
        schema_api.AllocationPlanConfirmCommand(expected_version=0)


def test_execute_command_requires_positive_expected_version() -> None:
    schema_api, _ = _execute_api()
    with pytest.raises(Exception):
        schema_api.AllocationPlanExecuteCommand(expected_version=0)


def test_viewer_cannot_confirm_plan(session, actor_contributor, actor_viewer) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="viewer-confirm")
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_viewer,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=context["plan"].version,
            ),
            idempotency_key="viewer-confirm",
        )
    assert raised.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_viewer_cannot_execute_plan(session, actor_contributor, actor_viewer) -> None:
    context = _execute_context(session, actor_contributor, suffix="viewer-execute")
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_viewer, key="viewer-execute")
    assert raised.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_contributor_can_confirm_and_execute_plan(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="contributor")
    result = _execute(context, session, actor_contributor)
    assert context["confirm_result"].status == "CONFIRMED"
    assert result.status == "COMPLETED"


# ---------------------------------------------------------------------------
# 9.2 Confirm state / stale preview
# ---------------------------------------------------------------------------


def test_only_previewed_plan_can_be_confirmed(session, actor_contributor) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(
        session,
        actor_contributor,
        suffix="confirm-state",
        preview=False,
    )
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_contributor,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=context["plan"].version,
            ),
            idempotency_key="confirm-state",
        )
    assert raised.value.code == "ALLOCATION_PLAN_STATE_CONFLICT"


def test_confirm_rejects_stale_plan_version(session, actor_contributor) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-stale")
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_contributor,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=context["plan"].version + 1,
            ),
            idempotency_key="confirm-stale",
        )
    assert raised.value.code == "ALLOCATION_PLAN_VERSION_CONFLICT"


def test_confirm_requires_latest_preview_to_match_current_plan_version(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="preview-match")
    service = context["service"]
    plan = context["plan"]
    line = context["lines"][0]
    service.edit_line(
        session,
        actor_contributor,
        plan.id,
        line.id,
        command=schema_api.AllocationPlanLineEditCommand(
            expected_plan_version=plan.version,
            expected_line_version=line.version,
            allocated_quantity=min(line.allocated_quantity, Decimal("1.000000")),
            reason="make preview stale",
        ),
    )
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_contributor,
            plan.id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=plan.version,
            ),
            idempotency_key="confirm-preview-stale",
        )
    assert raised.value.code == "ALLOCATION_PLAN_STATE_CONFLICT"
    assert "preview" in str(raised.value.details).lower()


def test_confirm_rejects_quantity_not_exactly_representable_at_inventory_scale(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-scale")
    line = context["lines"][0]
    line.allocated_quantity = Decimal("1.000001")
    line.gap_quantity = max(line.demand_quantity - line.allocated_quantity, Decimal("0"))
    session.flush()
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_contributor,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=context["plan"].version,
            ),
            idempotency_key="confirm-scale",
        )
    assert raised.value.code == "ALLOCATION_INVENTORY_CONFLICT"
    assert context["plan"].status == "PREVIEWED"


def test_confirm_rejects_quantity_outside_numeric_18_4_range(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-range")
    line = context["lines"][0]
    line.allocated_quantity = Decimal("100000000000000.000000")
    line.demand_quantity = line.allocated_quantity
    line.gap_quantity = Decimal("0.000000")
    # Keep the out-of-range value in the identity map so confirmation, not SQLite's
    # permissive Numeric storage, owns the domain rejection.
    with session.no_autoflush:
        with pytest.raises(AppException) as raised:
            service_api.AllocationPlanService().confirm(
                session,
                actor_contributor,
                context["plan"].id,
                command=schema_api.AllocationPlanConfirmCommand(
                    expected_version=context["plan"].version,
                ),
                idempotency_key="confirm-range",
            )
    assert raised.value.code == "ALLOCATION_INVENTORY_CONFLICT"
    assert context["plan"].status == "PREVIEWED"


def test_confirm_requires_frozen_serial_quantity_to_equal_exactly_one(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-serial")
    balance = context["balances"][0]
    serial = SerializedItem(
        tenant_id=actor_contributor.tenant_id,
        spare_part_id=context["spare"].id,
        serial_number="SER-CONFIRM-QUANTITY",
        lot_id=balance.lot_id,
        warehouse_id=balance.warehouse_id,
        location_id=balance.location_id,
        status="IN_STOCK",
        version=1,
    )
    session.add(serial)
    session.flush()
    line = context["lines"][0]
    line.recommended_serial_item_id = serial.id
    line.allocated_quantity = Decimal("2.000000")
    line.demand_quantity = Decimal("2.000000")
    line.gap_quantity = Decimal("0.000000")
    session.flush()
    with pytest.raises(AppException) as raised:
        service_api.AllocationPlanService().confirm(
            session,
            actor_contributor,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=context["plan"].version,
            ),
            idempotency_key="confirm-serial-quantity",
        )
    assert raised.value.code == "ALLOCATION_INVENTORY_CONFLICT"


def test_confirm_appends_frozen_preview_audit_without_inventory_side_effects(
    session,
    actor_contributor,
) -> None:
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-audit")
    schema_api, service_api = _confirm_api()
    before_inventory = _inventory_facts(session, actor_contributor.tenant_id)
    before_events = _events(session, actor_contributor.tenant_id, context["plan"].id)
    result = service_api.AllocationPlanService().confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=schema_api.AllocationPlanConfirmCommand(
            expected_version=context["plan"].version,
        ),
        idempotency_key="confirm-audit",
    )
    after_events = _events(session, actor_contributor.tenant_id, context["plan"].id)
    assert result.status == "CONFIRMED"
    assert len(after_events) == len(before_events) + 1
    event = after_events[-1]
    assert event.event_type == "CONFIRMED"
    assert event.idempotency_key == "confirm-audit"
    assert event.request_hash
    assert "confirmed_preview_event_id" in str(event.after_snapshot_json)
    assert _inventory_facts(session, actor_contributor.tenant_id) == before_inventory


# ---------------------------------------------------------------------------
# 9.3 Confirm idempotency
# ---------------------------------------------------------------------------


def test_confirm_same_key_same_request_replays_exact_response(session, actor_contributor) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-replay")
    service = service_api.AllocationPlanService()
    command = schema_api.AllocationPlanConfirmCommand(
        expected_version=context["plan"].version,
    )
    first = service.confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=command,
        idempotency_key="confirm-replay",
    )
    second = service.confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=command,
        idempotency_key="confirm-replay",
    )
    assert first == second


def test_confirm_same_key_changed_request_is_rejected(session, actor_contributor) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-key-change")
    service = service_api.AllocationPlanService()
    original_version = context["plan"].version
    service.confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=schema_api.AllocationPlanConfirmCommand(expected_version=original_version),
        idempotency_key="confirm-key-change",
    )
    with pytest.raises(AppException) as raised:
        service.confirm(
            session,
            actor_contributor,
            context["plan"].id,
            command=schema_api.AllocationPlanConfirmCommand(
                expected_version=original_version + 1,
            ),
            idempotency_key="confirm-key-change",
        )
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_confirm_replay_does_not_increment_plan_version_or_append_duplicate_event(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _confirm_api()
    context = _seed_plan_context(session, actor_contributor, suffix="confirm-no-dup")
    service = service_api.AllocationPlanService()
    command = schema_api.AllocationPlanConfirmCommand(
        expected_version=context["plan"].version,
    )
    first = service.confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=command,
        idempotency_key="confirm-no-dup",
    )
    event_count = len(_events(session, actor_contributor.tenant_id, context["plan"].id))
    plan_version = session.get(type(context["plan"]), context["plan"].id).version
    second = service.confirm(
        session,
        actor_contributor,
        context["plan"].id,
        command=command,
        idempotency_key="confirm-no-dup",
    )
    assert first == second
    assert session.get(type(context["plan"]), context["plan"].id).version == plan_version
    assert len(_events(session, actor_contributor.tenant_id, context["plan"].id)) == event_count


# ---------------------------------------------------------------------------
# 9.4 Execute whole-plan blockers
# ---------------------------------------------------------------------------


def test_only_confirmed_plan_can_start_new_execution(session, actor_contributor) -> None:
    schema_api, service_api = _execute_api()
    fake = RecordingReservationService()
    service = _service_with_fake(service_api, fake)
    context = _seed_plan_context(
        session,
        actor_contributor,
        suffix="execute-state",
        service=service,
    )
    context["schema_api"] = schema_api
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="execute-state")
    assert raised.value.code == "ALLOCATION_PLAN_STATE_CONFLICT"
    assert fake.calls == []


def test_execute_rejects_stale_plan_version_before_inventory_mutation(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="execute-stale")
    with pytest.raises(AppException) as raised:
        _execute(
            context,
            session,
            actor_contributor,
            key="execute-stale",
            expected_version=context["plan"].version + 1,
        )
    assert raised.value.code == "ALLOCATION_PLAN_VERSION_CONFLICT"
    assert context["fake"].calls == []


def test_execute_requires_source_to_be_current_published(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="execute-source-current")
    context["source"].is_current = False
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="source-current")
    assert raised.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"
    assert context["fake"].calls == []


def test_execute_rejects_source_version_drift(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="execute-source-version")
    context["source"].version += 1
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="source-version")
    assert raised.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"
    assert "regenerate" in str(raised.value.details).lower()
    assert context["fake"].calls == []


def test_plan_frozen_on_confirmed_source_requires_regenerate_after_source_publish_increments_version(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="confirmed-published",
        source_status=DemandListStatus.CONFIRMED,
        source_is_current=False,
    )
    frozen = context["plan"].source_demand_list_version
    context["source"].status = DemandListStatus.PUBLISHED
    context["source"].is_current = True
    context["source"].version = frozen + 1
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="confirmed-published")
    assert raised.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"
    assert "regenerate" in str(raised.value.details).lower()
    assert context["fake"].calls == []


def test_execute_requires_frozen_rule_to_remain_published(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="rule-status")
    context["rule"].status = "RETIRED"
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="rule-status")
    assert raised.value.code == "ALLOCATION_RULE_VERSION_CONFLICT"
    assert context["fake"].calls == []


def test_execute_rejects_rule_version_drift(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="rule-version")
    context["rule"].version += 1
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key="rule-version")
    assert raised.value.code == "ALLOCATION_RULE_VERSION_CONFLICT"
    assert context["fake"].calls == []


def test_unrelated_inventory_fingerprint_drift_does_not_block_valid_lines(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="unrelated-drift")
    other_part = SparePart(
        tenant_id=actor_contributor.tenant_id,
        code="SP-UNRELATED",
        name="Unrelated",
        unit="EA",
    )
    other_wh = Warehouse(
        tenant_id=actor_contributor.tenant_id,
        code="WH-UNRELATED",
        name="Unrelated",
    )
    session.add_all([other_part, other_wh])
    session.flush()
    other_loc = WarehouseLocation(
        tenant_id=actor_contributor.tenant_id,
        warehouse_id=other_wh.id,
        code="LOC-UNRELATED",
        name="Unrelated",
        location_type="SHELF",
        is_pickable=True,
        is_active=True,
    )
    session.add(other_loc)
    session.flush()
    session.add(
        InventoryBalance(
            tenant_id=actor_contributor.tenant_id,
            warehouse_id=other_wh.id,
            location_id=other_loc.id,
            spare_part_id=other_part.id,
            lot_id=None,
            on_hand_quantity=Decimal("1.0000"),
            reserved_quantity=ZERO4,
            damaged_quantity=ZERO4,
            quarantined_quantity=ZERO4,
            in_transit_quantity=ZERO4,
            version=1,
        )
    )
    session.flush()
    result = _execute(context, session, actor_contributor, key="unrelated-drift")
    assert result.status == "COMPLETED"
    assert context["fake"].calls


# ---------------------------------------------------------------------------
# 9.5 Reservation linkage / strict selection
# ---------------------------------------------------------------------------


def test_execute_success_delegates_to_reservation_service_and_links_reservation(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="link-reservation")
    result = _execute(context, session, actor_contributor)
    [call] = context["fake"].calls
    [line_result] = result.line_results
    line = _plan_lines(session, actor_contributor.tenant_id, context["plan"].id)[0]
    assert call["required_balance_id"] == line.recommended_balance_id
    assert line.reservation_id == line_result.reservation_id
    assert line.reservation_id is not None


def test_execution_reservation_owner_links_to_allocation_plan(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="owner-link")
    _execute(context, session, actor_contributor)
    [call] = context["fake"].calls
    assert call["command"].owner_type == "ALLOCATION_PLAN"
    assert call["command"].owner_id == str(context["plan"].id)


def test_execute_requests_exact_allocated_quantity_and_disallows_partial(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="exact-quantity")
    line = context["lines"][0]
    _execute(context, session, actor_contributor)
    [call] = context["fake"].calls
    assert call["command"].requested_quantity == line.allocated_quantity.quantize(Decimal("0.0001"))
    assert call["command"].allow_partial is False


def test_gap_line_does_not_call_reservation_service(session, actor_contributor) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="gap-line",
        balance_quantities=("0.0000",),
    )
    assert context["lines"][0].allocated_quantity == 0
    result = _execute(context, session, actor_contributor)
    assert context["fake"].calls == []
    assert result.line_results[0].outcome == "GAP_RETAINED"


def test_positive_allocation_without_recommended_balance_conflicts(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="missing-balance")
    line = context["lines"][0]
    line.recommended_balance_id = None
    line.expected_balance_version = None
    line.allocated_quantity = Decimal("1.000000")
    line.gap_quantity = max(line.demand_quantity - line.allocated_quantity, Decimal("0"))
    session.flush()
    result = _execute(context, session, actor_contributor)
    assert context["fake"].calls == []
    assert result.line_results[0].outcome == "CONFLICT"
    assert result.line_results[0].error_code == "ALLOCATION_INVENTORY_CONFLICT"


def test_required_balance_is_preserved_when_current_fefo_recommends_another_balance(
    session,
    actor_contributor,
) -> None:
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="required-balance",
        quantities=("4.0000", "4.0000"),
    )
    required = seeded["balances"][1]
    result = _strict_reserve(
        session,
        actor_contributor,
        seeded=seeded,
        quantity="2.0000",
        required_balance_id=required.id,
    )
    assert [line.balance_id for line in result.lines] == [required.id]


def test_required_balance_fefo_override_is_audited_with_plan_line_execution_context(
    session,
    actor_contributor,
) -> None:
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="override-audit")
    required = seeded["balances"][1]
    result = _strict_reserve(
        session,
        actor_contributor,
        seeded=seeded,
        quantity="2.0000",
        required_balance_id=required.id,
    )
    stored_line = session.scalar(
        select(InventoryReservationLine).where(
            InventoryReservationLine.reservation_id == result.id
        )
    )
    assert stored_line.actual_selection_json["balance_id"] == required.id
    assert stored_line.recommended_selection_json["balance_id"] != required.id
    assert "allocation plan" in (stored_line.fefo_override_reason or "").lower()
    tx = session.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.idempotency_key == "allocation-plan:123:line:456:execute:789")
    )
    assert "allocation_plan_line_id" in str(tx.response_snapshot_json)


def test_required_balance_must_still_be_currently_eligible(session, actor_contributor) -> None:
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="required-eligible")
    required = seeded["balances"][1]
    seeded["lots"][1].is_frozen = True
    session.flush()
    with pytest.raises(AppException):
        _strict_reserve(
            session,
            actor_contributor,
            seeded=seeded,
            quantity="1.0000",
            required_balance_id=required.id,
        )


def test_unconfirmed_serial_selection_is_rejected(session, actor_contributor) -> None:
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="serial-unconfirmed",
        quantities=("1.0000",),
        serial_on_first=True,
    )
    with pytest.raises(AppException):
        _strict_reserve(
            session,
            actor_contributor,
            seeded=seeded,
            quantity="1.0000",
            required_balance_id=seeded["balances"][0].id,
            required_serial_item_id=None,
        )


def test_frozen_serial_selection_is_revalidated(session, actor_contributor) -> None:
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="serial-frozen",
        quantities=("1.0000",),
        serial_on_first=True,
    )
    serial = seeded["serials"][0]
    serial.status = "FROZEN"
    session.flush()
    with pytest.raises(AppException):
        _strict_reserve(
            session,
            actor_contributor,
            seeded=seeded,
            quantity="1.0000",
            required_balance_id=seeded["balances"][0].id,
            required_serial_item_id=serial.id,
        )


# ---------------------------------------------------------------------------
# 9.6 Balance/version/policy
# ---------------------------------------------------------------------------


def test_execute_rejects_frozen_balance_version_drift_per_line(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="balance-version")
    line = context["lines"][0]
    context["fake"].fail_line(
        line.id,
        _inventory_conflict(
            code="INVENTORY_VERSION_CONFLICT",
            details={
                "expected_version": line.expected_balance_version,
                "actual_version": line.expected_balance_version + 1,
            },
        ),
    )
    result = _execute(context, session, actor_contributor)
    assert result.line_results[0].outcome == "CONFLICT"
    assert result.line_results[0].cause_code == "INVENTORY_VERSION_CONFLICT"


def test_execute_rejects_insufficient_current_available_quantity(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="insufficient-current")
    line = context["lines"][0]
    context["fake"].fail_line(
        line.id,
        _inventory_conflict(code="INSUFFICIENT_AVAILABLE_INVENTORY", retryable=True),
    )
    result = _execute(context, session, actor_contributor)
    assert result.line_results[0].cause_code == "INSUFFICIENT_AVAILABLE_INVENTORY"


def test_execute_preserves_current_safety_stock_at_warehouse_part_scope(
    session,
    actor_contributor,
) -> None:
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="safety-stock",
        quantities=("3.0000", "3.0000"),
        safety_stock="5.0000",
    )
    with pytest.raises(AppException):
        _strict_reserve(
            session,
            actor_contributor,
            seeded=seeded,
            quantity="2.0000",
            required_balance_id=seeded["balances"][0].id,
        )


def test_safety_stock_is_not_subtracted_once_per_balance(session, actor_contributor) -> None:
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="safety-once",
        quantities=("3.0000", "3.0000"),
        safety_stock="2.0000",
    )
    result = _strict_reserve(
        session,
        actor_contributor,
        seeded=seeded,
        quantity="2.0000",
        required_balance_id=seeded["balances"][1].id,
    )
    assert result.reserved_quantity == Decimal("2.0000")


def test_lazy_expiry_runs_before_authoritative_safety_stock_and_available_check(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="lazy-before-policy",
        quantities=("4.0000",),
        safety_stock="1.0000",
    )
    service = service_api.InventoryReservationService()
    first_command = _reserve_command(schema_api, seeded, quantity="3.0000")
    first = service.reserve(
        session,
        actor_contributor,
        command=first_command,
        idempotency_key="preexisting-expiring",
    )
    stored = session.get(InventoryReservation, first.id)
    stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.flush()
    command = _reserve_command(schema_api, seeded, quantity="2.0000")
    result = service.reserve_for_allocation_line(
        session,
        actor_contributor,
        command=command,
        required_balance_id=seeded["balances"][0].id,
        required_serial_item_id=None,
        allocation_context={
            "allocation_plan_id": 1,
            "allocation_plan_line_id": 2,
            "allocation_execution_id": 3,
            "execution_as_of": "2026-08-26",
            "source_demand_list_id": 4,
            "rule_id": 5,
        },
        idempotency_key="strict-after-lazy-expiry",
    )
    assert result.reserved_quantity == Decimal("2.0000")
    assert session.get(InventoryReservation, first.id).status == "EXPIRED"


def test_execute_does_not_auto_preempt_other_reservations(session, actor_contributor) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="no-preempt",
        quantities=("4.0000",),
        safety_stock="1.0000",
    )
    service = service_api.InventoryReservationService()
    existing = service.reserve(
        session,
        actor_contributor,
        command=_reserve_command(schema_api, seeded, quantity="2.0000"),
        idempotency_key="active-other-reservation",
    )
    with pytest.raises(AppException):
        service.reserve_for_allocation_line(
            session,
            actor_contributor,
            command=_reserve_command(schema_api, seeded, quantity="2.0000"),
            required_balance_id=seeded["balances"][0].id,
            required_serial_item_id=None,
            allocation_context={
                "allocation_plan_id": 1,
                "allocation_plan_line_id": 2,
                "allocation_execution_id": 3,
                "execution_as_of": "2026-08-26",
                "source_demand_list_id": 4,
                "rule_id": 5,
            },
            idempotency_key="strict-no-preempt",
        )
    assert session.get(InventoryReservation, existing.id).status == "ACTIVE"


def test_same_balance_multiple_lines_do_not_self_conflict_on_owned_version_increment(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _execute_api()
    service = service_api.AllocationPlanService()
    context = _confirm_context(
        session,
        actor_contributor,
        suffix="same-balance-owned-version",
        service=service,
        demand_quantities=("2.000000", "2.000000"),
        balance_quantities=("10.0000",),
    )
    context["schema_api"] = schema_api
    result = _execute(context, session, actor_contributor, key="same-balance-owned-version")
    assert result.status == "COMPLETED"
    assert [item.outcome for item in result.line_results] == ["RESERVED", "RESERVED"]


def test_same_balance_later_line_conflicts_when_prior_plan_line_consumes_remaining_availability(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _execute_api()
    service = service_api.AllocationPlanService()
    context = _confirm_context(
        session,
        actor_contributor,
        suffix="same-balance-insufficient",
        service=service,
        demand_quantities=("3.000000", "3.000000"),
        balance_quantities=("5.0000",),
    )
    context["schema_api"] = schema_api
    result = _execute(context, session, actor_contributor, key="same-balance-insufficient")
    outcomes = [item.outcome for item in result.line_results]
    assert outcomes.count("RESERVED") == 1
    assert outcomes.count("CONFLICT") == 1
    assert result.status == "PARTIALLY_COMPLETED"


# ---------------------------------------------------------------------------
# 9.7 Partial success and isolation
# ---------------------------------------------------------------------------


def test_one_inventory_conflict_does_not_block_later_nonconflicting_line(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="partial-continue",
        demand_quantities=("1.000000", "1.000000"),
    )
    first, second = context["lines"]
    context["fake"].fail_line(first.id, _inventory_conflict())
    result = _execute(context, session, actor_contributor)
    by_id = {item.line_id: item for item in result.line_results}
    assert by_id[first.id].outcome == "CONFLICT"
    assert by_id[second.id].outcome == "RESERVED"


def test_success_plus_conflict_finishes_partially_completed(session, actor_contributor) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="partial-status",
        demand_quantities=("1.000000", "1.000000"),
    )
    context["fake"].fail_line(context["lines"][1].id, _inventory_conflict())
    result = _execute(context, session, actor_contributor)
    assert result.status == "PARTIALLY_COMPLETED"


def test_all_executable_lines_conflict_finishes_failed(session, actor_contributor) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="all-conflict",
        demand_quantities=("1.000000", "1.000000"),
    )
    for line in context["lines"]:
        context["fake"].fail_line(line.id, _inventory_conflict())
    result = _execute(context, session, actor_contributor)
    assert result.status == "FAILED"
    assert all(item.outcome == "CONFLICT" for item in result.line_results)


def test_all_success_and_gap_lines_finish_completed(session, actor_contributor) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="success-gap",
        demand_quantities=("1.000000", "1.000000"),
        balance_quantities=("5.0000",),
    )
    context["lines"][1].recommended_balance_id = None
    context["lines"][1].expected_balance_version = None
    context["lines"][1].allocated_quantity = Decimal("0.000000")
    context["lines"][1].gap_quantity = context["lines"][1].demand_quantity
    session.flush()
    result = _execute(context, session, actor_contributor)
    assert result.status == "COMPLETED"
    assert {item.outcome for item in result.line_results} == {"RESERVED", "GAP_RETAINED"}


def test_line_conflict_records_public_allocation_error_and_inventory_cause(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="conflict-public")
    line = context["lines"][0]
    context["fake"].fail_line(
        line.id,
        _inventory_conflict(code="INVENTORY_VERSION_CONFLICT", retryable=True),
    )
    result = _execute(context, session, actor_contributor)
    item = result.line_results[0]
    assert item.error_code == "ALLOCATION_INVENTORY_CONFLICT"
    assert item.cause_code == "INVENTORY_VERSION_CONFLICT"
    stored = _plan_lines(session, actor_contributor.tenant_id, context["plan"].id)[0]
    assert stored.result_json["error_code"] == "ALLOCATION_INVENTORY_CONFLICT"
    events = _events(session, actor_contributor.tenant_id, context["plan"].id)
    conflict_event = next(event for event in events if event.event_type == "LINE_EXECUTION_CONFLICT")
    assert conflict_event.error_code == "ALLOCATION_INVENTORY_CONFLICT"


def test_line_conflict_contains_expected_actual_affected_line_retryability_and_regenerate_action(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="conflict-details")
    line = context["lines"][0]
    context["fake"].fail_line(
        line.id,
        _inventory_conflict(
            details={
                "expected_version": line.expected_balance_version,
                "actual_version": line.expected_balance_version + 1,
                "balance_id": line.recommended_balance_id,
            }
        ),
    )
    item = _execute(context, session, actor_contributor).line_results[0]
    assert item.details["line_id"] == line.id
    assert item.details["balance_id"] == line.recommended_balance_id
    assert item.details["expected_version"] == line.expected_balance_version
    assert item.details["actual_version"] == line.expected_balance_version + 1
    assert item.retryable is False
    assert item.suggested_action == "regenerate"


def test_allocation_line_retryable_is_false_while_inventory_cause_retryable_is_preserved_separately(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="retryability")
    line = context["lines"][0]
    context["fake"].fail_line(line.id, _inventory_conflict(retryable=True))
    item = _execute(context, session, actor_contributor).line_results[0]
    assert item.retryable is False
    assert item.details["cause_retryable"] is True


# ---------------------------------------------------------------------------
# 9.8 Execution idempotency / retry
# ---------------------------------------------------------------------------


def test_execute_same_key_replays_exact_terminal_response_without_double_reserve(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="execute-replay")
    key = "execute-replay"
    original_version = context["plan"].version
    first = _execute(context, session, actor_contributor, key=key)
    calls_after_first = len(context["fake"].calls)
    second = _execute(
        context,
        session,
        actor_contributor,
        key=key,
        expected_version=original_version,
    )
    assert first == second
    assert len(context["fake"].calls) == calls_after_first


def test_execute_same_key_changed_request_is_rejected(session, actor_contributor) -> None:
    context = _execute_context(session, actor_contributor, suffix="execute-key-change")
    key = "execute-key-change"
    original_version = context["plan"].version
    _execute(context, session, actor_contributor, key=key)
    with pytest.raises(AppException) as raised:
        _execute(
            context,
            session,
            actor_contributor,
            key=key,
            expected_version=original_version + 1,
        )
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def _assert_new_execute_key_on_terminal_plan_is_state_conflict(
    session,
    actor_contributor,
    terminal_status,
) -> None:
    context = _execute_context(session, actor_contributor, suffix=f"new-key-{terminal_status.lower()}")
    context["plan"].status = terminal_status
    session.flush()
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor, key=f"new-key-{terminal_status}")
    assert raised.value.code == "ALLOCATION_PLAN_STATE_CONFLICT"
    assert "regenerate" in str(raised.value.details).lower()


def test_new_execute_key_on_completed_plan_is_state_conflict(session, actor_contributor) -> None:
    _assert_new_execute_key_on_terminal_plan_is_state_conflict(
        session, actor_contributor, "COMPLETED"
    )


def test_new_execute_key_on_partially_completed_plan_is_state_conflict(
    session,
    actor_contributor,
) -> None:
    _assert_new_execute_key_on_terminal_plan_is_state_conflict(
        session, actor_contributor, "PARTIALLY_COMPLETED"
    )


def test_new_execute_key_on_failed_plan_is_state_conflict(session, actor_contributor) -> None:
    _assert_new_execute_key_on_terminal_plan_is_state_conflict(
        session, actor_contributor, "FAILED"
    )


def test_child_idempotency_key_uses_plan_line_and_execution_event_id(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="child-key")
    result = _execute(context, session, actor_contributor)
    [call] = context["fake"].calls
    line_id = context["lines"][0].id
    assert call["idempotency_key"] == (
        f"allocation-plan:{context['plan'].id}:line:{line_id}:execute:{result.execution_id}"
    )


def test_child_idempotency_request_hash_covers_required_balance_required_serial_and_allocation_context(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="strict-hash")
    first_balance, second_balance = seeded["balances"]
    service = service_api.InventoryReservationService()
    command = _reserve_command(schema_api, seeded, quantity="1.0000")
    key = "allocation-plan:123:line:456:execute:789"
    base_context = {
        "allocation_plan_id": 123,
        "allocation_plan_line_id": 456,
        "allocation_execution_id": 789,
        "execution_as_of": "2026-08-26",
        "source_demand_list_id": 11,
        "rule_id": 22,
    }
    service.reserve_for_allocation_line(
        session,
        actor_contributor,
        command=command,
        required_balance_id=first_balance.id,
        required_serial_item_id=None,
        allocation_context=base_context,
        idempotency_key=key,
    )

    with pytest.raises(AppException) as balance_reuse:
        service.reserve_for_allocation_line(
            session,
            actor_contributor,
            command=command,
            required_balance_id=second_balance.id,
            required_serial_item_id=None,
            allocation_context=base_context,
            idempotency_key=key,
        )
    assert balance_reuse.value.code == "IDEMPOTENCY_KEY_REUSED"

    serial = SerializedItem(
        tenant_id=actor_contributor.tenant_id,
        spare_part_id=seeded["spare"].id,
        serial_number="SER-STRICT-HASH",
        lot_id=first_balance.lot_id,
        warehouse_id=first_balance.warehouse_id,
        location_id=first_balance.location_id,
        status="IN_STOCK",
        version=1,
    )
    session.add(serial)
    session.flush()
    with pytest.raises(AppException) as serial_reuse:
        service.reserve_for_allocation_line(
            session,
            actor_contributor,
            command=command,
            required_balance_id=first_balance.id,
            required_serial_item_id=serial.id,
            allocation_context=base_context,
            idempotency_key=key,
        )
    assert serial_reuse.value.code == "IDEMPOTENCY_KEY_REUSED"

    changed_context = dict(base_context)
    changed_context["rule_id"] = 23
    with pytest.raises(AppException) as context_reuse:
        service.reserve_for_allocation_line(
            session,
            actor_contributor,
            command=command,
            required_balance_id=first_balance.id,
            required_serial_item_id=None,
            allocation_context=changed_context,
            idempotency_key=key,
        )
    assert context_reuse.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_child_idempotency_request_hash_mismatch_aborts_instead_of_becoming_line_conflict(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="child-hash-abort")
    line = context["lines"][0]
    context["fake"].fail_line(
        line.id,
        _inventory_conflict(code="IDEMPOTENCY_KEY_REUSED", retryable=False),
    )
    with pytest.raises(AppException) as raised:
        _execute(context, session, actor_contributor)
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


# ---------------------------------------------------------------------------
# 9.9 Concurrency / order / rollback
# ---------------------------------------------------------------------------


def test_reservable_lines_execute_in_balance_id_then_line_id_order(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="execution-order",
        demand_quantities=("1.000000", "1.000000"),
        balance_quantities=("4.0000", "4.0000"),
    )
    lines = context["lines"]
    # Force line ids and balance ids into opposite presentation/execution ordering.
    lines[0].recommended_balance_id = context["balances"][1].id
    lines[0].expected_balance_version = context["balances"][1].version
    lines[1].recommended_balance_id = context["balances"][0].id
    lines[1].expected_balance_version = context["balances"][0].version
    session.flush()
    _execute(context, session, actor_contributor)
    observed = [
        (call["required_balance_id"], call["allocation_context"]["allocation_plan_line_id"])
        for call in context["fake"].calls
    ]
    assert observed == sorted(observed)


def test_result_lines_are_reported_in_line_id_order(session, actor_contributor) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="result-order",
        demand_quantities=("1.000000", "1.000000"),
    )
    result = _execute(context, session, actor_contributor)
    assert [item.line_id for item in result.line_results] == sorted(
        item.line_id for item in result.line_results
    )


def test_execution_as_of_is_frozen_once_and_reused_for_all_child_reservations(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="as-of-frozen",
        demand_quantities=("1.000000", "1.000000"),
    )
    service_module = importlib.import_module("app.services.allocation_plan_service")
    real_datetime = datetime

    class MovingDateTime(real_datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = real_datetime(2026, 8, 26 + min(cls.calls - 1, 2), 23, 59, tzinfo=timezone.utc)
            return value if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", MovingDateTime)
    result = _execute(context, session, actor_contributor)
    child_dates = [call["command"].as_of for call in context["fake"].calls]
    assert child_dates
    assert set(child_dates) == {result.execution_as_of}


def test_execute_replay_preserves_original_execution_as_of_without_clock_recalculation(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="as-of-replay")
    service_module = importlib.import_module("app.services.allocation_plan_service")
    real_datetime = datetime

    class FirstClock(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
            return value if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", FirstClock)
    original_version = context["plan"].version
    first = _execute(context, session, actor_contributor, key="as-of-replay")

    class LaterClock(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
            return value if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", LaterClock)
    second = _execute(
        context,
        session,
        actor_contributor,
        key="as-of-replay",
        expected_version=original_version,
    )
    assert first == second
    assert second.execution_as_of == date(2026, 8, 26)


def test_unexpected_exception_aborts_execution_instead_of_claiming_partial_success(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(
        session,
        actor_contributor,
        suffix="unexpected-abort",
        demand_quantities=("1.000000", "1.000000"),
    )
    context["fake"].fail_line(context["lines"][1].id, RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        _execute(context, session, actor_contributor)
    assert not any(
        event.event_type in {
            "EXECUTION_COMPLETED",
            "EXECUTION_PARTIALLY_COMPLETED",
            "EXECUTION_FAILED",
        }
        for event in _events(session, actor_contributor.tenant_id, context["plan"].id)
    )


def test_failed_line_savepoint_does_not_leave_reservation_transaction_or_ledger_rows(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _execute_api()
    _, reservation_service_api = _strict_api()
    injected = ReserveThenConflictService(
        reservation_service_api.InventoryReservationService()
    )
    service = _service_with_fake(service_api, injected)
    context = _confirm_context(
        session,
        actor_contributor,
        suffix="savepoint-clean",
        service=service,
        demand_quantities=("1.000000",),
        balance_quantities=("5.0000",),
    )
    context["schema_api"] = schema_api
    before = _inventory_facts(session, actor_contributor.tenant_id)
    result = _execute(context, session, actor_contributor, key="savepoint-clean")
    assert result.line_results[0].outcome == "CONFLICT"
    after = _inventory_facts(session, actor_contributor.tenant_id)
    assert len(after[InventoryReservation.__tablename__]) == len(before[InventoryReservation.__tablename__])
    assert len(after[InventoryTransaction.__tablename__]) == len(before[InventoryTransaction.__tablename__])
    assert len(after[InventoryLedgerEntry.__tablename__]) == len(before[InventoryLedgerEntry.__tablename__])


def test_execution_never_calls_release_cancel_or_direct_balance_mutation(
    session,
    actor_contributor,
) -> None:
    context = _execute_context(session, actor_contributor, suffix="no-release-cancel")
    before = [_row_snapshot(balance) for balance in context["balances"]]
    _execute(context, session, actor_contributor)
    after = [_row_snapshot(balance) for balance in context["balances"]]
    assert context["fake"].release_calls == 0
    assert context["fake"].cancel_calls == 0
    assert after == before


# ---------------------------------------------------------------------------
# 9.10 05-4B strict helper compatibility
# ---------------------------------------------------------------------------


def test_normal_reserve_behavior_is_unchanged_without_allocation_requirement(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="normal-compatible")
    service = service_api.InventoryReservationService()
    result = service.reserve(
        session,
        actor_contributor,
        command=_reserve_command(schema_api, seeded, quantity="5.0000"),
        idempotency_key="normal-compatible",
    )
    assert [(line.balance_id, line.reserved_quantity) for line in result.lines] == [
        (seeded["balances"][0].id, Decimal("4.0000")),
        (seeded["balances"][1].id, Decimal("1.0000")),
    ]


def test_allocation_strict_reserve_reuses_existing_idempotent_replay(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="strict-replay")
    service = service_api.InventoryReservationService()
    command = _reserve_command(schema_api, seeded, quantity="1.0000")
    context = {
        "allocation_plan_id": 123,
        "allocation_plan_line_id": 456,
        "allocation_execution_id": 789,
        "execution_as_of": "2026-08-26",
        "source_demand_list_id": 11,
        "rule_id": 22,
    }
    kwargs = dict(
        command=command,
        required_balance_id=seeded["balances"][0].id,
        required_serial_item_id=None,
        allocation_context=context,
        idempotency_key="strict-replay",
    )
    first = service.reserve_for_allocation_line(session, actor_contributor, **kwargs)
    before_tx_count = session.scalar(select(func.count(InventoryTransaction.id)))
    second = service.reserve_for_allocation_line(session, actor_contributor, **kwargs)
    after_tx_count = session.scalar(select(func.count(InventoryTransaction.id)))
    assert first == second
    assert after_tx_count == before_tx_count


def test_allocation_strict_reserve_rejects_same_key_when_only_strict_context_changes(
    session,
    actor_contributor,
) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="strict-context")
    service = service_api.InventoryReservationService()
    command = _reserve_command(schema_api, seeded, quantity="1.0000")
    key = "strict-context"
    base_context = {
        "allocation_plan_id": 123,
        "allocation_plan_line_id": 456,
        "allocation_execution_id": 789,
        "execution_as_of": "2026-08-26",
        "source_demand_list_id": 11,
        "rule_id": 22,
    }
    service.reserve_for_allocation_line(
        session,
        actor_contributor,
        command=command,
        required_balance_id=seeded["balances"][0].id,
        required_serial_item_id=None,
        allocation_context=base_context,
        idempotency_key=key,
    )
    changed = dict(base_context)
    changed["rule_id"] = 23
    with pytest.raises(AppException) as raised:
        service.reserve_for_allocation_line(
            session,
            actor_contributor,
            command=command,
            required_balance_id=seeded["balances"][0].id,
            required_serial_item_id=None,
            allocation_context=changed,
            idempotency_key=key,
        )
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_allocation_strict_reserve_keeps_lazy_expiry_behavior(session, actor_contributor) -> None:
    schema_api, service_api = _strict_api()
    seeded = _seed_strict_inventory(
        session,
        actor_contributor,
        suffix="strict-lazy",
        quantities=("3.0000",),
    )
    service = service_api.InventoryReservationService()
    first = service.reserve(
        session,
        actor_contributor,
        command=_reserve_command(schema_api, seeded, quantity="2.0000"),
        idempotency_key="strict-lazy-old",
    )
    stored = session.get(InventoryReservation, first.id)
    stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.flush()
    result = service.reserve_for_allocation_line(
        session,
        actor_contributor,
        command=_reserve_command(schema_api, seeded, quantity="2.0000"),
        required_balance_id=seeded["balances"][0].id,
        required_serial_item_id=None,
        allocation_context={
            "allocation_plan_id": 1,
            "allocation_plan_line_id": 2,
            "allocation_execution_id": 3,
            "execution_as_of": "2026-08-26",
            "source_demand_list_id": 4,
            "rule_id": 5,
        },
        idempotency_key="strict-lazy-new",
    )
    assert result.reserved_quantity == Decimal("2.0000")
    assert session.get(InventoryReservation, first.id).status == "EXPIRED"


def test_allocation_strict_reserve_writes_transaction_and_ledger_through_existing_kernel(
    session,
    actor_contributor,
) -> None:
    seeded = _seed_strict_inventory(session, actor_contributor, suffix="strict-kernel")
    before_tx = session.scalar(select(func.count(InventoryTransaction.id)))
    before_ledger = session.scalar(select(func.count(InventoryLedgerEntry.id)))
    result = _strict_reserve(
        session,
        actor_contributor,
        seeded=seeded,
        quantity="1.0000",
        required_balance_id=seeded["balances"][0].id,
        key="strict-kernel",
    )
    after_tx = session.scalar(select(func.count(InventoryTransaction.id)))
    after_ledger = session.scalar(select(func.count(InventoryLedgerEntry.id)))
    assert result.reserved_quantity == Decimal("1.0000")
    assert after_tx == before_tx + 1
    assert after_ledger == before_ledger + 1
