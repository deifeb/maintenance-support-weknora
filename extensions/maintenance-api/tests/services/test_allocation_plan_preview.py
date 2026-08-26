from __future__ import annotations

import importlib
from copy import deepcopy
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
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
    InventoryPolicy,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import DemandListStatus
from sqlalchemy import select

FEATURE_MISSING = "PLAN05_4D_TASK4_FEATURE_MISSING"
CONTRACT_MISSING = "PLAN05_4D_TASK4_CONTRACT_MISSING"


def _apis():
    service_name = "app.services.allocation_plan_service"
    schema_name = "app.schemas.allocation"
    if importlib.util.find_spec(service_name) is None:
        pytest.fail(
            f"{FEATURE_MISSING}: missing Task 4 module: {service_name}",
            pytrace=False,
        )
    service_api = importlib.import_module(service_name)
    schema_api = importlib.import_module(schema_name)
    if not hasattr(service_api, "AllocationPlanService"):
        pytest.fail(
            f"{CONTRACT_MISSING}: missing AllocationPlanService",
            pytrace=False,
        )
    required_schema = (
        "AllocationPlanLineEditCommand",
        "AllocationPlanPreviewCommand",
    )
    missing = [name for name in required_schema if not hasattr(schema_api, name)]
    if missing:
        pytest.fail(
            f"{CONTRACT_MISSING}: missing Task 4 schema API: {', '.join(missing)}",
            pytrace=False,
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


def _seed_plan_context(session, actor):
    tenant_id = actor.tenant_id
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code="scenario-preview",
        name="Scenario Preview",
    )
    session.add(template)
    session.flush()

    scenario = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code="v1-preview",
        version_name="Version Preview",
    )
    session.add(scenario)
    session.flush()

    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=scenario.id,
        primary_candidate_key="preview-primary",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id="seed-user",
        created_by_request_id="seed-request",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code="SP-PREVIEW",
        name="Spare Preview",
        unit="EA",
        category="critical",
        is_critical=True,
    )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code="WH-PREVIEW",
        name="Warehouse Preview",
    )
    session.add_all([group, spare, warehouse])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code="PICK-PREVIEW",
        name="Pick Preview",
        location_type="PICK",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    source = DemandList(
        tenant_id=tenant_id,
        name="Preview source",
        lineage_id="demand-preview",
        version_number=1,
        scenario_version_id=scenario.id,
        calculation_group_id=group.id,
        status=DemandListStatus.PUBLISHED,
        is_current=True,
        created_by_user_id="seed-user",
        created_by_request_id="seed-request",
    )
    session.add(source)
    session.flush()

    item = DemandListItem(
        tenant_id=tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
        criticality_level_snapshot="CRITICAL",
        original_quantity=Decimal("6.000000"),
        final_quantity=Decimal("6.000000"),
        source_snapshot_json={"seed": "preview"},
    )
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare.id,
        lot_id=None,
        on_hand_quantity=Decimal("10.0000"),
        reserved_quantity=Decimal("2.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("3.0000"),
        version=5,
    )
    policy = InventoryPolicy(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        safety_stock=Decimal("0.0000"),
        reorder_point=Decimal("2.0000"),
        maximum_stock=Decimal("4.0000"),
        version=1,
    )
    rule = AllocationRuleVersion(
        tenant_id=tenant_id,
        lineage_id="rule-preview",
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
        change_reason="Task 4 preview RED",
        published_by_user_id="admin-a",
        published_by_request_id="publish-preview",
        version=2,
    )
    session.add_all([item, balance, policy, rule])
    session.flush()

    _, service_api = _apis()
    service = service_api.AllocationPlanService()
    plan = service.create(
        session,
        actor,
        source.id,
        idempotency_key="task4-preview-create",
    )
    [line] = list(
        session.scalars(
            select(AllocationPlanLine)
            .where(
                AllocationPlanLine.tenant_id == tenant_id,
                AllocationPlanLine.plan_id == plan.id,
            )
            .order_by(AllocationPlanLine.id.asc())
        ).all()
    )
    return {
        "service": service,
        "source": source,
        "item": item,
        "balance": balance,
        "policy": policy,
        "rule": rule,
        "plan": plan,
        "line": line,
    }


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


