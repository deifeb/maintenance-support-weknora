from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.models import (
    AIReportJob,
    AIReviewFinding,
    AIReviewRun,
    DemandCalculation,
    DemandCalculationRun,
    DemandRunItemResult,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    EquipmentModel,
    SparePart,
    Warehouse,
    WarehouseInventory,
)
from app.models.enums import (
    AIBlockingLevel,
    AIReportJobStatus,
    AIReportType,
    AIReviewFindingStatus,
    AIReviewRunStatus,
    AISeverity,
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    ScenarioVersionStatus,
    ShortageRiskLevel,
)
from app.security.actor import ActorContext
from app.services.dashboard_service import DashboardService
from sqlalchemy import event
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TenantDashboardData:
    equipment_count: int
    spare_part_count: int
    running_calculations: int
    review_run_id: int
    report_job_id: int


def add_calculation(
    session: Session,
    tenant_id: str,
    code: str,
    *,
    status: CalculationStatus,
) -> DemandCalculation:
    now = datetime.now(timezone.utc)
    row = DemandCalculation(
        tenant_id=tenant_id,
        calculation_code=f"CALC-{code}",
        calculation_name=f"Calculation {code}",
        execution_type=CalculationExecutionType.ASYNCHRONOUS,
        requested_mode=DemandExecutionMode.AUTO,
        status=status,
        progress_percent=Decimal("45"),
        input_snapshot_json={},
        input_snapshot_hash=(code.lower() * 64)[:64],
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(row)
    session.flush()
    return row


def add_result(
    session: Session,
    tenant_id: str,
    calculation: DemandCalculation,
    spare: SparePart,
    *,
    risk: ShortageRiskLevel,
) -> DemandRunItemResult:
    run = DemandCalculationRun(
        tenant_id=tenant_id,
        calculation_id=calculation.id,
        run_mode=DemandExecutionMode.AUTO,
        status=CalculationStatus.SUCCEEDED,
        is_current_attempt=True,
        engine_version="dashboard-test",
        formula_version="dashboard-test",
    )
    session.add(run)
    session.flush()

    zero = Decimal("0")
    result = DemandRunItemResult(
        tenant_id=tenant_id,
        calculation_run_id=run.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        criticality_level="HIGH",
        calculation_status=ItemCalculationStatus.CALCULATED,
        failure_process_mode=FailureProcessMode.AUTO,
        target_service_level=Decimal("0.95"),
        expected_demand=Decimal("10"),
        variance=Decimal("1"),
        standard_deviation=Decimal("1"),
        p50=Decimal("8"),
        p80=Decimal("10"),
        p90=Decimal("11"),
        p95=Decimal("12"),
        p99=Decimal("13"),
        target_quantile_demand=Decimal("12"),
        gross_replacement_demand=Decimal("12"),
        repair_pipeline_demand=zero,
        repair_pipeline_peak=zero,
        net_consumption_demand=Decimal("12"),
        recommended_spare_quantity=Decimal("12"),
        on_hand_quantity=Decimal("2"),
        available_quantity=Decimal("2"),
        in_transit_quantity=zero,
        safety_stock_reserved=zero,
        usable_inventory=Decimal("2"),
        net_demand_gap=Decimal("10"),
        inventory_coverage_rate=Decimal("0.1667"),
        shortage_risk_level=risk,
        minimum_inventory_point=zero,
        maximum_simultaneous_gap=Decimal("10"),
        common_shock_demand=zero,
    )
    session.add(result)
    session.flush()
    return result


def seed_tenant_dashboard(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> TenantDashboardData:
    equipment = EquipmentModel(
        tenant_id=tenant_id,
        code=f"EQ-{suffix}",
        name=f"Equipment {suffix}",
        is_active=True,
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
        unit="piece",
        is_active=True,
    )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
        is_active=True,
    )
    session.add_all((equipment, spare, warehouse))
    session.flush()

    session.add(
        WarehouseInventory(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            spare_part_id=spare.id,
            on_hand_quantity=Decimal("3"),
            reserved_quantity=Decimal("0"),
            damaged_quantity=Decimal("0"),
            quarantined_quantity=Decimal("0"),
            in_transit_quantity=Decimal("0"),
            safety_stock=Decimal("2"),
            reorder_point=Decimal("5"),
        )
    )

    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SCN-{suffix}",
        name=f"Scenario {suffix}",
        is_active=True,
    )
    session.add(template)
    session.flush()
    session.add(
        DemandScenarioVersion(
            tenant_id=tenant_id,
            scenario_template_id=template.id,
            version_code="V1",
            version_name=f"Scenario version {suffix}",
            status=ScenarioVersionStatus.DRAFT,
        )
    )

    calculation = add_calculation(
        session,
        tenant_id,
        suffix,
        status=CalculationStatus.RUNNING,
    )
    add_result(
        session,
        tenant_id,
        calculation,
        spare,
        risk=ShortageRiskLevel.CRITICAL,
    )

    review = AIReviewRun(
        tenant_id=tenant_id,
        status=AIReviewRunStatus.COMPLETED,
        rule_set_version="dashboard-test",
        input_snapshot_json={},
    )
    session.add(review)
    session.flush()
    session.add(
        AIReviewFinding(
            tenant_id=tenant_id,
            review_run_id=review.id,
            rule_code=f"R-{suffix}",
            rule_version="1",
            category="INVENTORY",
            severity=AISeverity.CRITICAL,
            status=AIReviewFindingStatus.OPEN,
            blocking_level=(
                AIBlockingLevel.BLOCK_FORMAL_CALCULATION
            ),
            finding_title=f"Critical finding {suffix}",
            deterministic_message=(
                f"Tenant {tenant_id} requires attention"
            ),
        )
    )

    report = AIReportJob(
        tenant_id=tenant_id,
        report_code=f"REPORT-{suffix}",
        report_type=AIReportType.DEMAND_CALCULATION,
        status=AIReportJobStatus.READY_FOR_REVIEW,
        title=f"Report {suffix}",
        progress_percent=100,
    )
    session.add(report)
    session.commit()

    return TenantDashboardData(
        equipment_count=1,
        spare_part_count=1,
        running_calculations=1,
        review_run_id=review.id,
        report_job_id=report.id,
    )


