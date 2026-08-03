from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AIReportJob,
    AIReviewFinding,
    AIReviewRun,
    DemandCalculation,
    DemandCalculationRun,
    DemandRunItemResult,
    DemandScenarioVersion,
    EquipmentModel,
    SparePart,
    Warehouse,
)
from app.models.enums import (
    AIReviewFindingStatus,
    AISeverity,
    CalculationStatus,
    ScenarioVersionStatus,
    ShortageRiskLevel,
)
from app.schemas.dashboard import (
    DashboardMetric,
    DashboardSummary,
    RecentTask,
    RiskItem,
)
from app.security.actor import ActorContext
from app.services.inventory_query_service import InventoryQueryService


class DashboardService:
    _TASK_LIMIT = 10
    _RISK_LIMIT = 10
    _RISK_RANK = {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "BLOCKING": 4,
    }

    def __init__(
        self,
        inventory_query_service: InventoryQueryService | None = None,
    ) -> None:
        self.inventory_query_service = (
            inventory_query_service or InventoryQueryService()
        )

    def summary(
        self,
        session: Session,
        actor: ActorContext,
    ) -> DashboardSummary:
        return DashboardSummary(
            metrics=self._metrics(session, actor),
            recent_tasks=self._recent_tasks(session, actor.tenant_id),
            risk_items=self._risk_items(session, actor.tenant_id),
            risk_distribution=self._risk_distribution(
                session,
                actor.tenant_id,
            ),
            generated_at=datetime.now(timezone.utc),
        )

    def _metrics(
        self,
        session: Session,
        actor: ActorContext,
    ) -> list[DashboardMetric]:
        tenant_id = actor.tenant_id
        summaries = self.inventory_query_service.summaries_for_parts(
            session,
            actor,
        )
        active_warehouse_ids = set(
            session.scalars(
                select(Warehouse.id).where(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.is_active.is_(True),
                )
            )
        )
        active_spare_part_ids = set(
            session.scalars(
                select(SparePart.id).where(
                    SparePart.tenant_id == tenant_id,
                    SparePart.is_active.is_(True),
                )
            )
        )
        inventory_risk_count = len(
            {
                summary.spare_part_id
                for summary in summaries
                if summary.warehouse_id in active_warehouse_ids
                and summary.spare_part_id in active_spare_part_ids
                and summary.available_quantity < summary.reorder_point
            }
        )

        active_equipment = (
            select(func.count(EquipmentModel.id))
            .where(
                EquipmentModel.tenant_id == tenant_id,
                EquipmentModel.is_active.is_(True),
            )
            .scalar_subquery()
        )
        active_spare_parts = (
            select(func.count(SparePart.id))
            .where(
                SparePart.tenant_id == tenant_id,
                SparePart.is_active.is_(True),
            )
            .scalar_subquery()
        )
        pending_scenarios = (
            select(func.count(DemandScenarioVersion.id))
            .where(
                DemandScenarioVersion.tenant_id == tenant_id,
                DemandScenarioVersion.status
                == ScenarioVersionStatus.DRAFT,
            )
            .scalar_subquery()
        )
        running_calculations = (
            select(func.count(DemandCalculation.id))
            .where(
                DemandCalculation.tenant_id == tenant_id,
                DemandCalculation.status == CalculationStatus.RUNNING,
            )
            .scalar_subquery()
        )
        failed_calculations = (
            select(func.count(DemandCalculation.id))
            .where(
                DemandCalculation.tenant_id == tenant_id,
                DemandCalculation.status == CalculationStatus.FAILED,
            )
            .scalar_subquery()
        )
        high_risk_findings = (
            select(func.count(AIReviewFinding.id))
            .where(
                AIReviewFinding.tenant_id == tenant_id,
                AIReviewFinding.status.in_(
                    (
                        AIReviewFindingStatus.OPEN,
                        AIReviewFindingStatus.ACKNOWLEDGED,
                    )
                ),
                AIReviewFinding.severity.in_(
                    (
                        AISeverity.ERROR,
                        AISeverity.CRITICAL,
                    )
                ),
            )
            .scalar_subquery()
        )
        demand_gaps = (
            select(
                func.count(
                    func.distinct(DemandRunItemResult.spare_part_id)
                )
            )
            .select_from(DemandRunItemResult)
            .join(
                DemandCalculationRun,
                DemandCalculationRun.id
                == DemandRunItemResult.calculation_run_id,
            )
            .where(
                DemandRunItemResult.tenant_id == tenant_id,
                DemandCalculationRun.tenant_id == tenant_id,
                DemandCalculationRun.is_current_attempt.is_(True),
                DemandRunItemResult.net_demand_gap > 0,
            )
            .scalar_subquery()
        )

        row = session.execute(
            select(
                active_equipment.label("active_equipment_count"),
                active_spare_parts.label("active_spare_part_count"),
                pending_scenarios.label("pending_scenario_count"),
                running_calculations.label(
                    "running_calculation_count"
                ),
                failed_calculations.label(
                    "failed_calculation_count"
                ),
                high_risk_findings.label(
                    "high_risk_finding_count"
                ),
                demand_gaps.label("demand_gap_count"),
            )
        ).one()

        values = {
            "active_equipment_count": row.active_equipment_count,
            "active_spare_part_count": row.active_spare_part_count,
            "inventory_risk_count": inventory_risk_count,
            "pending_scenario_count": row.pending_scenario_count,
            "running_calculation_count": row.running_calculation_count,
            "failed_calculation_count": row.failed_calculation_count,
            "high_risk_finding_count": row.high_risk_finding_count,
            "demand_gap_count": row.demand_gap_count,
        }
        return [
            DashboardMetric(
                key=key,
                value=int(value or 0),
            )
            for key, value in values.items()
        ]

    def _recent_tasks(
        self,
        session: Session,
        tenant_id: str,
    ) -> list[RecentTask]:
        tasks: list[RecentTask] = []

        scenario_rows = session.execute(
            select(
                DemandScenarioVersion.id,
                DemandScenarioVersion.version_name,
                DemandScenarioVersion.status,
                DemandScenarioVersion.updated_at,
            )
            .where(DemandScenarioVersion.tenant_id == tenant_id)
            .order_by(
                DemandScenarioVersion.updated_at.desc(),
                DemandScenarioVersion.id.desc(),
            )
            .limit(self._TASK_LIMIT)
        ).all()
        tasks.extend(
            RecentTask(
                task_type="SCENARIO",
                task_id=row.id,
                title=row.version_name,
                status=self._enum_value(row.status),
                updated_at=row.updated_at,
                route=(
                    "/platform/maintenance/scenarios/"
                    f"{row.id}"
                ),
            )
            for row in scenario_rows
        )

        calculation_rows = session.execute(
            select(
                DemandCalculation.id,
                DemandCalculation.calculation_name,
                DemandCalculation.status,
                DemandCalculation.progress_percent,
                DemandCalculation.updated_at,
            )
            .where(DemandCalculation.tenant_id == tenant_id)
            .order_by(
                DemandCalculation.updated_at.desc(),
                DemandCalculation.id.desc(),
            )
            .limit(self._TASK_LIMIT)
        ).all()
        tasks.extend(
            RecentTask(
                task_type="CALCULATION",
                task_id=row.id,
                title=row.calculation_name,
                status=self._enum_value(row.status),
                progress=row.progress_percent,
                updated_at=row.updated_at,
                route=(
                    "/platform/maintenance/calculations/"
                    f"{row.id}"
                ),
            )
            for row in calculation_rows
        )

        review_rows = session.execute(
            select(
                AIReviewRun.id,
                AIReviewRun.status,
                AIReviewRun.updated_at,
            )
            .where(AIReviewRun.tenant_id == tenant_id)
            .order_by(
                AIReviewRun.updated_at.desc(),
                AIReviewRun.id.desc(),
            )
            .limit(self._TASK_LIMIT)
        ).all()
        tasks.extend(
            RecentTask(
                task_type="REVIEW",
                task_id=row.id,
                title=f"Review #{row.id}",
                status=self._enum_value(row.status),
                updated_at=row.updated_at,
                route=(
                    "/platform/maintenance/reviews/"
                    f"{row.id}"
                ),
            )
            for row in review_rows
        )

        report_rows = session.execute(
            select(
                AIReportJob.id,
                AIReportJob.title,
                AIReportJob.status,
                AIReportJob.progress_percent,
                AIReportJob.updated_at,
            )
            .where(AIReportJob.tenant_id == tenant_id)
            .order_by(
                AIReportJob.updated_at.desc(),
                AIReportJob.id.desc(),
            )
            .limit(self._TASK_LIMIT)
        ).all()
        tasks.extend(
            RecentTask(
                task_type="REPORT",
                task_id=row.id,
                title=row.title,
                status=self._enum_value(row.status),
                progress=row.progress_percent,
                updated_at=row.updated_at,
                route=(
                    "/platform/maintenance/reports/"
                    f"{row.id}"
                ),
            )
            for row in report_rows
        )

        return sorted(
            tasks,
            key=lambda item: (
                self._timestamp(item.updated_at),
                item.task_id,
            ),
            reverse=True,
        )[: self._TASK_LIMIT]

    def _risk_distribution(
        self,
        session: Session,
        tenant_id: str,
    ) -> dict[str, int]:
        distribution = {
            "LOW": 0,
            "MEDIUM": 0,
            "HIGH": 0,
            "BLOCKING": 0,
        }
        rows = session.execute(
            select(
                DemandRunItemResult.shortage_risk_level,
                func.count(DemandRunItemResult.id),
            )
            .join(
                DemandCalculationRun,
                DemandCalculationRun.id
                == DemandRunItemResult.calculation_run_id,
            )
            .where(
                DemandRunItemResult.tenant_id == tenant_id,
                DemandCalculationRun.tenant_id == tenant_id,
                DemandCalculationRun.is_current_attempt.is_(True),
            )
            .group_by(
                DemandRunItemResult.shortage_risk_level
            )
        ).all()

        for level, count in rows:
            severity = self._shortage_severity(level)
            if severity is not None:
                distribution[severity] += int(count)

        return distribution

    def _risk_items(
        self,
        session: Session,
        tenant_id: str,
    ) -> list[RiskItem]:
        shortage_rank = case(
            (
                DemandRunItemResult.shortage_risk_level
                == ShortageRiskLevel.CRITICAL,
                4,
            ),
            (
                DemandRunItemResult.shortage_risk_level
                == ShortageRiskLevel.HIGH,
                3,
            ),
            (
                DemandRunItemResult.shortage_risk_level
                == ShortageRiskLevel.MEDIUM,
                2,
            ),
            (
                DemandRunItemResult.shortage_risk_level
                == ShortageRiskLevel.LOW,
                1,
            ),
            else_=0,
        )
        shortage_rows = session.execute(
            select(
                DemandRunItemResult.id,
                DemandRunItemResult.spare_part_code_snapshot,
                DemandRunItemResult.spare_part_name_snapshot,
                DemandRunItemResult.net_demand_gap,
                DemandRunItemResult.shortage_risk_level,
                DemandRunItemResult.updated_at,
            )
            .join(
                DemandCalculationRun,
                DemandCalculationRun.id
                == DemandRunItemResult.calculation_run_id,
            )
            .where(
                DemandRunItemResult.tenant_id == tenant_id,
                DemandCalculationRun.tenant_id == tenant_id,
                DemandCalculationRun.is_current_attempt.is_(True),
                DemandRunItemResult.shortage_risk_level
                != ShortageRiskLevel.NONE,
            )
            .order_by(
                shortage_rank.desc(),
                DemandRunItemResult.net_demand_gap.desc(),
                DemandRunItemResult.updated_at.desc(),
            )
            .limit(self._RISK_LIMIT)
        ).all()

        items = [
            RiskItem(
                key=f"inventory-gap:{row.id}",
                risk_type="INVENTORY_GAP",
                entity_type="DEMAND_RUN_ITEM",
                entity_id=row.id,
                title=(
                    f"{row.spare_part_code_snapshot} "
                    f"{row.spare_part_name_snapshot}"
                ),
                severity=(
                    self._shortage_severity(
                        row.shortage_risk_level
                    )
                    or "LOW"
                ),
                value=row.net_demand_gap,
                detail=(
                    "Net demand gap: "
                    f"{row.net_demand_gap}"
                ),
                updated_at=row.updated_at,
                route="/platform/maintenance/inventory-gap",
            )
            for row in shortage_rows
        ]

        finding_rank = case(
            (AIReviewFinding.severity == AISeverity.CRITICAL, 4),
            (AIReviewFinding.severity == AISeverity.ERROR, 3),
            (AIReviewFinding.severity == AISeverity.WARNING, 2),
            else_=1,
        )
        finding_rows = session.execute(
            select(
                AIReviewFinding.id,
                AIReviewFinding.review_run_id,
                AIReviewFinding.finding_title,
                AIReviewFinding.deterministic_message,
                AIReviewFinding.severity,
                AIReviewFinding.updated_at,
            )
            .where(
                AIReviewFinding.tenant_id == tenant_id,
                AIReviewFinding.status.in_(
                    (
                        AIReviewFindingStatus.OPEN,
                        AIReviewFindingStatus.ACKNOWLEDGED,
                    )
                ),
            )
            .order_by(
                finding_rank.desc(),
                AIReviewFinding.updated_at.desc(),
                AIReviewFinding.id.desc(),
            )
            .limit(self._RISK_LIMIT)
        ).all()
        items.extend(
            RiskItem(
                key=f"review-finding:{row.id}",
                risk_type="REVIEW_FINDING",
                entity_type="AI_REVIEW_FINDING",
                entity_id=row.id,
                title=row.finding_title,
                severity=self._review_severity(row.severity),
                detail=row.deterministic_message,
                updated_at=row.updated_at,
                route=(
                    "/platform/maintenance/reviews/"
                    f"{row.review_run_id}"
                ),
            )
            for row in finding_rows
        )

        return sorted(
            items,
            key=lambda item: (
                self._RISK_RANK.get(item.severity, 0),
                self._timestamp(item.updated_at),
                item.entity_id,
            ),
            reverse=True,
        )[: self._RISK_LIMIT]

    @staticmethod
    def _enum_value(value: Any) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return str(value)

    @classmethod
    def _shortage_severity(
        cls,
        level: ShortageRiskLevel | str,
    ) -> str | None:
        value = cls._enum_value(level)
        return {
            ShortageRiskLevel.NONE.value: None,
            ShortageRiskLevel.LOW.value: "LOW",
            ShortageRiskLevel.MEDIUM.value: "MEDIUM",
            ShortageRiskLevel.HIGH.value: "HIGH",
            ShortageRiskLevel.CRITICAL.value: "BLOCKING",
        }.get(value)

    @classmethod
    def _review_severity(
        cls,
        severity: AISeverity | str,
    ) -> str:
        value = cls._enum_value(severity)
        return {
            AISeverity.INFO.value: "LOW",
            AISeverity.WARNING.value: "MEDIUM",
            AISeverity.ERROR.value: "HIGH",
            AISeverity.CRITICAL.value: "BLOCKING",
        }.get(value, "LOW")

    @staticmethod
    def _timestamp(value: datetime) -> float:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()


dashboard_service = DashboardService()