def test_edit_requires_reason_expected_versions_and_respects_policy_cap(
    session,
    actor_contributor,
) -> None:
    schema_api, _ = _apis()
    context = _seed_plan_context(session, actor_contributor)
    service = context["service"]
    plan = context["plan"]
    line = context["line"]

    with pytest.raises(Exception):
        schema_api.AllocationPlanLineEditCommand(
            expected_plan_version=plan.version,
            expected_line_version=line.version,
            allocated_quantity="3.000000",
            reason="   ",
        )

    with pytest.raises(AppException) as too_high:
        service.edit_line(
            session,
            actor_contributor,
            plan.id,
            line.id,
            command=schema_api.AllocationPlanLineEditCommand(
                expected_plan_version=plan.version,
                expected_line_version=line.version,
                allocated_quantity="5.000000",
                reason="manual assurance adjustment",
            ),
        )
    assert too_high.value.code == "ALLOCATION_INVENTORY_CONFLICT"
    assert "policy" in str(too_high.value.details).lower()

    with pytest.raises(Exception):
        schema_api.AllocationPlanLineEditCommand(
            expected_plan_version=plan.version,
            expected_line_version=line.version,
            allocated_quantity="-0.000001",
            reason="invalid negative",
        )


def test_edit_appends_auditable_event_and_does_not_touch_inventory(
    session,
    actor_contributor,
) -> None:
    schema_api, _ = _apis()
    context = _seed_plan_context(session, actor_contributor)
    service = context["service"]
    plan = context["plan"]
    line = context["line"]
    before_inventory = _inventory_facts(session, actor_contributor.tenant_id)
    before_events = _events(session, actor_contributor.tenant_id, plan.id)

    updated = service.edit_line(
        session,
        actor_contributor,
        plan.id,
        line.id,
        command=schema_api.AllocationPlanLineEditCommand(
            expected_plan_version=plan.version,
            expected_line_version=line.version,
            allocated_quantity="4.000000",
            reason="cap to policy",
        ),
    )

    after_events = _events(session, actor_contributor.tenant_id, plan.id)
    assert updated.manual_override_json
    assert "cap to policy" in str(updated.manual_override_json)
    assert len(after_events) == len(before_events) + 1
    event = after_events[-1]
    assert event.event_type == "LINE_EDITED"
    assert event.before_snapshot_json
    assert event.after_snapshot_json
    assert event.request_id == actor_contributor.request_id
    assert _inventory_facts(session, actor_contributor.tenant_id) == before_inventory


def test_edit_rejects_stale_plan_or_line_version(
    session,
    actor_contributor,
) -> None:
    schema_api, _ = _apis()
    context = _seed_plan_context(session, actor_contributor)
    service = context["service"]
    plan = context["plan"]
    line = context["line"]

    with pytest.raises(AppException) as stale:
        service.edit_line(
            session,
            actor_contributor,
            plan.id,
            line.id,
            command=schema_api.AllocationPlanLineEditCommand(
                expected_plan_version=plan.version + 1,
                expected_line_version=line.version,
                allocated_quantity="3.000000",
                reason="stale plan",
            ),
        )
    assert "VERSION" in stale.value.code


def test_preview_recomputes_and_persists_pre_view_event_without_inventory_mutation(
    session,
    actor_contributor,
) -> None:
    schema_api, _ = _apis()
    context = _seed_plan_context(session, actor_contributor)
    service = context["service"]
    plan = context["plan"]
    before = _inventory_facts(session, actor_contributor.tenant_id)

    previewed = service.preview(
        session,
        actor_contributor,
        plan.id,
        command=schema_api.AllocationPlanPreviewCommand(
            expected_version=plan.version,
        ),
    )

    assert previewed.status == "PREVIEWED"
    events = _events(session, actor_contributor.tenant_id, plan.id)
    assert events
    assert events[-1].event_type == "PREVIEWED"
    assert events[-1].before_snapshot_json
    assert events[-1].after_snapshot_json
    assert _inventory_facts(session, actor_contributor.tenant_id) == before


@pytest.mark.parametrize("stale_fact", ["source", "rule", "balance"])
def test_preview_returns_structured_regenerate_conflict_when_frozen_facts_change(
    session,
    actor_contributor,
    stale_fact,
) -> None:
    schema_api, _ = _apis()
    context = _seed_plan_context(session, actor_contributor)
    service = context["service"]
    plan = context["plan"]

    if stale_fact == "source":
        context["source"].version += 1
    elif stale_fact == "rule":
        context["rule"].version += 1
    else:
        context["balance"].on_hand_quantity += Decimal("1.0000")
        context["balance"].version += 1
    session.flush()

    before = _inventory_facts(session, actor_contributor.tenant_id)
    with pytest.raises(AppException) as raised:
        service.preview(
            session,
            actor_contributor,
            plan.id,
            command=schema_api.AllocationPlanPreviewCommand(
                expected_version=plan.version,
            ),
        )

    if stale_fact == "source":
        assert raised.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"
    elif stale_fact == "rule":
        assert raised.value.code == "ALLOCATION_RULE_VERSION_CONFLICT"
    else:
        assert raised.value.code == "ALLOCATION_INVENTORY_CONFLICT"

    details = str(raised.value.details).lower()
    assert stale_fact in details
    assert "regenerate" in details
    assert _inventory_facts(session, actor_contributor.tenant_id) == before