def test_dashboard_counts_only_actor_tenant(
    session: Session,
    actor_viewer: ActorContext,
) -> None:
    tenant_one_data = seed_tenant_dashboard(
        session,
        "tenant-a",
        "A",
    )
    seed_tenant_dashboard(
        session,
        "tenant-b",
        "B",
    )
    session.add_all(
        (
            EquipmentModel(
                tenant_id="tenant-a",
                code="EQ-INACTIVE",
                name="Inactive equipment",
                is_active=False,
            ),
            SparePart(
                tenant_id="tenant-a",
                code="SP-INACTIVE",
                name="Inactive spare",
                unit="piece",
                is_active=False,
            ),
        )
    )
    session.commit()

    summary = DashboardService().summary(
        session,
        actor_viewer,
    )

    assert (
        summary.active_equipment_count
        == tenant_one_data.equipment_count
    )
    assert (
        summary.active_spare_part_count
        == tenant_one_data.spare_part_count
    )
    assert (
        summary.running_calculation_count
        == tenant_one_data.running_calculations
    )
    assert summary.metric_value("inventory_risk_count") == 1
    assert summary.metric_value("high_risk_finding_count") == 1
    assert summary.metric_value("demand_gap_count") == 1


def test_dashboard_returns_bounded_cross_domain_content(
    session: Session,
    actor_viewer: ActorContext,
) -> None:
    tenant_data = seed_tenant_dashboard(
        session,
        "tenant-a",
        "A",
    )
    foreign_data = seed_tenant_dashboard(
        session,
        "tenant-b",
        "B",
    )

    summary = DashboardService().summary(
        session,
        actor_viewer,
    )

    assert {
        task.task_type
        for task in summary.recent_tasks
    } == {
        "SCENARIO",
        "CALCULATION",
        "REVIEW",
        "REPORT",
    }
    assert len(summary.recent_tasks) <= 10
    assert len(summary.risk_items) <= 10
    assert summary.risk_distribution["BLOCKING"] == 1
    assert all(
        str(foreign_data.review_run_id)
        not in item.route
        for item in summary.risk_items
    )
    assert any(
        item.route.endswith(
            str(tenant_data.review_run_id)
        )
        for item in summary.risk_items
        if item.risk_type == "REVIEW_FINDING"
    )
    assert all(
        str(foreign_data.report_job_id)
        not in task.route
        for task in summary.recent_tasks
    )


def test_dashboard_uses_at_most_twelve_sql_statements(
    session: Session,
    actor_viewer: ActorContext,
) -> None:
    data = seed_tenant_dashboard(
        session,
        "tenant-a",
        "A",
    )

    for index in range(15):
        session.add(
            AIReportJob(
                tenant_id="tenant-a",
                report_code=f"EXTRA-REPORT-{index}",
                report_type=AIReportType.INVENTORY_GAP,
                status=AIReportJobStatus.CREATED,
                title=f"Extra report {index}",
                progress_percent=0,
            )
        )
        session.add(
            AIReviewFinding(
                tenant_id="tenant-a",
                review_run_id=data.review_run_id,
                rule_code=f"X{index:02d}",
                rule_version="1",
                category="INVENTORY",
                severity=AISeverity.WARNING,
                status=AIReviewFindingStatus.OPEN,
                blocking_level=AIBlockingLevel.NONE,
                finding_title=f"Extra finding {index}",
                deterministic_message="Review required",
            )
        )
    session.commit()

    statements: list[str] = []
    bind = session.get_bind()

    def record_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement)

    event.listen(
        bind,
        "before_cursor_execute",
        record_statement,
    )
    try:
        summary = DashboardService().summary(
            session,
            actor_viewer,
        )
    finally:
        event.remove(
            bind,
            "before_cursor_execute",
            record_statement,
        )

    assert len(statements) <= 12
    assert len(summary.recent_tasks) == 10
    assert len(summary.risk_items) == 10
