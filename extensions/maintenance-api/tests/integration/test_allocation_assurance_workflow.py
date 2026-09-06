from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.models import (
    AllocationPlanEvent,
    AllocationPlanLine,
    AllocationRuleVersion,
    AllocationSimulation,
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
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import DemandListStatus
from app.repositories.demand_list_repository import DemandListRepository
from app.schemas.allocation import (
    AllocationPlanConfirmCommand,
    AllocationPlanExecuteCommand,
    AllocationPlanLineEditCommand,
    AllocationPlanPreviewCommand,
    AllocationRuleDraftCommand,
    AllocationRulePublishCommand,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta
from app.security.actor import MaintenanceRole
from app.services.allocation_plan_service import AllocationPlanService
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_simulation_service import AllocationSimulationService
from app.services.demand_list_service import DemandListService
from app.services.inventory_transaction_service import InventoryTransactionService
from app.services.snapshot_service import snapshot_service
from app.workers.allocation_simulation_executor import AllocationSimulationExecutor
from sqlalchemy import func, select

ZERO4 = Decimal("0.0000")


def _snapshot_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    return deepcopy(value)


def _row_snapshot(row) -> dict[str, object]:
    return {
        column.name: _snapshot_value(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _inventory_facts(
    session,
    tenant_id: str,
) -> dict[str, list[dict[str, object]]]:
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
        result[model.__tablename__] = [
            _row_snapshot(row)
            for row in rows
        ]
    return result


def _plan_lines(
    session,
    tenant_id: str,
    plan_id: int,
) -> list[AllocationPlanLine]:
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


def _seed_domain(session, actor, *, suffix: str):
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
        created_by_user_id="task9-seed",
        created_by_request_id=f"task9-seed-{suffix}",
    )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    session.add_all([group, warehouse])
    session.flush()

    source = DemandList(
        tenant_id=tenant_id,
        name=f"Demand {suffix}",
        lineage_id=f"demand-{suffix}",
        version_number=1,
        scenario_version_id=scenario.id,
        calculation_group_id=group.id,
        status=DemandListStatus.PUBLISHED,
        is_current=True,
        created_by_user_id="task9-seed",
        created_by_request_id=f"task9-seed-{suffix}",
    )
    session.add(source)
    session.flush()

    spares: list[SparePart] = []
    items: list[DemandListItem] = []
    balances: list[InventoryBalance] = []
    lots: list[InventoryLot] = []
    policies: list[InventoryPolicy] = []

    for index in (1, 2):
        spare = SparePart(
            tenant_id=tenant_id,
            code=f"SP-{suffix}-{index}",
            name=f"Spare {suffix} {index}",
            unit="EA",
            category="critical",
            is_critical=True,
        )
        session.add(spare)
        session.flush()

        item = DemandListItem(
            tenant_id=tenant_id,
            demand_list_id=source.id,
            spare_part_id=spare.id,
            spare_part_code_snapshot=spare.code,
            spare_part_name_snapshot=spare.name,
            spare_part_unit_snapshot=spare.unit,
            criticality_level_snapshot="CRITICAL",
            original_quantity=Decimal("2.000000"),
            final_quantity=Decimal("2.000000"),
            source_snapshot_json={"task9": True, "index": index},
        )
        session.add(item)
        session.flush()

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
            on_hand_quantity=Decimal("6.0000"),
            reserved_quantity=ZERO4,
            damaged_quantity=ZERO4,
            quarantined_quantity=ZERO4,
            in_transit_quantity=ZERO4,
            version=2 + index,
        )
        policy = InventoryPolicy(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            spare_part_id=spare.id,
            safety_stock=ZERO4,
            reorder_point=ZERO4,
            maximum_stock=None,
            version=1,
        )
        session.add_all([balance, policy])
        session.flush()

        spares.append(spare)
        items.append(item)
        balances.append(balance)
        lots.append(lot)
        policies.append(policy)

    baseline_rule = AllocationRuleService().repository.create_rule(
        session,
        tenant_id,
        {
            "lineage_id": f"rule-{suffix}",
            "version_number": 1,
            "status": "PUBLISHED",
            "scope_json": {
                "warehouse_ids": [warehouse.id],
                "spare_part_ids": [spare.id for spare in spares],
            },
            "effective_from": None,
            "effective_to": None,
            "hard_rules_json": {
                "exclude_frozen": True,
                "exclude_expired": True,
                "require_available": True,
            },
            "weights_json": {"criticality": "1.000000"},
            "normalization_json": {
                "criticality": {
                    "min": "0",
                    "max": "4",
                }
            },
            "change_reason": "Task 9 integration baseline",
            "published_by_user_id": "task9-admin",
            "published_by_request_id": f"task9-publish-{suffix}",
            "version": 2,
        },
    )
    session.flush()

    return {
        "source": source,
        "items": items,
        "spares": spares,
        "warehouse": warehouse,
        "balances": balances,
        "lots": lots,
        "policies": policies,
        "baseline_rule": baseline_rule,
    }


def _admin_actor(actor_context, contributor, *, suffix: str):
    return actor_context(
        tenant_id=contributor.tenant_id,
        user_id=f"task9-admin-{suffix}",
        role=MaintenanceRole.ADMIN,
        request_id=f"task9-admin-request-{suffix}",
        token_id=f"task9-admin-token-{suffix}",
    )


def _candidate_command(context, *, reason: str) -> AllocationRuleDraftCommand:
    baseline = context["baseline_rule"]
    return AllocationRuleDraftCommand(
        lineage_id=baseline.lineage_id,
        scope=dict(baseline.scope_json or {}),
        effective_from=None,
        effective_to=None,
        hard_rules=dict(baseline.hard_rules_json or {}),
        weights={"criticality": Decimal("1.000000")},
        normalization={
            "criticality": {
                "min": Decimal("0"),
                "max": Decimal("4"),
            }
        },
        change_reason=reason,
    )


def _simulate_candidate(
    session,
    contributor,
    context,
    *,
    suffix: str,
):
    baseline = context["baseline_rule"]
    rule_service = AllocationRuleService()
    candidate = rule_service.create_draft(
        session,
        contributor,
        command=_candidate_command(
            context,
            reason=f"Task 9 candidate {suffix}",
        ),
    )

    inventory_before = _inventory_facts(
        session,
        contributor.tenant_id,
    )
    simulation = AllocationSimulationService().submit(
        session,
        contributor,
        candidate_rule_id=candidate.id,
        baseline_rule_id=baseline.id,
        source_demand_list_id=context["source"].id,
        sample_ref=f"task9-{suffix}",
        idempotency_key=f"task9-simulation-{suffix}",
        expected_rule_version=candidate.version,
    )
    simulation_id = simulation.id
    candidate_id = candidate.id
    session.commit()

    AllocationSimulationExecutor._run(
        contributor.tenant_id,
        simulation_id,
    )

    session.expire_all()
    completed = session.get(
        AllocationSimulation,
        simulation_id,
    )
    candidate_after = session.get(
        AllocationRuleVersion,
        candidate_id,
    )
    assert completed is not None
    assert candidate_after is not None
    assert completed.status == "COMPLETED"
    assert completed.candidate_rule_id == candidate_id
    assert completed.baseline_rule_id == baseline.id
    assert completed.source_demand_list_id == context["source"].id
    assert isinstance(completed.input_snapshot_json, dict)
    frozen_inventory = completed.input_snapshot_json["inventory"]
    assert completed.inventory_fingerprint == snapshot_service.canonical_hash(
        frozen_inventory
    )
    assert candidate_after.status == "SIMULATED"
    assert _inventory_facts(
        session,
        contributor.tenant_id,
    ) == inventory_before

    summary = AllocationSimulationService().latest_for_rule(
        session,
        contributor.tenant_id,
        candidate_id,
    )
    assert summary is not None
    assert summary.status == "COMPLETED"
    assert not summary.blockers
    return candidate_after, summary


def _publish_candidate(
    session,
    contributor,
    admin,
    context,
    *,
    suffix: str,
):
    candidate, summary = _simulate_candidate(
        session,
        contributor,
        context,
        suffix=suffix,
    )
    rule_service = AllocationRuleService()
    command = AllocationRulePublishCommand(
        expected_version=candidate.version,
    )
    key = f"task9-rule-publish-{suffix}"
    published = rule_service.publish(
        session,
        admin,
        candidate.id,
        command=command,
        latest_simulation=summary,
        idempotency_key=key,
    )
    replay = rule_service.publish(
        session,
        admin,
        candidate.id,
        command=command,
        latest_simulation=summary,
        idempotency_key=key,
    )

    assert replay.id == published.id
    assert replay.publish_request_hash == published.publish_request_hash
    assert published.status == "PUBLISHED"
    assert published.published_by_user_id == admin.user_id
    assert published.published_by_request_id == admin.request_id
    assert published.publish_idempotency_key == key
    assert published.publish_request_hash
    assert len(published.publish_request_hash) == 64
    assert isinstance(published.publish_response_snapshot_json, dict)
    return published


def _publish_newer_source(
    session,
    admin,
    context,
    *,
    suffix: str,
):
    source = context["source"]
    repository = DemandListRepository()
    newer = repository.create_version(
        session,
        admin.tenant_id,
        {
            "name": f"{source.name} superseding {suffix}",
            "description": "Task 9 source-drift integration version",
            "lineage_id": source.lineage_id,
            "derived_from_id": source.id,
            "scenario_version_id": source.scenario_version_id,
            "calculation_group_id": source.calculation_group_id,
            "status": DemandListStatus.CONFIRMED,
            "is_current": False,
            "created_by_user_id": admin.user_id,
            "created_by_request_id": admin.request_id,
        },
    )
    for source_item in context["items"]:
        repository.add_item(
            session,
            admin.tenant_id,
            demand_list_id=newer.id,
            spare_part_id=source_item.spare_part_id,
            original_quantity=source_item.original_quantity,
            final_quantity=source_item.final_quantity,
            source_snapshot=deepcopy(source_item.source_snapshot_json),
            spare_part_code_snapshot=source_item.spare_part_code_snapshot,
            spare_part_name_snapshot=source_item.spare_part_name_snapshot,
            spare_part_unit_snapshot=source_item.spare_part_unit_snapshot,
            criticality_level_snapshot=source_item.criticality_level_snapshot,
            decision_snapshot_json=deepcopy(source_item.decision_snapshot_json),
            interval_snapshot_json=deepcopy(source_item.interval_snapshot_json),
            parameter_snapshot_json=deepcopy(source_item.parameter_snapshot_json),
            warning_snapshot_json=deepcopy(source_item.warning_snapshot_json),
            inventory_snapshot_json=deepcopy(source_item.inventory_snapshot_json),
        )

    published = DemandListService().publish(
        session,
        admin,
        newer.id,
        expected_version=newer.version,
        idempotency_key=f"task9-source-publish-{suffix}",
    )
    assert published.status is DemandListStatus.PUBLISHED
    assert published.is_current is True

    session.expire_all()
    previous = session.get(DemandList, source.id)
    assert previous is not None
    assert previous.is_current is False
    assert previous.superseded_by_id == published.id
    return published


def _plan_events(session, tenant_id: str, plan_id: int) -> list[AllocationPlanEvent]:
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


def test_simulation_executor_preserves_inventory_facts(
    session,
    actor_contributor,
) -> None:
    context = _seed_domain(
        session,
        actor_contributor,
        suffix="task9-simulation",
    )
    candidate, _summary = _simulate_candidate(
        session,
        actor_contributor,
        context,
        suffix="simulation-preserves-inventory",
    )

    assert candidate.status == "SIMULATED"


def test_execute_partial_conflict_replay_is_idempotent(
    session,
    actor_contributor,
    actor_context,
) -> None:
    context = _seed_domain(
        session,
        actor_contributor,
        suffix="task9-execute",
    )
    admin = _admin_actor(
        actor_context,
        actor_contributor,
        suffix="execute",
    )
    published_rule = _publish_candidate(
        session,
        actor_contributor,
        admin,
        context,
        suffix="execute",
    )

    service = AllocationPlanService()
    plan = service.create(
        session,
        actor_contributor,
        context["source"].id,
        idempotency_key="task9-plan-create",
        expected_source_version=context["source"].version,
    )
    assert plan.rule_id == published_rule.id

    lines = _plan_lines(
        session,
        actor_contributor.tenant_id,
        plan.id,
    )
    assert len(lines) == 2
    line_by_spare = {
        line.spare_part_id: line
        for line in lines
    }
    first_line = line_by_spare[context["spares"][0].id]
    second_line = line_by_spare[context["spares"][1].id]
    first_balance, second_balance = context["balances"]
    assert first_line.recommended_balance_id == first_balance.id
    assert second_line.recommended_balance_id == second_balance.id
    assert first_line.expected_balance_version == first_balance.version
    assert second_line.expected_balance_version == second_balance.version

    edited = service.edit_line(
        session,
        actor_contributor,
        plan.id,
        first_line.id,
        command=AllocationPlanLineEditCommand(
            expected_plan_version=plan.version,
            expected_line_version=first_line.version,
            allocated_quantity=Decimal("1.000000"),
            reason="Task 9 exercises the real allocation edit authority",
        ),
    )
    assert edited.allocated_quantity == Decimal("1.000000")
    assert edited.gap_quantity == Decimal("1.000000")
    assert edited.manual_override_json
    session.refresh(plan)

    previewed = service.preview(
        session,
        actor_contributor,
        plan.id,
        command=AllocationPlanPreviewCommand(
            expected_version=plan.version,
        ),
    )
    confirmed = service.confirm(
        session,
        actor_contributor,
        plan.id,
        command=AllocationPlanConfirmCommand(
            expected_version=previewed.version,
        ),
        idempotency_key="task9-plan-confirm",
    )
    execute_command = AllocationPlanExecuteCommand(
        expected_version=confirmed.version,
    )

    stale_expected_version = second_line.expected_balance_version
    assert stale_expected_version is not None
    adjustment = InventoryTransactionService().adjust(
        session,
        admin,
        balance_id=second_balance.id,
        expected_version=stale_expected_version,
        deltas=InventoryQuantityDelta(
            on_hand=Decimal("1.0000"),
        ),
        reason="Task 9 legitimate concurrent inventory drift",
        idempotency_key="task9-second-balance-drift",
    )
    assert adjustment.status == "COMPLETED"
    assert len(adjustment.entries) == 1
    [adjustment_entry] = adjustment.entries
    actual_version = adjustment_entry.resulting_balance_version
    assert actual_version == stale_expected_version + 1

    first_result = service.execute(
        session,
        actor_contributor,
        plan.id,
        command=execute_command,
        idempotency_key="task9-plan-execute",
    )

    assert first_result.status == "PARTIALLY_COMPLETED"
    outcomes = [
        result.outcome
        for result in first_result.line_results
    ]
    assert outcomes.count("RESERVED") == 1
    assert outcomes.count("CONFLICT") == 1

    reserved = next(
        result
        for result in first_result.line_results
        if result.outcome == "RESERVED"
    )
    conflict = next(
        result
        for result in first_result.line_results
        if result.outcome == "CONFLICT"
    )
    assert reserved.line_id == first_line.id
    assert conflict.line_id == second_line.id
    assert conflict.cause_code == "INVENTORY_VERSION_CONFLICT"
    assert conflict.retryable is False
    assert conflict.suggested_action == "regenerate"
    assert conflict.details["cause_retryable"] is True
    assert conflict.details["expected_version"] == stale_expected_version
    assert conflict.details["actual_version"] == actual_version

    assert reserved.reservation_id is not None
    reservation = session.get(
        InventoryReservation,
        reserved.reservation_id,
    )
    assert reservation is not None
    assert reservation.owner_type == "ALLOCATION_PLAN"
    assert reservation.owner_id == str(plan.id)
    assert reservation.actor_user_id == actor_contributor.user_id
    assert reservation.actor_roles_json == [actor_contributor.role.value]
    assert reservation.request_id == actor_contributor.request_id

    reservation_lines = list(
        session.scalars(
            select(InventoryReservationLine)
            .where(
                InventoryReservationLine.tenant_id
                == actor_contributor.tenant_id,
                InventoryReservationLine.reservation_id
                == reservation.id,
            )
            .order_by(InventoryReservationLine.id.asc())
        ).all()
    )
    assert len(reservation_lines) == 1
    [reservation_line] = reservation_lines
    assert reservation_line.balance_id == first_balance.id
    assert reservation_line.reserved_quantity == Decimal("1.0000")

    child_key = reserved.details["child_idempotency_key"]
    assert child_key == (
        f"allocation-plan:{plan.id}:line:{first_line.id}:"
        f"execute:{first_result.execution_id}"
    )
    reserve_transaction = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.tenant_id
            == actor_contributor.tenant_id,
            InventoryTransaction.operation_type == "RESERVE",
            InventoryTransaction.idempotency_key == child_key,
        )
    )
    assert reserve_transaction is not None
    assert reserve_transaction.status == "COMPLETED"
    assert reserve_transaction.reference_type == "INVENTORY_RESERVATION"
    assert reserve_transaction.reference_id == str(reservation.id)
    assert reserve_transaction.actor_user_id == actor_contributor.user_id
    assert reserve_transaction.actor_roles_json == [
        actor_contributor.role.value
    ]
    assert reserve_transaction.request_id == actor_contributor.request_id

    transaction_snapshot = reserve_transaction.response_snapshot_json
    assert isinstance(transaction_snapshot, dict)
    transaction_extensions = transaction_snapshot["_extensions"]
    assert isinstance(transaction_extensions, dict)
    reservation_snapshot = transaction_extensions["reservation"]
    assert reservation_snapshot["id"] == reservation.id
    audit_context = transaction_extensions["audit_context"]
    assert audit_context["reservation_id"] == reservation.id
    assert audit_context["allocation_plan_id"] == plan.id
    assert audit_context["allocation_plan_line_id"] == first_line.id
    assert audit_context["allocation_execution_id"] == (
        first_result.execution_id
    )

    ledger_entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.tenant_id
                == actor_contributor.tenant_id,
                InventoryLedgerEntry.transaction_id
                == reserve_transaction.id,
            )
            .order_by(InventoryLedgerEntry.id.asc())
        ).all()
    )
    assert len(ledger_entries) == 1
    [ledger_entry] = ledger_entries
    assert ledger_entry.balance_id == first_balance.id
    assert ledger_entry.on_hand_delta == ZERO4
    assert ledger_entry.reserved_delta == Decimal("1.0000")
    assert ledger_entry.resulting_balance_version > (
        ledger_entry.before_balance_version
    )

    reservation_count = session.scalar(
        select(func.count())
        .select_from(InventoryReservation)
        .where(
            InventoryReservation.tenant_id
            == actor_contributor.tenant_id
        )
    )
    assert reservation_count == 1

    failed_balance_reservation_lines = session.scalar(
        select(func.count())
        .select_from(InventoryReservationLine)
        .where(
            InventoryReservationLine.tenant_id
            == actor_contributor.tenant_id,
            InventoryReservationLine.balance_id
            == second_balance.id,
        )
    )
    assert failed_balance_reservation_lines == 0

    after_first = _inventory_facts(
        session,
        actor_contributor.tenant_id,
    )
    replay = service.execute(
        session,
        actor_contributor,
        plan.id,
        command=execute_command,
        idempotency_key="task9-plan-execute",
    )

    assert replay.model_dump(mode="json") == first_result.model_dump(
        mode="json"
    )
    assert _inventory_facts(
        session,
        actor_contributor.tenant_id,
    ) == after_first

    events = _plan_events(
        session,
        actor_contributor.tenant_id,
        plan.id,
    )
    event_types = {event.event_type for event in events}
    assert {
        "PLAN_CREATED",
        "LINE_EDITED",
        "PREVIEWED",
        "CONFIRMED",
        "EXECUTION_STARTED",
        "LINE_EXECUTED",
        "EXECUTION_PARTIALLY_COMPLETED",
    }.issubset(event_types)
    for event in events:
        if event.event_type in {
            "PLAN_CREATED",
            "LINE_EDITED",
            "PREVIEWED",
            "CONFIRMED",
            "EXECUTION_STARTED",
            "LINE_EXECUTED",
            "EXECUTION_PARTIALLY_COMPLETED",
        }:
            assert event.actor_user_id == actor_contributor.user_id
            assert event.actor_roles_json == [actor_contributor.role.value]
            assert event.request_id == actor_contributor.request_id


