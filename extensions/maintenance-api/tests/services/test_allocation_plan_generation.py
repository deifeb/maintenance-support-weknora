from __future__ import annotations

import importlib
from copy import deepcopy
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
from app.models import (
    AllocationPlan,
    AllocationPlanLine,
    AllocationRuleVersion,
    CalculationGroup,
    DemandList,
    DemandListItem,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import DemandListStatus
from sqlalchemy import select

FEATURE_MISSING = "PLAN05_4D_TASK4_FEATURE_MISSING"
CONTRACT_MISSING = "PLAN05_4D_TASK4_CONTRACT_MISSING"
STRUCTURAL_BLOCKER = "PLAN05_4D_TASK4_STRUCTURAL_BLOCKER"


def _service_api():
    name = "app.services.allocation_plan_service"
    if importlib.util.find_spec(name) is None:
        pytest.fail(
            f"{FEATURE_MISSING}: missing Task 4 module: {name}",
            pytrace=False,
        )
    module = importlib.import_module(name)
    if not hasattr(module, "AllocationPlanService"):
        pytest.fail(
            f"{CONTRACT_MISSING}: missing AllocationPlanService",
            pytrace=False,
        )
    return module


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
    facts: dict[str, list[dict[str, object]]] = {}
    for model in models:
        rows = list(
            session.scalars(
                select(model)
                .where(model.tenant_id == tenant_id)
                .order_by(model.id.asc())
            ).all()
        )
        facts[model.__tablename__] = [_row_snapshot(row) for row in rows]
    return facts


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


def _seed_context(
    session,
    *,
    tenant_id: str = "tenant-a",
    suffix: str = "a",
    source_status: DemandListStatus = DemandListStatus.PUBLISHED,
    is_current: bool = True,
    include_rule: bool = True,
    second_published_rule: bool = False,
    top_available: Decimal = Decimal("5.0000"),
    alternate_available: Decimal = Decimal("10.0000"),
    demand_quantity: Decimal = Decimal("8.000000"),
    top_in_transit: Decimal = Decimal("4.0000"),
    include_repair_pipeline: bool = True,
):
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"scenario-{tenant_id}-{suffix}",
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
    session.add(group)
    session.flush()

    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{tenant_id}-{suffix}",
        name=f"Spare {suffix}",
        unit="EA",
        category="critical",
        is_critical=True,
    )
    warehouse_top = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{tenant_id}-{suffix}-01",
        name=f"Warehouse {suffix} 01",
    )
    warehouse_alt = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{tenant_id}-{suffix}-02",
        name=f"Warehouse {suffix} 02",
    )
    session.add_all([spare, warehouse_top, warehouse_alt])
    session.flush()

    location_top = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_top.id,
        code=f"PICK-{suffix}-01",
        name=f"Pick {suffix} 01",
        location_type="PICK",
        is_pickable=True,
        is_active=True,
    )
    location_alt = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_alt.id,
        code=f"PICK-{suffix}-02",
        name=f"Pick {suffix} 02",
        location_type="PICK",
        is_pickable=True,
        is_active=True,
    )
    session.add_all([location_top, location_alt])
    session.flush()

    demand_list = DemandList(
        tenant_id=tenant_id,
        name=f"Demand {suffix}",
        lineage_id=f"demand-{tenant_id}-{suffix}",
        version_number=1,
        scenario_version_id=scenario.id,
        calculation_group_id=group.id,
        status=source_status,
        is_current=is_current,
        created_by_user_id="seed-user",
        created_by_request_id=f"seed-request-{suffix}",
    )
    session.add(demand_list)
    session.flush()

    item = DemandListItem(
        tenant_id=tenant_id,
        demand_list_id=demand_list.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
        criticality_level_snapshot="CRITICAL",
        original_quantity=demand_quantity,
        final_quantity=demand_quantity,
        source_snapshot_json={"seed": suffix},
    )
    session.add(item)

    top = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse_top.id,
        location_id=location_top.id,
        spare_part_id=spare.id,
        lot_id=None,
        on_hand_quantity=top_available,
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=top_in_transit,
        version=3,
    )
    alternate = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse_alt.id,
        location_id=location_alt.id,
        spare_part_id=spare.id,
        lot_id=None,
        on_hand_quantity=alternate_available,
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
        version=7,
    )
    session.add_all([top, alternate])
    session.flush()

    if include_repair_pipeline:
        repair_item = SerializedItem(
            tenant_id=tenant_id,
            spare_part_id=spare.id,
            serial_number=f"SER-{tenant_id}-{suffix}",
            lot_id=None,
            warehouse_id=warehouse_top.id,
            location_id=location_top.id,
            status="IN_REPAIR",
            version=1,
        )
        session.add(repair_item)

    rules: list[AllocationRuleVersion] = []
    if include_rule:
        rule = AllocationRuleVersion(
            tenant_id=tenant_id,
            lineage_id=f"rule-{tenant_id}-{suffix}",
            version_number=1,
            status="PUBLISHED",
            scope_json={
                "warehouse_ids": [warehouse_top.id, warehouse_alt.id],
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
            normalization_json={
                "criticality": {"min": "0", "max": "4"}
            },
            change_reason="Task 4 RED seed",
            published_by_user_id="admin-a",
            published_by_request_id="publish-a",
            version=1,
        )
        session.add(rule)
        rules.append(rule)

        if second_published_rule:
            ambiguous = AllocationRuleVersion(
                tenant_id=tenant_id,
                lineage_id=f"rule-{tenant_id}-{suffix}-ambiguous",
                version_number=1,
                status="PUBLISHED",
                scope_json={
                    "warehouse_ids": [warehouse_top.id, warehouse_alt.id],
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
                normalization_json={
                    "criticality": {"min": "0", "max": "4"}
                },
                change_reason="Task 4 RED ambiguous seed",
                published_by_user_id="admin-a",
                published_by_request_id="publish-b",
                version=1,
            )
            session.add(ambiguous)
            rules.append(ambiguous)

    session.flush()
    return {
        "source": demand_list,
        "item": item,
        "spare": spare,
        "top": top,
        "alternate": alternate,
        "rules": rules,
    }


def test_00_gap_only_line_model_contract_can_represent_no_balance_version() -> None:
    recommended = AllocationPlanLine.__table__.c.recommended_balance_id
    expected_version = AllocationPlanLine.__table__.c.expected_balance_version

    assert recommended.nullable is True
    if expected_version.nullable is not True:
        pytest.fail(
            (
                f"{STRUCTURAL_BLOCKER}: AllocationPlanLine.expected_balance_version "
                "is NOT NULL, but a no-eligible-candidate gap-only line has "
                "recommended_balance_id=None and therefore has no real balance "
                "version to freeze. Do not use a fake sentinel version; Task 1 "
                "model/migration scope must be amended before Task 4 GREEN."
            ),
            pytrace=False,
        )


@pytest.mark.parametrize(
    ("status", "is_current", "allowed"),
    [
        (DemandListStatus.CONFIRMED, False, True),
        (DemandListStatus.PUBLISHED, True, True),
        (DemandListStatus.PUBLISHED, False, False),
        (DemandListStatus.DRAFT, False, False),
        (DemandListStatus.PENDING_CONFIRMATION, False, False),
        (DemandListStatus.VOIDED, False, False),
    ],
)
def test_create_accepts_only_confirmed_or_current_published_source(
    session,
    actor_contributor,
    status,
    is_current,
    allowed,
) -> None:
    service = _service_api().AllocationPlanService()
    context = _seed_context(
        session,
        suffix=f"source-{status.value.lower()}-{int(is_current)}",
        source_status=status,
        is_current=is_current,
    )

    if allowed:
        plan = service.create(
            session,
            actor_contributor,
            context["source"].id,
            idempotency_key=f"task4-source-{status.value}-{is_current}",
        )
        assert plan.status == "DRAFT"
        assert plan.source_demand_list_id == context["source"].id
        assert plan.source_demand_list_version == context["source"].version
        return

    with pytest.raises(AppException) as raised:
        service.create(
            session,
            actor_contributor,
            context["source"].id,
            idempotency_key=f"task4-source-{status.value}-{is_current}",
        )
    assert raised.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"


def test_create_requires_exactly_one_matching_published_rule(
    session,
    actor_contributor,
) -> None:
    service = _service_api().AllocationPlanService()

    no_rule = _seed_context(
        session,
        suffix="no-rule",
        include_rule=False,
    )
    with pytest.raises(AppException) as missing:
        service.create(
            session,
            actor_contributor,
            no_rule["source"].id,
            idempotency_key="task4-rule-missing",
        )
    assert missing.value.code == "ALLOCATION_RULE_NOT_AVAILABLE"
    assert "regenerate" in str(missing.value.details).lower()

    ambiguous = _seed_context(
        session,
        suffix="ambiguous-rule",
        second_published_rule=True,
    )
    with pytest.raises(AppException) as duplicate:
        service.create(
            session,
            actor_contributor,
            ambiguous["source"].id,
            idempotency_key="task4-rule-ambiguous",
        )
    assert duplicate.value.code == "ALLOCATION_RULE_AMBIGUOUS"
    assert "rule" in str(duplicate.value.details).lower()


def test_create_is_tenant_scoped_and_viewer_cannot_write(
    session,
    actor_contributor,
    actor_viewer,
    actor_context,
) -> None:
    service = _service_api().AllocationPlanService()
    context = _seed_context(session, suffix="tenant-scope")

    with pytest.raises(AppException) as viewer_error:
        service.create(
            session,
            actor_viewer,
            context["source"].id,
            idempotency_key="task4-viewer",
        )
    assert viewer_error.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"

    other_actor = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
    )
    with pytest.raises(AppException) as tenant_error:
        service.create(
            session,
            other_actor,
            context["source"].id,
            idempotency_key="task4-cross-tenant",
        )
    assert tenant_error.value.code in {
        "NOT_FOUND",
        "ALLOCATION_SOURCE_NOT_CURRENT",
    }


def test_create_is_idempotent_and_rejects_key_reuse_for_different_source(
    session,
    actor_contributor,
) -> None:
    service = _service_api().AllocationPlanService()
    first_context = _seed_context(session, suffix="idem-a")
    second_context = _seed_context(session, suffix="idem-b")

    first = service.create(
        session,
        actor_contributor,
        first_context["source"].id,
        idempotency_key="task4-create-idem",
    )
    replay = service.create(
        session,
        actor_contributor,
        first_context["source"].id,
        idempotency_key="task4-create-idem",
    )
    assert replay.id == first.id
    assert (
        session.query(AllocationPlan)
        .filter_by(
            tenant_id=actor_contributor.tenant_id,
            idempotency_key="task4-create-idem",
        )
        .count()
        == 1
    )

    with pytest.raises(AppException) as reused:
        service.create(
            session,
            actor_contributor,
            second_context["source"].id,
            idempotency_key="task4-create-idem",
        )
    assert reused.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_generation_freezes_source_rule_inventory_and_has_no_inventory_side_effect(
    session,
    actor_contributor,
) -> None:
    service = _service_api().AllocationPlanService()
    context = _seed_context(session, suffix="freeze")
    before = _inventory_facts(session, actor_contributor.tenant_id)

    plan = service.create(
        session,
        actor_contributor,
        context["source"].id,
        idempotency_key="task4-freeze",
    )
    lines = _plan_lines(session, actor_contributor.tenant_id, plan.id)

    assert plan.status == "DRAFT"
    assert plan.source_demand_list_id == context["source"].id
    assert plan.source_demand_list_version == context["source"].version
    assert plan.rule_id == context["rules"][0].id
    assert len(plan.inventory_fingerprint) == 64
    assert lines
    assert all(line.reservation_id is None for line in lines)
    assert _inventory_facts(session, actor_contributor.tenant_id) == before


def test_generation_uses_deterministic_top_candidate_without_auto_substitution(
    session,
    actor_contributor,
) -> None:
    service = _service_api().AllocationPlanService()
    context = _seed_context(
        session,
        suffix="deterministic",
        top_available=Decimal("5.0000"),
        alternate_available=Decimal("10.0000"),
        demand_quantity=Decimal("8.000000"),
        top_in_transit=Decimal("4.0000"),
        include_repair_pipeline=True,
    )

    plan = service.create(
        session,
        actor_contributor,
        context["source"].id,
        idempotency_key="task4-deterministic",
    )
    [line] = _plan_lines(session, actor_contributor.tenant_id, plan.id)

    assert line.recommended_balance_id == context["top"].id
    assert line.expected_balance_version == context["top"].version
    assert line.demand_quantity == Decimal("8.000000")
    assert line.allocated_quantity == Decimal("5.000000")
    assert line.gap_quantity == Decimal("3.000000")
    assert line.recommended_balance_id != context["alternate"].id

    risks = str(line.risks_json).lower()
    assert "alternative" in risks
    assert str(context["alternate"].id) in risks
    assert "in_transit" in risks or "in-transit" in risks
    assert "repair" in risks


def test_generation_gap_only_line_has_no_fake_recommended_identity(
    session,
    actor_contributor,
) -> None:
    service = _service_api().AllocationPlanService()
    context = _seed_context(
        session,
        suffix="gap-only",
        top_available=Decimal("0.0000"),
        alternate_available=Decimal("0.0000"),
        demand_quantity=Decimal("3.000000"),
        top_in_transit=Decimal("2.0000"),
    )

    plan = service.create(
        session,
        actor_contributor,
        context["source"].id,
        idempotency_key="task4-gap-only",
    )
    [line] = _plan_lines(session, actor_contributor.tenant_id, plan.id)

    assert line.recommended_balance_id is None
    assert line.recommended_lot_id is None
    assert line.recommended_serial_item_id is None
    assert line.expected_balance_version is None
    assert line.allocated_quantity == Decimal("0.000000")
    assert line.gap_quantity == Decimal("3.000000")
    assert "no_eligible" in str(line.risks_json).lower() or "no eligible" in str(
        line.risks_json
    ).lower()
