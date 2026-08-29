from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from app.core.exceptions import (
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    AIReviewFinding,
    AIReviewRun,
    AllocationPlanEvent,
    AllocationPlanLine,
    AllocationRuleVersion,
    AllocationSimulation,
    CalculationGroup,
    DemandList,
    DemandListEvent,
    DemandListItem,
    DemandReviewDecision,
    DemandReviewEvent,
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
from app.models.enums import (
    CalculationGroupStatus,
    DemandListEventType,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from app.schemas.allocation import (
    AllocationPlanConfirmCommand,
    AllocationPlanExecuteCommand,
    AllocationPlanPreviewCommand,
    AllocationRuleDraftCommand,
    AllocationRulePublishCommand,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.allocation_plan_service import AllocationPlanService
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_simulation_service import AllocationSimulationService
from app.services.demand_list_service import DemandListService
from app.services.demand_review_service import DemandReviewService
from app.workers.allocation_simulation_executor import AllocationSimulationExecutor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

ZERO4 = Decimal("0.0000")


def _count_rows(
    session: Session,
    model,
    *,
    tenant_id: str | None = None,
) -> int:
    statement = select(func.count()).select_from(model)
    if tenant_id is not None and hasattr(model, "tenant_id"):
        statement = statement.where(model.tenant_id == tenant_id)
    return int(session.scalar(statement) or 0)


def _seed_published_review_source(
    session: Session,
    actor: ActorContext,
) -> tuple[DemandList, DemandListItem, SparePart]:
    template = DemandScenarioTemplate(
        tenant_id=actor.tenant_id,
        code="SC-TASK9-CROSS-DOMAIN",
        name="Task 9 cross-domain scenario",
    )
    session.add(template)
    session.flush()

    scenario = DemandScenarioVersion(
        tenant_id=actor.tenant_id,
        scenario_template_id=template.id,
        version_code="TASK9-CD-V1",
        version_name="Task 9 cross-domain version",
    )
    session.add(scenario)
    session.flush()

    group = CalculationGroup(
        tenant_id=actor.tenant_id,
        scenario_version_id=scenario.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id=actor.user_id,
        created_by_request_id=actor.request_id,
    )
    spare = SparePart(
        tenant_id=actor.tenant_id,
        code="SP-TASK9-CROSS-DOMAIN",
        name="Task 9 cross-domain spare",
        unit="EA",
        category="critical",
        is_critical=True,
    )
    session.add_all([group, spare])
    session.flush()

    repository = DemandListRepository()
    source = repository.create_version(
        session,
        actor.tenant_id,
        {
            "name": "Task 9 authoritative source",
            "description": "Cross-domain source for Plan 05-4 closure",
            "scenario_version_id": scenario.id,
            "calculation_group_id": group.id,
            "status": DemandListStatus.PUBLISHED,
            "is_current": True,
            "created_by_user_id": actor.user_id,
            "created_by_request_id": actor.request_id,
        },
    )
    source.status = DemandListStatus.PUBLISHED
    source.is_current = True
    session.flush()

    child_id = 9101
    quantity = Decimal("10.000000")
    item = repository.add_item(
        session,
        actor.tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        original_quantity=quantity,
        final_quantity=quantity,
        source_snapshot={
            "recommended_spare_quantity": format(quantity, "f"),
            "task9_cross_domain": True,
        },
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
    )
    item.criticality_level_snapshot = "HIGH"
    item.decision_snapshot_json = {
        "source_child_id": child_id,
    }
    item.interval_snapshot_json = {
        "system_source_child_id": child_id,
        "selected_child_id": child_id,
        "candidates": [
            {
                "child_id": child_id,
                "candidate_key": "task9-cross-domain-candidate",
                "reliability_model": "WEIBULL",
                "execution_mode": "ANALYTICAL",
                "recommended_quantity": format(quantity, "f"),
                "p50": format(quantity, "f"),
                "p80": format(quantity, "f"),
                "p90": format(quantity, "f"),
                "p95": format(quantity, "f"),
                "p99": format(quantity, "f"),
                "warnings": [],
            }
        ],
    }
    item.warning_snapshot_json = []
    item.inventory_snapshot_json = {
        "task9_review_inventory": "0.000000",
    }
    session.flush()
    return source, item, spare


def _source_item_facts(item: DemandListItem) -> dict[str, object]:
    return {
        "final_quantity": item.final_quantity,
        "decision_type": item.decision_type,
        "decision_reason": item.decision_reason,
        "decision_snapshot": deepcopy(item.decision_snapshot_json),
        "interval_snapshot": deepcopy(item.interval_snapshot_json),
        "parameter_snapshot": deepcopy(item.parameter_snapshot_json),
        "warning_snapshot": deepcopy(item.warning_snapshot_json),
        "inventory_snapshot": deepcopy(item.inventory_snapshot_json),
        "version": item.version,
    }


def _seed_allocation_inventory(
    session: Session,
    actor: ActorContext,
    spare: SparePart,
) -> tuple[Warehouse, InventoryBalance]:
    warehouse = Warehouse(
        tenant_id=actor.tenant_id,
        code="WH-TASK9-CROSS-DOMAIN",
        name="Task 9 cross-domain warehouse",
    )
    session.add(warehouse)
    session.flush()

    location = WarehouseLocation(
        tenant_id=actor.tenant_id,
        warehouse_id=warehouse.id,
        code="PICK-TASK9-CROSS-DOMAIN",
        name="Task 9 pick location",
        location_type="PICK",
        is_pickable=True,
        is_active=True,
    )
    lot = InventoryLot(
        tenant_id=actor.tenant_id,
        spare_part_id=spare.id,
        lot_code="LOT-TASK9-CROSS-DOMAIN",
        received_date=date(2026, 8, 1),
        expiry_date=date(2027, 8, 1),
        quality_status="AVAILABLE",
        is_frozen=False,
    )
    session.add_all([location, lot])
    session.flush()

    balance = InventoryBalance(
        tenant_id=actor.tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare.id,
        lot_id=lot.id,
        on_hand_quantity=Decimal("5.0000"),
        reserved_quantity=ZERO4,
        damaged_quantity=ZERO4,
        quarantined_quantity=ZERO4,
        in_transit_quantity=ZERO4,
        version=1,
    )
    policy = InventoryPolicy(
        tenant_id=actor.tenant_id,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        safety_stock=ZERO4,
        reorder_point=ZERO4,
        maximum_stock=None,
        version=1,
    )
    session.add_all([balance, policy])
    session.flush()
    return warehouse, balance


def _inventory_business_facts(
    session: Session,
    tenant_id: str,
) -> dict[str, object]:
    balances = list(
        session.scalars(
            select(InventoryBalance)
            .where(InventoryBalance.tenant_id == tenant_id)
            .order_by(InventoryBalance.id.asc())
        ).all()
    )
    return {
        "balances": [
            (
                row.id,
                row.on_hand_quantity,
                row.reserved_quantity,
                row.damaged_quantity,
                row.quarantined_quantity,
                row.in_transit_quantity,
                row.version,
            )
            for row in balances
        ],
        "transactions": _count_rows(
            session,
            InventoryTransaction,
            tenant_id=tenant_id,
        ),
        "ledger_entries": _count_rows(
            session,
            InventoryLedgerEntry,
            tenant_id=tenant_id,
        ),
        "reservations": _count_rows(
            session,
            InventoryReservation,
            tenant_id=tenant_id,
        ),
        "reservation_lines": _count_rows(
            session,
            InventoryReservationLine,
            tenant_id=tenant_id,
        ),
    }


def _plan_lines(
    session: Session,
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


def test_plan05_04_cross_domain_authority_lineage_and_inventory_trace(
    session: Session,
    actor_context,
) -> None:
    contributor = actor_context(
        tenant_id="tenant-task9-cross-domain",
        user_id="task9-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="task9-contributor-request",
        token_id="task9-contributor-token",
    )
    admin = actor_context(
        tenant_id="tenant-task9-cross-domain",
        user_id="task9-admin",
        role=MaintenanceRole.ADMIN,
        request_id="task9-admin-request",
        token_id="task9-admin-token",
    )
    other_tenant_viewer = actor_context(
        tenant_id="tenant-task9-other",
        user_id="task9-other-viewer",
        role=MaintenanceRole.VIEWER,
        request_id="task9-other-request",
        token_id="task9-other-token",
    )

    source, source_item, spare = _seed_published_review_source(
        session,
        contributor,
    )
    source_id = source.id
    source_version = source.version
    source_lineage = source.lineage_id
    source_item_id = source_item.id
    source_item_before = _source_item_facts(source_item)

    ai_runs_before = _count_rows(session, AIReviewRun)
    ai_findings_before = _count_rows(session, AIReviewFinding)

    review_service = DemandReviewService()
    review_run_key = "task9-cross-domain-review-run"
    review = review_service.run(
        session,
        contributor,
        source.id,
        expected_source_version=source.version,
        idempotency_key=review_run_key,
    )
    review_replay = review_service.run(
        session,
        contributor,
        source.id,
        expected_source_version=source_version,
        idempotency_key=review_run_key,
    )
    assert review_replay.id == review.id
    assert review_replay.input_hash == review.input_hash
    assert review.status is DemandReviewStatus.OPEN
    assert review.source_demand_list_id == source_id
    assert review.source_demand_list_version == source_version

    inventory_gap = next(
        finding
        for finding in review.findings
        if finding.rule_code == "INVENTORY_GAP"
        and finding.source_demand_list_item_id == source_item_id
    )
    assert inventory_gap.blocking is True

    edited_quantity = Decimal("2.000000")
    state = review_service.decide_finding(
        session,
        admin,
        review.id,
        inventory_gap.id,
        expected_review_version=review.version,
        expected_finding_version=inventory_gap.version,
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity=edited_quantity,
        reason="Task 9 admin turns review evidence into an authoritative quantity",
        idempotency_key="task9-cross-domain-review-edit",
    )

    resolver_keys: list[str] = []
    while state.pending_blocking_finding_count:
        pending = next(
            finding
            for finding in state.findings
            if finding.blocking
            and finding.decision_status
            is DemandReviewDecisionStatus.PENDING
        )
        key = f"task9-cross-domain-review-resolve-{pending.id}"
        resolver_keys.append(key)
        state = review_service.decide_finding(
            session,
            admin,
            state.id,
            pending.id,
            expected_review_version=state.version,
            expected_finding_version=pending.version,
            action=DemandReviewDecisionStatus.REJECTED,
            final_quantity=None,
            reason="Task 9 admin resolves remaining formal review evidence",
            idempotency_key=key,
        )

    assert state.status is DemandReviewStatus.READY_TO_DERIVE
    derive_key = "task9-cross-domain-review-derive"
    derived_result = review_service.derive(
        session,
        admin,
        state.id,
        expected_review_version=state.version,
        idempotency_key=derive_key,
    )
    derived = derived_result.derived_demand_list
    assert derived_result.review.status is DemandReviewStatus.DERIVED
    assert derived.status is DemandListStatus.DRAFT
    assert derived.derived_from_id == source_id
    assert derived.lineage_id == source_lineage
    assert derived.version_number == source.version_number + 1
    assert len(derived.items) == 1
    assert derived.items[0].final_quantity == edited_quantity

    session.expire_all()
    source_after_derive = session.get(DemandList, source_id)
    source_item_after_derive = session.get(DemandListItem, source_item_id)
    assert source_after_derive is not None
    assert source_item_after_derive is not None
    assert source_after_derive.status is DemandListStatus.PUBLISHED
    assert source_after_derive.is_current is True
    assert source_after_derive.version == source_version
    assert _source_item_facts(source_item_after_derive) == source_item_before

    review_events = list(
        session.scalars(
            select(DemandReviewEvent)
            .where(
                DemandReviewEvent.tenant_id == contributor.tenant_id,
                DemandReviewEvent.review_id == review.id,
            )
            .order_by(DemandReviewEvent.id.asc())
        ).all()
    )
    command_events = [
        event
        for event in review_events
        if event.command_type is not None
    ]
    run_event = next(
        event
        for event in command_events
        if event.command_type is DemandReviewCommandType.RUN
    )
    assert run_event.actor_user_id == contributor.user_id
    assert run_event.actor_roles_json == [contributor.role.value]
    assert run_event.request_id == contributor.request_id
    assert run_event.idempotency_key == review_run_key

    derive_event = next(
        event
        for event in command_events
        if event.command_type is DemandReviewCommandType.DERIVE
    )
    assert derive_event.actor_user_id == admin.user_id
    assert derive_event.actor_roles_json == [admin.role.value]
    assert derive_event.request_id == admin.request_id
    assert derive_event.idempotency_key == derive_key
    assert all(
        event.request_hash is not None
        and len(event.request_hash) == 64
        for event in command_events
    )

    decisions = list(
        session.scalars(
            select(DemandReviewDecision)
            .where(
                DemandReviewDecision.tenant_id == contributor.tenant_id,
                DemandReviewDecision.review_id == review.id,
            )
            .order_by(DemandReviewDecision.id.asc())
        ).all()
    )
    assert decisions
    assert all(
        decision.actor_user_id == admin.user_id
        for decision in decisions
    )
    assert all(
        decision.actor_roles_json == [admin.role.value]
        for decision in decisions
    )
    assert all(
        decision.request_id == admin.request_id
        for decision in decisions
    )
    assert all(
        decision.request_hash is not None
        and len(decision.request_hash) == 64
        for decision in decisions
    )
    assert _count_rows(session, AIReviewRun) == ai_runs_before
    assert _count_rows(session, AIReviewFinding) == ai_findings_before

    demand_service = DemandListService()
    submitted = demand_service.submit(
        session,
        contributor,
        derived.id,
        expected_version=derived.version,
        idempotency_key="task9-cross-domain-demand-submit",
    )
    assert submitted.status is DemandListStatus.PENDING_CONFIRMATION

    with pytest.raises(InsufficientMaintenanceRoleError):
        demand_service.confirm(
            session,
            contributor,
            derived.id,
            expected_version=submitted.version,
            confirmation_note="Contributor must not be final authority",
            idempotency_key="task9-cross-domain-demand-confirm-forbidden",
        )

    confirmed = demand_service.confirm(
        session,
        admin,
        derived.id,
        expected_version=submitted.version,
        confirmation_note="Task 9 admin confirms reviewed demand",
        idempotency_key="task9-cross-domain-demand-confirm",
    )
    assert confirmed.status is DemandListStatus.CONFIRMED

    published = demand_service.publish(
        session,
        admin,
        derived.id,
        expected_version=confirmed.version,
        idempotency_key="task9-cross-domain-demand-publish",
    )
    published_replay = demand_service.publish(
        session,
        admin,
        derived.id,
        expected_version=confirmed.version,
        idempotency_key="task9-cross-domain-demand-publish",
    )
    assert published_replay == published
    assert published.status is DemandListStatus.PUBLISHED
    assert published.is_current is True
    assert published.lineage_id == source_lineage

    session.expire_all()
    source_after_publish = session.get(DemandList, source_id)
    published_row = session.get(DemandList, published.id)
    source_item_after_publish = session.get(DemandListItem, source_item_id)
    assert source_after_publish is not None
    assert published_row is not None
    assert source_item_after_publish is not None
    assert source_after_publish.status is DemandListStatus.PUBLISHED
    assert source_after_publish.is_current is False
    assert source_after_publish.superseded_by_id == published.id
    assert source_after_publish.superseded_at is not None
    assert _source_item_facts(source_item_after_publish) == source_item_before
    assert published_row.derived_from_id == source_id
    assert published_row.lineage_id == source_lineage
    assert published_row.is_current is True

    with pytest.raises(NotFoundError):
        demand_service.get(
            session,
            other_tenant_viewer,
            published.id,
        )

    demand_events = list(
        session.scalars(
            select(DemandListEvent)
            .where(
                DemandListEvent.tenant_id == contributor.tenant_id,
                DemandListEvent.demand_list_id == published.id,
            )
            .order_by(DemandListEvent.id.asc())
        ).all()
    )
    lifecycle_events = {
        event.event_type: event
        for event in demand_events
        if event.event_type
        in {
            DemandListEventType.SUBMITTED,
            DemandListEventType.CONFIRMED,
            DemandListEventType.PUBLISHED,
        }
    }
    assert set(lifecycle_events) == {
        DemandListEventType.SUBMITTED,
        DemandListEventType.CONFIRMED,
        DemandListEventType.PUBLISHED,
    }
    assert all(
        event.idempotency_key
        and event.request_hash
        and len(event.request_hash) == 64
        for event in lifecycle_events.values()
    )
    submitted_event = lifecycle_events[DemandListEventType.SUBMITTED]
    confirmed_event = lifecycle_events[DemandListEventType.CONFIRMED]
    published_event = lifecycle_events[DemandListEventType.PUBLISHED]
    assert submitted_event.actor_user_id == contributor.user_id
    assert submitted_event.actor_roles_json == [contributor.role.value]
    assert submitted_event.request_id == contributor.request_id
    assert confirmed_event.actor_user_id == admin.user_id
    assert confirmed_event.actor_roles_json == [admin.role.value]
    assert confirmed_event.request_id == admin.request_id
    assert published_event.actor_user_id == admin.user_id
    assert published_event.actor_roles_json == [admin.role.value]
    assert published_event.request_id == admin.request_id

    warehouse, balance = _seed_allocation_inventory(
        session,
        contributor,
        spare,
    )
    inventory_before_simulation = _inventory_business_facts(
        session,
        contributor.tenant_id,
    )

    rule_service = AllocationRuleService()
    candidate = rule_service.create_draft(
        session,
        contributor,
        command=AllocationRuleDraftCommand(
            lineage_id="task9-cross-domain-rule",
            scope={
                "warehouse_ids": [warehouse.id],
                "spare_part_ids": [spare.id],
            },
            effective_from=None,
            effective_to=None,
            hard_rules={
                "exclude_frozen": True,
                "exclude_expired": True,
                "require_available": True,
            },
            weights={
                "criticality": Decimal("1.000000"),
            },
            normalization={
                "criticality": {
                    "min": Decimal("0"),
                    "max": Decimal("4"),
                }
            },
            change_reason="Task 9 cross-domain allocation assurance",
        ),
    )

    simulation_service = AllocationSimulationService()
    simulation = simulation_service.submit(
        session,
        contributor,
        candidate_rule_id=candidate.id,
        baseline_rule_id=None,
        source_demand_list_id=published.id,
        sample_ref="task9-cross-domain",
        idempotency_key="task9-cross-domain-simulation",
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
    completed_simulation = session.get(
        AllocationSimulation,
        simulation_id,
    )
    candidate_after_simulation = session.get(
        AllocationRuleVersion,
        candidate_id,
    )
    assert completed_simulation is not None
    assert candidate_after_simulation is not None
    assert completed_simulation.status == "COMPLETED"
    assert candidate_after_simulation.status == "SIMULATED"
    assert completed_simulation.inventory_fingerprint
    assert _inventory_business_facts(
        session,
        contributor.tenant_id,
    ) == inventory_before_simulation

    simulation_summary = simulation_service.latest_for_rule(
        session,
        contributor.tenant_id,
        candidate_id,
    )
    assert simulation_summary is not None
    assert simulation_summary.status == "COMPLETED"
    assert not simulation_summary.blockers

    publish_command = AllocationRulePublishCommand(
        expected_version=candidate_after_simulation.version,
    )
    published_rule = rule_service.publish(
        session,
        admin,
        candidate_id,
        command=publish_command,
        latest_simulation=simulation_summary,
        idempotency_key="task9-cross-domain-rule-publish",
    )
    rule_replay = rule_service.publish(
        session,
        admin,
        candidate_id,
        command=publish_command,
        latest_simulation=simulation_summary,
        idempotency_key="task9-cross-domain-rule-publish",
    )
    assert rule_replay.id == published_rule.id
    assert rule_replay.publish_request_hash == (
        published_rule.publish_request_hash
    )
    assert published_rule.status == "PUBLISHED"
    assert published_rule.published_by_user_id == admin.user_id
    assert published_rule.published_by_request_id == admin.request_id
    assert published_rule.publish_idempotency_key == (
        "task9-cross-domain-rule-publish"
    )

    plan_service = AllocationPlanService()
    plan = plan_service.create(
        session,
        contributor,
        published.id,
        idempotency_key="task9-cross-domain-plan-create",
        expected_source_version=published.version,
    )
    plan_replay = plan_service.create(
        session,
        contributor,
        published.id,
        idempotency_key="task9-cross-domain-plan-create",
        expected_source_version=published.version,
    )
    assert plan_replay.id == plan.id
    assert plan.source_demand_list_id == published.id
    assert plan.source_demand_list_version == published.version
    assert plan.rule_id == published_rule.id

    [line] = _plan_lines(
        session,
        contributor.tenant_id,
        plan.id,
    )
    assert line.spare_part_id == spare.id
    assert line.recommended_balance_id == balance.id
    assert line.allocated_quantity == edited_quantity
    assert line.gap_quantity == Decimal("0.000000")
    assert line.expected_balance_version == balance.version

    previewed = plan_service.preview(
        session,
        contributor,
        plan.id,
        command=AllocationPlanPreviewCommand(
            expected_version=plan.version,
        ),
    )
    confirmed_plan = plan_service.confirm(
        session,
        contributor,
        plan.id,
        command=AllocationPlanConfirmCommand(
            expected_version=previewed.version,
        ),
        idempotency_key="task9-cross-domain-plan-confirm",
    )
    execute_command = AllocationPlanExecuteCommand(
        expected_version=confirmed_plan.version,
    )
    executed = plan_service.execute(
        session,
        contributor,
        plan.id,
        command=execute_command,
        idempotency_key="task9-cross-domain-plan-execute",
    )
    assert executed.status == "COMPLETED"
    assert len(executed.line_results) == 1
    [line_result] = executed.line_results
    assert line_result.outcome == "RESERVED"
    assert line_result.reservation_id is not None

    facts_after_execute = _inventory_business_facts(
        session,
        contributor.tenant_id,
    )
    replayed_execution = plan_service.execute(
        session,
        contributor,
        plan.id,
        command=execute_command,
        idempotency_key="task9-cross-domain-plan-execute",
    )
    assert replayed_execution == executed
    assert _inventory_business_facts(
        session,
        contributor.tenant_id,
    ) == facts_after_execute

    reservation = session.get(
        InventoryReservation,
        line_result.reservation_id,
    )
    assert reservation is not None
    assert reservation.owner_type == "ALLOCATION_PLAN"
    assert reservation.owner_id == str(plan.id)
    assert reservation.status == "ACTIVE"
    assert reservation.actor_user_id == contributor.user_id
    assert reservation.actor_roles_json == [contributor.role.value]
    assert reservation.request_id == contributor.request_id
    [reservation_line] = list(
        session.scalars(
            select(InventoryReservationLine).where(
                InventoryReservationLine.tenant_id
                == contributor.tenant_id,
                InventoryReservationLine.reservation_id
                == reservation.id,
            )
        ).all()
    )
    assert reservation_line.balance_id == balance.id
    assert reservation_line.reserved_quantity == Decimal("2.0000")

    reserve_transactions = list(
        session.scalars(
            select(InventoryTransaction)
            .where(
                InventoryTransaction.tenant_id
                == contributor.tenant_id,
                InventoryTransaction.operation_type == "RESERVE",
                InventoryTransaction.idempotency_key.like(
                    f"allocation-plan:{plan.id}:line:%"
                ),
            )
            .order_by(InventoryTransaction.id.asc())
        ).all()
    )
    assert len(reserve_transactions) == 1
    transaction = reserve_transactions[0]
    assert transaction.status == "COMPLETED"
    assert transaction.actor_user_id == contributor.user_id
    assert transaction.actor_roles_json == [contributor.role.value]
    assert transaction.request_id == contributor.request_id
    assert transaction.request_hash
    assert len(transaction.request_hash) == 64
    transaction_snapshot = transaction.response_snapshot_json
    assert isinstance(transaction_snapshot, dict)
    extensions = transaction_snapshot.get("_extensions")
    assert isinstance(extensions, dict)
    audit_context = extensions.get("audit_context")
    assert isinstance(audit_context, dict)
    assert audit_context["allocation_plan_id"] == plan.id
    assert audit_context["allocation_plan_line_id"] == line.id

    ledger_entries = list(
        session.scalars(
            select(InventoryLedgerEntry)
            .where(
                InventoryLedgerEntry.tenant_id
                == contributor.tenant_id,
                InventoryLedgerEntry.transaction_id
                == transaction.id,
            )
            .order_by(InventoryLedgerEntry.id.asc())
        ).all()
    )
    assert len(ledger_entries) == 1
    [ledger] = ledger_entries
    assert ledger.balance_id == balance.id
    assert ledger.on_hand_delta == ZERO4
    assert ledger.reserved_delta == Decimal("2.0000")
    assert ledger.resulting_balance_version > (
        ledger.before_balance_version
    )

    session.expire_all()
    balance_after = session.get(
        InventoryBalance,
        balance.id,
    )
    assert balance_after is not None
    assert balance_after.on_hand_quantity == Decimal("5.0000")
    assert balance_after.reserved_quantity == Decimal("2.0000")

    plan_events = list(
        session.scalars(
            select(AllocationPlanEvent)
            .where(
                AllocationPlanEvent.tenant_id
                == contributor.tenant_id,
                AllocationPlanEvent.plan_id == plan.id,
            )
            .order_by(AllocationPlanEvent.id.asc())
        ).all()
    )
    event_types = {
        event.event_type
        for event in plan_events
    }
    assert {
        "PLAN_CREATED",
        "PREVIEWED",
        "CONFIRMED",
        "EXECUTION_STARTED",
        "LINE_EXECUTED",
        "EXECUTION_COMPLETED",
    }.issubset(event_types)
    created_event = next(
        event
        for event in plan_events
        if event.event_type == "PLAN_CREATED"
    )
    confirmed_event = next(
        event
        for event in plan_events
        if event.event_type == "CONFIRMED"
    )
    completed_event = next(
        event
        for event in plan_events
        if event.event_type == "EXECUTION_COMPLETED"
    )
    assert created_event.idempotency_key == "task9-cross-domain-plan-create"
    assert confirmed_event.idempotency_key == "task9-cross-domain-plan-confirm"
    assert completed_event.idempotency_key == "task9-cross-domain-plan-execute"
    for event in (created_event, confirmed_event, completed_event):
        assert event.actor_user_id == contributor.user_id
        assert event.actor_roles_json == [contributor.role.value]
        assert event.request_id == contributor.request_id

    assert published_row.id == derived.id
    tenant_chain_entities = (
        source_after_publish,
        published_row,
        review,
        spare,
        warehouse,
        completed_simulation,
        candidate_after_simulation,
        published_rule,
        plan,
        line,
        reservation,
        reservation_line,
        transaction,
        ledger,
        balance_after,
        *review_events,
        *decisions,
        *demand_events,
        *plan_events,
    )
    assert {
        entity.tenant_id
        for entity in tenant_chain_entities
    } == {contributor.tenant_id}
    assert admin.tenant_id == contributor.tenant_id
    assert other_tenant_viewer.tenant_id != contributor.tenant_id

    assert _count_rows(session, AIReviewRun) == ai_runs_before
    assert _count_rows(session, AIReviewFinding) == ai_findings_before