def test_execute_blocks_superseded_source_before_inventory_mutation(
    session,
    actor_contributor,
    actor_context,
) -> None:
    context = _seed_domain(
        session,
        actor_contributor,
        suffix="task9-source-drift",
    )
    admin = _admin_actor(
        actor_context,
        actor_contributor,
        suffix="source-drift",
    )
    published_rule = _publish_candidate(
        session,
        actor_contributor,
        admin,
        context,
        suffix="source-drift",
    )

    service = AllocationPlanService()
    plan = service.create(
        session,
        actor_contributor,
        context["source"].id,
        idempotency_key="task9-source-drift-plan-create",
        expected_source_version=context["source"].version,
    )
    assert plan.rule_id == published_rule.id
    previewed = service.preview(
        session,
        actor_contributor,
        plan.id,
        command=AllocationPlanPreviewCommand(
            expected_version=plan.version,
        ),
    )
    confirmed = service.confirm(
        session,
        actor_contributor,
        plan.id,
        command=AllocationPlanConfirmCommand(
            expected_version=previewed.version,
        ),
        idempotency_key="task9-source-drift-plan-confirm",
    )
    execute_command = AllocationPlanExecuteCommand(
        expected_version=confirmed.version,
    )

    newer = _publish_newer_source(
        session,
        admin,
        context,
        suffix="source-drift",
    )
    assert newer.lineage_id == context["source"].lineage_id

    before = _inventory_facts(
        session,
        actor_contributor.tenant_id,
    )
    reservations_before = session.scalar(
        select(func.count())
        .select_from(InventoryReservation)
        .where(
            InventoryReservation.tenant_id
            == actor_contributor.tenant_id
        )
    )

    with pytest.raises(ConflictError) as captured:
        service.execute(
            session,
            actor_contributor,
            plan.id,
            command=execute_command,
            idempotency_key="task9-source-drift-plan-execute",
        )

    assert captured.value.code == "ALLOCATION_SOURCE_NOT_CURRENT"
    assert captured.value.details["fact"] == "source"
    assert captured.value.details["source_demand_list_id"] == context["source"].id
    assert captured.value.details["retryable"] is False
    assert captured.value.details["suggested_action"] == "regenerate"
    assert _inventory_facts(
        session,
        actor_contributor.tenant_id,
    ) == before

    reservations_after = session.scalar(
        select(func.count())
        .select_from(InventoryReservation)
        .where(
            InventoryReservation.tenant_id
            == actor_contributor.tenant_id
        )
    )
    assert reservations_after == reservations_before
