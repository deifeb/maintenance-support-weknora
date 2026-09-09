from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    AllocationPlan,
    AllocationRuleVersion,
    AllocationSimulation,
    CalculationGroup,
    DemandScenarioVersion,
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
)
from app.models.enums import (
    AIReportSourceType,
    DemandListStatus,
    DemandReviewDecisionStatus,
    DemandReviewStatus,
)
from app.repositories.ai_report_repository import ai_report_repository
from app.schemas.ai_report import ReportSourceRefInput
from app.schemas.allocation import (
    AllocationPlanConfirmCommand,
    AllocationPlanExecuteCommand,
    AllocationPlanPreviewCommand,
    AllocationRuleDraftCommand,
    AllocationRulePublishCommand,
)
from app.schemas.report_center import ReportJobCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service
from app.services.allocation_plan_service import AllocationPlanService
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_simulation_service import AllocationSimulationService
from app.services.demand_list_service import DemandListService
from app.services.demand_review_service import DemandReviewService
from app.services.report_center_service import ReportCenterQueryService
from app.workers.allocation_simulation_executor import AllocationSimulationExecutor
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_plan05_04_cross_domain_invariants import (
    _plan_lines,
    _seed_allocation_inventory,
    _seed_published_review_source,
)


def test_full_plan05_workflow_preserves_authority_and_report_lineage(
    session: Session,
    actor_context,
    tmp_path,
    monkeypatch,
) -> None:
    contributor = actor_context(
        tenant_id="tenant-plan05-full-a",
        user_id="plan05-full-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="plan05-full-contributor-request",
        token_id="plan05-full-contributor-token",
    )
    admin = actor_context(
        tenant_id=contributor.tenant_id,
        user_id="plan05-full-admin",
        role=MaintenanceRole.ADMIN,
        request_id="plan05-full-admin-request",
        token_id="plan05-full-admin-token",
    )
    tenant_b = actor_context(
        tenant_id="tenant-plan05-full-b",
        user_id="plan05-full-foreign-viewer",
        role=MaintenanceRole.VIEWER,
        request_id="plan05-full-foreign-request",
        token_id="plan05-full-foreign-token",
    )

    source, source_item, spare = _seed_published_review_source(
        session,
        contributor,
    )
    scenario = session.get(
        DemandScenarioVersion,
        source.scenario_version_id,
    )
    calculation_group = session.get(
        CalculationGroup,
        source.calculation_group_id,
    )
    assert scenario is not None
    assert calculation_group is not None
    assert calculation_group.status.value == "COMPLETED"
    assert source.status is DemandListStatus.PUBLISHED

    review_service = DemandReviewService()
    review = review_service.run(
        session,
        contributor,
        source.id,
        expected_source_version=source.version,
        idempotency_key="plan05-full-review-run",
    )
    assert review.status is DemandReviewStatus.OPEN
    inventory_gap = next(
        finding
        for finding in review.findings
        if finding.rule_code == "INVENTORY_GAP"
        and finding.source_demand_list_item_id == source_item.id
    )
    state = review_service.decide_finding(
        session,
        admin,
        review.id,
        inventory_gap.id,
        expected_review_version=review.version,
        expected_finding_version=inventory_gap.version,
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity=Decimal("2.000000"),
        reason="Plan 05 full workflow authoritative quantity",
        idempotency_key="plan05-full-review-edit",
    )
    while state.pending_blocking_finding_count:
        pending = next(
            finding
            for finding in state.findings
            if finding.blocking
            and finding.decision_status is DemandReviewDecisionStatus.PENDING
        )
        state = review_service.decide_finding(
            session,
            admin,
            state.id,
            pending.id,
            expected_review_version=state.version,
            expected_finding_version=pending.version,
            action=DemandReviewDecisionStatus.REJECTED,
            final_quantity=None,
            reason="Plan 05 full workflow resolves remaining evidence",
            idempotency_key=f"plan05-full-review-resolve-{pending.id}",
        )

    assert state.status is DemandReviewStatus.READY_TO_DERIVE
    derived_result = review_service.derive(
        session,
        admin,
        state.id,
        expected_review_version=state.version,
        idempotency_key="plan05-full-review-derive",
    )
    derived = derived_result.derived_demand_list
    assert derived.status is DemandListStatus.DRAFT
    assert derived.derived_from_id == source.id
    assert derived.lineage_id == source.lineage_id
    assert derived.items[0].final_quantity == Decimal("2.000000")

    demand_service = DemandListService()
    submitted = demand_service.submit(
        session,
        contributor,
        derived.id,
        expected_version=derived.version,
        idempotency_key="plan05-full-demand-submit",
    )
    confirmed = demand_service.confirm(
        session,
        admin,
        derived.id,
        expected_version=submitted.version,
        confirmation_note="Plan 05 full workflow authoritative confirmation",
        idempotency_key="plan05-full-demand-confirm",
    )
    published = demand_service.publish(
        session,
        admin,
        derived.id,
        expected_version=confirmed.version,
        idempotency_key="plan05-full-demand-publish",
    )
    assert published.status is DemandListStatus.PUBLISHED

    with pytest.raises(ConflictError) as immutable_demand:
        demand_service.update_item(
            session,
            admin,
            published.id,
            published.items[0].id,
            expected_version=published.version,
            final_quantity=Decimal("1.000000"),
            adjustment_reason="Published demand must remain immutable",
        )
    assert immutable_demand.value.code == "PUBLISHED_DEMAND_LIST_IMMUTABLE"
    with pytest.raises(NotFoundError):
        demand_service.get(session, tenant_b, published.id)

    warehouse, balance = _seed_allocation_inventory(
        session,
        contributor,
        spare,
    )
    rule_service = AllocationRuleService()
    candidate = rule_service.create_draft(
        session,
        contributor,
        command=AllocationRuleDraftCommand(
            lineage_id="plan05-full-allocation-rule",
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
            weights={"criticality": Decimal("1.000000")},
            normalization={
                "criticality": {
                    "min": Decimal("0"),
                    "max": Decimal("4"),
                }
            },
            change_reason="Plan 05 full workflow allocation rule",
        ),
    )
    simulation_service = AllocationSimulationService()
    simulation = simulation_service.submit(
        session,
        contributor,
        candidate_rule_id=candidate.id,
        baseline_rule_id=None,
        source_demand_list_id=published.id,
        sample_ref="plan05-full-workflow",
        idempotency_key="plan05-full-simulation",
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
    completed_simulation = session.get(AllocationSimulation, simulation_id)
    simulated_candidate = session.get(AllocationRuleVersion, candidate_id)
    assert completed_simulation is not None
    assert simulated_candidate is not None
    assert completed_simulation.status == "COMPLETED"
    simulation_summary = simulation_service.latest_for_rule(
        session,
        contributor.tenant_id,
        candidate_id,
    )
    assert simulation_summary is not None
    assert not simulation_summary.blockers
    published_rule = rule_service.publish(
        session,
        admin,
        candidate_id,
        command=AllocationRulePublishCommand(
            expected_version=simulated_candidate.version,
        ),
        latest_simulation=simulation_summary,
        idempotency_key="plan05-full-rule-publish",
    )
    assert published_rule.status == "PUBLISHED"

    plan_service = AllocationPlanService()
    plan = plan_service.create(
        session,
        contributor,
        published.id,
        idempotency_key="plan05-full-plan-create",
        expected_source_version=published.version,
    )
    assert plan.rule_id == published_rule.id
    [plan_line] = _plan_lines(
        session,
        contributor.tenant_id,
        plan.id,
    )
    previewed = plan_service.preview(
        session,
        contributor,
        plan.id,
        command=AllocationPlanPreviewCommand(expected_version=plan.version),
    )
    confirmed_plan = plan_service.confirm(
        session,
        contributor,
        plan.id,
        command=AllocationPlanConfirmCommand(
            expected_version=previewed.version,
        ),
        idempotency_key="plan05-full-plan-confirm",
    )
    executed = plan_service.execute(
        session,
        contributor,
        plan.id,
        command=AllocationPlanExecuteCommand(
            expected_version=confirmed_plan.version,
        ),
        idempotency_key="plan05-full-plan-execute",
    )
    assert executed.status == "COMPLETED"
    [line_result] = executed.line_results
    assert line_result.outcome == "RESERVED"
    assert line_result.reservation_id is not None

    session.expire_all()
    persisted_plan = session.get(AllocationPlan, plan.id)
    persisted_balance = session.get(InventoryBalance, balance.id)
    reservation = session.get(
        InventoryReservation,
        line_result.reservation_id,
    )
    assert persisted_plan is not None
    assert persisted_balance is not None
    assert reservation is not None
    [reservation_line] = list(
        session.scalars(
            select(InventoryReservationLine).where(
                InventoryReservationLine.tenant_id == contributor.tenant_id,
                InventoryReservationLine.reservation_id == reservation.id,
            )
        ).all()
    )
    [transaction] = list(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.tenant_id == contributor.tenant_id,
                InventoryTransaction.operation_type == "RESERVE",
                InventoryTransaction.idempotency_key.like(
                    f"allocation-plan:{plan.id}:line:%"
                ),
            )
        ).all()
    )
    [ledger] = list(
        session.scalars(
            select(InventoryLedgerEntry).where(
                InventoryLedgerEntry.tenant_id == contributor.tenant_id,
                InventoryLedgerEntry.transaction_id == transaction.id,
            )
        ).all()
    )
    assert reservation.owner_type == "ALLOCATION_PLAN"
    assert reservation.owner_id == str(plan.id)
    assert reservation.status == "ACTIVE"
    assert reservation_line.balance_id == balance.id
    assert reservation_line.reserved_quantity == Decimal("2.0000")
    assert ledger.balance_id == balance.id
    assert ledger.on_hand_delta == Decimal("0.0000")
    assert ledger.reserved_delta == Decimal("2.0000")
    assert persisted_balance.on_hand_quantity == Decimal("5.0000")
    assert persisted_balance.reserved_quantity == Decimal("2.0000")
    assert ledger.resulting_balance_version == persisted_balance.version
    assert plan_line.reservation_id == reservation.id

    report_center = ReportCenterQueryService()
    allocation_plan_version = persisted_plan.version
    created_report = report_center.create_job(
        session,
        contributor,
        ReportJobCreateRequest(
            title="Plan 05 allocation plan assurance report",
            report_type="ALLOCATION_PLAN",
            source_refs=[
                ReportSourceRefInput(
                    type=AIReportSourceType.ALLOCATION_PLAN,
                    id=persisted_plan.id,
                    version=str(allocation_plan_version),
                )
            ],
        ),
    )
    report_version = ai_report_service.latest_version(
        session,
        contributor,
        created_report.report_id,
    )
    [source_ref] = ai_report_repository.list_source_refs(
        session,
        contributor.tenant_id,
        report_version.id,
    )
    assert source_ref.source_type is AIReportSourceType.ALLOCATION_PLAN
    assert source_ref.source_id == str(persisted_plan.id)
    assert source_ref.source_version == str(allocation_plan_version)
    source_snapshot = deepcopy(report_version.source_snapshot_json)
    assert source_snapshot is not None
    assert source_snapshot["sources"][0]["version"] == str(
        allocation_plan_version
    )

    with pytest.raises(NotFoundError):
        report_center.detail(session, tenant_b, created_report.report_id)

    persisted_plan.inventory_fingerprint = "f" * 64
    persisted_plan.version += 1
    session.commit()
    generated = report_center.generate(
        session,
        contributor,
        created_report.report_id,
    )
    assert generated.job_status.value == "VALIDATING_NUMBERS"
    assert generated.latest_version.status.value == "DRAFT"
    generated_version = ai_report_service.latest_version(
        session,
        contributor,
        created_report.report_id,
    )
    assert generated_version.source_snapshot_json == source_snapshot
    assert generated_version.source_snapshot_json["sources"][0][
        "evidence"
    ]["inventory_fingerprint"] != persisted_plan.inventory_fingerprint

    ready = report_center.validate(
        session,
        contributor,
        created_report.report_id,
    )
    assert ready.job_status.value == "READY_FOR_REVIEW"
    assert ready.latest_version.status.value == "REVIEWED"
    finalized = report_center.finalize(
        session,
        admin,
        created_report.report_id,
    )
    assert finalized.job_status.value == "FINALIZED"
    assert finalized.latest_version.status.value == "FINAL"

    output_dir = tmp_path / "plan05-full-report"
    monkeypatch.setattr(
        "app.services.ai_report_service.get_settings",
        lambda: SimpleNamespace(ai_report_export_dir=str(output_dir)),
    )
    content, content_type, file_name = report_center.export(
        session,
        contributor,
        created_report.report_id,
        "DOCX",
    )
    assert content
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert file_name.endswith(".docx")
    assert (output_dir / file_name).stat().st_size == len(content)

    for operation in (report_center.generate, report_center.regenerate):
        with pytest.raises(BusinessValidationError) as immutable_report:
            operation(
                session,
                contributor,
                created_report.report_id,
            )
        assert immutable_report.value.code == "REPORT_FINAL_VERSION_IMMUTABLE"
