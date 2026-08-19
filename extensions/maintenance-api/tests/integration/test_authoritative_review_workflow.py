from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from app.models import (
    AIReviewFinding,
    AIReviewRun,
    CalculationGroup,
    DemandList,
    DemandListItem,
    DemandReviewDecision,
    DemandReviewEvent,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from app.security.actor import ActorContext, MaintenanceRole
from app.services.demand_review_service import DemandReviewService
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _create_published_source(
    session: Session,
    actor: ActorContext,
) -> tuple[DemandList, list[DemandListItem]]:
    template = DemandScenarioTemplate(
        tenant_id=actor.tenant_id,
        code="SC-TASK8-INTEGRATION",
        name="Task 8 authoritative review integration scenario",
    )
    session.add(template)
    session.flush()

    scenario_version = DemandScenarioVersion(
        tenant_id=actor.tenant_id,
        scenario_template_id=template.id,
        version_code="TASK8-V1",
        version_name="Task 8 integration version",
    )
    session.add(scenario_version)
    session.flush()

    group = CalculationGroup(
        tenant_id=actor.tenant_id,
        scenario_version_id=scenario_version.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id=actor.user_id,
        created_by_request_id=actor.request_id,
    )
    session.add(group)
    session.flush()

    repository = DemandListRepository()
    source = repository.create_version(
        session,
        actor.tenant_id,
        {
            "name": "Task 8 current published demand list",
            "description": "Authoritative review integration source",
            "scenario_version_id": scenario_version.id,
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

    items: list[DemandListItem] = []
    for index, quantity in enumerate(
        ("10.000000", "20.000000"),
        start=1,
    ):
        spare = SparePart(
            tenant_id=actor.tenant_id,
            code=f"SP-TASK8-{index}",
            name=f"Task 8 spare {index}",
            unit="EA",
        )
        session.add(spare)
        session.flush()

        child_id = 1000 + index

        item = repository.add_item(
            session,
            actor.tenant_id,
            demand_list_id=source.id,
            spare_part_id=spare.id,
            original_quantity=Decimal(quantity),
            final_quantity=Decimal(quantity),
            source_snapshot={
                "recommended_spare_quantity": quantity,
                "task8_source": index,
            },
            spare_part_code_snapshot=spare.code,
            spare_part_name_snapshot=spare.name,
            spare_part_unit_snapshot=spare.unit,
        )
        item.criticality_level_snapshot = (
            "LOW" if index == 1 else "HIGH"
        )
        item.decision_snapshot_json = {
            "source_child_id": child_id,
        }
        item.interval_snapshot_json = {
            "system_source_child_id": child_id,
            "selected_child_id": child_id,
            "candidates": [
                {
                    "child_id": child_id,
                    "candidate_key": f"task8-candidate-{index}",
                    "reliability_model": "WEIBULL",
                    "execution_mode": "ANALYTICAL",
                    "recommended_quantity": quantity,
                    "p50": quantity,
                    "p80": quantity,
                    "p90": quantity,
                    "p95": quantity,
                    "p99": quantity,
                    "warnings": [],
                }
            ],
        }
        item.warning_snapshot_json = []
        item.inventory_snapshot_json = {
            "task8_seeded_inventory": "0.000000",
        }
        session.flush()
        items.append(item)

    return source, items


def _source_snapshot(
    session: Session,
    source_id: int,
) -> dict[str, Any]:
    source = session.get(DemandList, source_id)
    assert source is not None

    items = list(
        session.scalars(
            select(DemandListItem)
            .where(DemandListItem.demand_list_id == source_id)
            .order_by(DemandListItem.id)
        ).all()
    )
    return {
        "id": source.id,
        "status": source.status.value,
        "is_current": source.is_current,
        "version": source.version,
        "version_number": source.version_number,
        "superseded_by_id": source.superseded_by_id,
        "superseded_at": source.superseded_at,
        "items": [
            {
                "id": item.id,
                "final_quantity": str(item.final_quantity),
                "decision_type": (
                    item.decision_type.value
                    if item.decision_type is not None
                    else None
                ),
                "decision_reason": item.decision_reason,
                "decision_snapshot": deepcopy(
                    item.decision_snapshot_json
                ),
                "interval_snapshot": deepcopy(
                    item.interval_snapshot_json
                ),
                "parameter_snapshot": deepcopy(
                    item.parameter_snapshot_json
                ),
                "warning_snapshot": deepcopy(
                    item.warning_snapshot_json
                ),
                "inventory_snapshot": deepcopy(
                    item.inventory_snapshot_json
                ),
                "version": item.version,
            }
            for item in items
        ],
    }


def _count_rows(session: Session, model: Any) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(model)
        )
        or 0
    )


def _finding_by_id(review: Any, finding_id: int) -> Any:
    return next(
        finding
        for finding in review.findings
        if finding.id == finding_id
    )


def test_authoritative_review_workflow_end_to_end(
    session: Session,
    actor_context,
) -> None:
    contributor = actor_context(
        tenant_id="tenant-task8",
        user_id="task8-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="task8-contributor-request",
        token_id="task8-contributor-token",
    )
    admin = actor_context(
        tenant_id="tenant-task8",
        user_id="task8-admin",
        role=MaintenanceRole.ADMIN,
        request_id="task8-admin-request",
        token_id="task8-admin-token",
    )

    source, source_items = _create_published_source(
        session,
        contributor,
    )
    source_id = source.id
    source_version = source.version
    source_before = _source_snapshot(session, source_id)
    source_item_by_id = {
        item.id: item.spare_part_id
        for item in source_items
    }
    source_quantity_by_id = {
        item.id: item.final_quantity
        for item in source_items
    }

    ai_runs_before = _count_rows(session, AIReviewRun)
    ai_findings_before = _count_rows(session, AIReviewFinding)

    service = DemandReviewService()
    run_key = "task8-authoritative-run"
    review = service.run(
        session,
        contributor,
        source_id,
        expected_source_version=source_version,
        idempotency_key=run_key,
    )

    assert review.status is DemandReviewStatus.OPEN
    assert review.source_demand_list_id == source_id
    assert review.source_demand_list_version == source_version
    assert review.source_snapshot["source_demand_list"]["status"] == "PUBLISHED"
    assert review.source_snapshot["source_demand_list"]["is_current"] is True
    assert not review.source_snapshot["current_inventory"]

    inventory_gaps = sorted(
        (
            finding
            for finding in review.findings
            if finding.rule_code == "INVENTORY_GAP"
        ),
        key=lambda finding: (
            finding.source_demand_list_item_id or 0,
            finding.id,
        ),
    )
    assert len(inventory_gaps) == 2
    assert all(finding.blocking for finding in inventory_gaps)
    assert all(
        finding.severity is DemandReviewSeverity.HIGH
        for finding in inventory_gaps
    )
    assert all(
        finding.decision_status
        is DemandReviewDecisionStatus.PENDING
        for finding in inventory_gaps
    )

    ordinary_gap = inventory_gaps[0]
    edited_gap = inventory_gaps[1]
    assert ordinary_gap.requires_admin_acceptance is False
    assert edited_gap.source_demand_list_item_id is not None
    assert edited_gap.effect_key == (
        f"FINAL_QUANTITY:{edited_gap.source_demand_list_item_id}"
    )

    contributor_key = "task8-contributor-reject"
    state = service.decide_finding(
        session,
        contributor,
        review.id,
        ordinary_gap.id,
        expected_review_version=review.version,
        expected_finding_version=ordinary_gap.version,
        action=DemandReviewDecisionStatus.REJECTED,
        final_quantity=None,
        reason="Task 8 contributor rejects ordinary inventory gap",
        idempotency_key=contributor_key,
    )

    edited_current = _finding_by_id(state, edited_gap.id)
    edited_quantity = Decimal("7.500000")
    admin_edit_key = "task8-admin-edit-accept"
    state = service.decide_finding(
        session,
        admin,
        state.id,
        edited_current.id,
        expected_review_version=state.version,
        expected_finding_version=edited_current.version,
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity=edited_quantity,
        reason="Task 8 admin edits high-severity inventory quantity",
        idempotency_key=admin_edit_key,
    )

    admin_only = next(
        (
            finding
            for finding in state.findings
            if finding.blocking
            and finding.requires_admin_acceptance
            and finding.decision_status
            is DemandReviewDecisionStatus.PENDING
        ),
        None,
    )
    assert admin_only is not None

    admin_accept_key = "task8-admin-accept-governed"
    state = service.decide_finding(
        session,
        admin,
        state.id,
        admin_only.id,
        expected_review_version=state.version,
        expected_finding_version=admin_only.version,
        action=DemandReviewDecisionStatus.ACCEPTED,
        final_quantity=None,
        reason="Task 8 admin accepts governed evidence finding",
        idempotency_key=admin_accept_key,
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
        key = f"task8-admin-resolve-{pending.id}"
        resolver_keys.append(key)
        state = service.decide_finding(
            session,
            admin,
            state.id,
            pending.id,
            expected_review_version=state.version,
            expected_finding_version=pending.version,
            action=DemandReviewDecisionStatus.REJECTED,
            final_quantity=None,
            reason="Task 8 resolves remaining blocking finding",
            idempotency_key=key,
        )

    assert state.status is DemandReviewStatus.READY_TO_DERIVE
    assert state.pending_blocking_finding_count == 0

    derive_key = "task8-authoritative-derive"
    derived_result = service.derive(
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
    assert derived.lineage_id == source.lineage_id
    assert derived.version_number == source.version_number + 1
    assert len(derived.items) == len(source_items)

    derived_by_part = {
        item.spare_part_id: item
        for item in derived.items
    }

    ordinary_source_id = ordinary_gap.source_demand_list_item_id
    edited_source_id = edited_gap.source_demand_list_item_id
    assert ordinary_source_id is not None
    assert edited_source_id is not None

    ordinary_part_id = source_item_by_id[ordinary_source_id]
    edited_part_id = source_item_by_id[edited_source_id]

    assert derived_by_part[ordinary_part_id].final_quantity == (
        source_quantity_by_id[ordinary_source_id]
    )
    assert derived_by_part[edited_part_id].final_quantity == edited_quantity

    session.expire_all()
    assert _source_snapshot(session, source_id) == source_before

    review_events = list(
        session.scalars(
            select(DemandReviewEvent)
            .where(DemandReviewEvent.review_id == state.id)
            .order_by(DemandReviewEvent.id)
        ).all()
    )
    command_events = [
        event
        for event in review_events
        if event.command_type is not None
    ]
    expected_command_keys = {
        run_key,
        contributor_key,
        admin_edit_key,
        admin_accept_key,
        derive_key,
        *resolver_keys,
    }
    assert {
        event.idempotency_key
        for event in command_events
    } == expected_command_keys
    assert all(
        event.request_hash
        and len(event.request_hash) == 64
        for event in command_events
    )

    run_event = next(
        event
        for event in command_events
        if event.command_type is DemandReviewCommandType.RUN
    )
    derive_event = next(
        event
        for event in command_events
        if event.command_type is DemandReviewCommandType.DERIVE
    )
    assert run_event.actor_user_id == contributor.user_id
    assert run_event.actor_roles_json == [contributor.role.value]
    assert run_event.request_id == contributor.request_id
    assert derive_event.actor_user_id == admin.user_id
    assert derive_event.actor_roles_json == [admin.role.value]
    assert derive_event.request_id == admin.request_id

    decisions = list(
        session.scalars(
            select(DemandReviewDecision)
            .where(DemandReviewDecision.review_id == state.id)
            .order_by(DemandReviewDecision.id)
        ).all()
    )
    assert decisions
    assert all(
        decision.request_hash
        and len(decision.request_hash) == 64
        for decision in decisions
    )

    contributor_decision = next(
        decision
        for decision in decisions
        if decision.finding_id == ordinary_gap.id
    )
    admin_edit_decision = next(
        decision
        for decision in decisions
        if decision.finding_id == edited_gap.id
    )
    assert contributor_decision.actor_user_id == contributor.user_id
    assert contributor_decision.actor_roles_json == [
        contributor.role.value
    ]
    assert contributor_decision.request_id == contributor.request_id
    assert (
        contributor_decision.action
        == DemandReviewDecisionStatus.REJECTED.value
    )
    assert admin_edit_decision.actor_user_id == admin.user_id
    assert admin_edit_decision.actor_roles_json == [admin.role.value]
    assert admin_edit_decision.request_id == admin.request_id
    assert (
        admin_edit_decision.action
        == DemandReviewDecisionStatus.EDIT_ACCEPTED.value
    )
    assert admin_edit_decision.final_quantity == edited_quantity

    assert _count_rows(session, AIReviewRun) == ai_runs_before
    assert _count_rows(session, AIReviewFinding) == ai_findings_before
