from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.exceptions import NotFoundError
from app.schemas.business_card import (
    CalculationCard,
    CalculationPayload,
    InventoryGapCard,
    InventoryGapPayload,
    MaintenanceBusinessCard,
    MaintenanceCardTarget,
    ModelComparisonCard,
    ModelComparisonPayload,
    ReportCard,
    ReportPayload,
    ReviewFindingCard,
    ReviewFindingPayload,
    ScenarioDraftCard,
    ScenarioDraftPayload,
    canonicalize_cards,
)
from app.security.actor import ActorContext

SCENARIO_DRAFT_STATUSES = {
    "UNDERSTANDING",
    "CLARIFICATION_REQUIRED",
    "PLANNED",
    "PARTIALLY_COMPLETED",
}
REPORT_CARD_STATUSES = {
    "READY_FOR_REVIEW",
    "FINALIZED",
    "PARTIALLY_COMPLETED",
    "FAILED",
}
INVENTORY_CARD_STATUSES = {
    "PREVIEWED",
    "CONFIRMED",
    "EXECUTING",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
}
COMPARABLE_CALCULATION_STATUSES = {"SUCCEEDED", "PARTIAL_SUCCESS"}
SEVERITY_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _observed_at(*rows: Any) -> datetime:
    values = [
        value
        for row in rows
        for value in (getattr(row, "updated_at", None), getattr(row, "created_at", None))
        if isinstance(value, datetime)
    ]
    if values:
        return max(values)
    return datetime.now(timezone.utc)


def _title(value: str, fallback: str) -> str:
    clean = value.strip() if isinstance(value, str) else ""
    return (clean or fallback)[:200]


class BusinessCardService:
    def __init__(
        self,
        *,
        ai_session_repository=None,
        calculation_group_repository=None,
        allocation_repository=None,
        demand_review_repository=None,
        ai_report_repository=None,
    ) -> None:
        if ai_session_repository is None:
            from app.repositories.ai_session_repository import AISessionRepository
            ai_session_repository = AISessionRepository()
        if calculation_group_repository is None:
            from app.repositories.calculation_group_repository import CalculationGroupRepository
            calculation_group_repository = CalculationGroupRepository()
        if allocation_repository is None:
            from app.repositories.allocation_repository import AllocationRepository
            allocation_repository = AllocationRepository()
        if demand_review_repository is None:
            from app.repositories.demand_review_repository import DemandReviewRepository
            demand_review_repository = DemandReviewRepository()
        if ai_report_repository is None:
            from app.repositories.ai_report_repository import AIReportRepository
            ai_report_repository = AIReportRepository()

        self.ai_session_repository = ai_session_repository
        self.calculation_group_repository = calculation_group_repository
        self.allocation_repository = allocation_repository
        self.demand_review_repository = demand_review_repository
        self.ai_report_repository = ai_report_repository

    def build_scenario_draft(
        self, session, actor: ActorContext, ai_session_id: int
    ) -> ScenarioDraftCard | None:
        row = self.ai_session_repository.get(session, actor.tenant_id, ai_session_id)
        if row is None:
            raise NotFoundError("ai_session", ai_session_id)
        snapshot = self.ai_session_repository.latest_snapshot(
            session, actor.tenant_id, ai_session_id
        )
        if snapshot is None:
            return None
        if getattr(row, "active_scenario_version_id", None) is not None:
            return None
        if _enum_value(row.status) not in SCENARIO_DRAFT_STATUSES:
            return None
        if not getattr(snapshot, "scenario_draft_json", None):
            return None
        return ScenarioDraftCard(
            title=_title(getattr(row, "title", ""), "场景草稿"),
            summary=f"场景草稿快照 v{snapshot.snapshot_version} 可继续完善。",
            status=_enum_value(row.status),
            target=MaintenanceCardTarget(
                object_type="AI_SESSION_SNAPSHOT",
                object_id=row.id,
                observed_version=snapshot.snapshot_version,
                navigation_path=(
                    f"/platform/maintenance/scenarios/new?session_id={row.id}"
                ),
            ),
            observed_at=_observed_at(snapshot, row),
            payload=ScenarioDraftPayload(),
        )

    def build_calculation(
        self, session, actor: ActorContext, group_id: int
    ) -> CalculationCard:
        group = self.calculation_group_repository.get(
            session, actor.tenant_id, group_id
        )
        if group is None:
            raise NotFoundError("calculation_group", group_id)
        status = _enum_value(group.status)
        return CalculationCard(
            title=f"计算组 #{group.id}",
            summary=(
                f"状态 {status}，当前候选方案 {len(group.current_children)} 个。"
            ),
            status=status,
            target=MaintenanceCardTarget(
                object_type="CALCULATION_GROUP",
                object_id=group.id,
                observed_version=group.version,
                navigation_path=(
                    f"/platform/maintenance/calculations/{group.id}/progress"
                ),
            ),
            observed_at=_observed_at(group),
            payload=CalculationPayload(
                group_id=group.id,
                scenario_version_id=group.scenario_version_id,
                status=status,
                primary_candidate_key=group.primary_candidate_key,
                current_candidate_count=len(group.current_children),
                observed_version=group.version,
            ),
        )

    def build_model_comparison(
        self, session, actor: ActorContext, group_id: int
    ) -> ModelComparisonCard | None:
        group = self.calculation_group_repository.get(
            session, actor.tenant_id, group_id
        )
        if group is None:
            raise NotFoundError("calculation_group", group_id)
        comparable = [
            child
            for child in group.current_children
            if getattr(child, "calculation", None) is not None
            and _enum_value(child.calculation.status)
            in COMPARABLE_CALCULATION_STATUSES
            and bool(getattr(child.calculation, "result_summary_json", None))
        ]
        if len(comparable) < 2:
            return None
        status = _enum_value(group.status)
        return ModelComparisonCard(
            title=f"模型比较 #{group.id}",
            summary=f"已有 {len(comparable)} 个当前候选结果可比较。",
            status=status,
            target=MaintenanceCardTarget(
                object_type="CALCULATION_GROUP",
                object_id=group.id,
                observed_version=group.version,
                navigation_path=(
                    f"/platform/maintenance/calculations/{group.id}/comparison"
                ),
            ),
            observed_at=_observed_at(group, *comparable),
            payload=ModelComparisonPayload(
                group_id=group.id,
                scenario_version_id=group.scenario_version_id,
                comparable_candidate_count=len(comparable),
                primary_candidate_key=group.primary_candidate_key,
                observed_version=group.version,
            ),
        )

    def build_inventory_gap(
        self, session, actor: ActorContext, plan_id: int
    ) -> InventoryGapCard | None:
        plan = self.allocation_repository.get_plan(
            session, actor.tenant_id, plan_id
        )
        if plan is None:
            raise NotFoundError("allocation_plan", plan_id)
        status = _enum_value(plan.status)
        if status not in INVENTORY_CARD_STATUSES:
            return None
        lines = self.allocation_repository.list_plan_lines(
            session, actor.tenant_id, plan_id
        )
        gap_lines = [line for line in lines if Decimal(line.gap_quantity) > 0]
        risk_lines = [line for line in lines if bool(getattr(line, "risks_json", None))]
        if not gap_lines and not risk_lines:
            return None
        total_gap = sum((Decimal(line.gap_quantity) for line in gap_lines), Decimal("0"))
        return InventoryGapCard(
            title=f"库存缺口 #{plan.id}",
            summary=(
                f"缺口物料 {len(gap_lines)} 项，风险物料 {len(risk_lines)} 项。"
            ),
            status=status,
            target=MaintenanceCardTarget(
                object_type="ALLOCATION_PLAN",
                object_id=plan.id,
                observed_version=plan.version,
                navigation_path=(
                    f"/platform/maintenance/inventory-gap/allocations/{plan.id}"
                ),
            ),
            observed_at=_observed_at(plan, *lines),
            payload=InventoryGapPayload(
                gap_item_count=len(gap_lines),
                total_gap_quantity=total_gap,
                risk_item_count=len(risk_lines),
                source_demand_list_id=plan.source_demand_list_id,
                plan_status=status,
                observed_version=plan.version,
            ),
        )

    def build_review_finding(
        self, session, actor: ActorContext, review_id: int
    ) -> ReviewFindingCard | None:
        review = self.demand_review_repository.get(
            session, actor.tenant_id, review_id
        )
        if review is None:
            raise NotFoundError("demand_review", review_id)
        findings = self.demand_review_repository.list_findings(
            session, actor.tenant_id, review_id
        )
        if not findings:
            return None

        def key(finding: Any) -> tuple[int, int, int, int, int]:
            return (
                0 if _enum_value(finding.decision_status) == "PENDING" else 1,
                0 if bool(finding.blocking) else 1,
                SEVERITY_PRIORITY.get(_enum_value(finding.severity), 99),
                0 if bool(finding.requires_admin_acceptance) else 1,
                int(finding.id),
            )

        finding = min(findings, key=key)
        severity = _enum_value(finding.severity)
        decision_status = _enum_value(finding.decision_status)
        return ReviewFindingCard(
            title=f"{severity} 复核发现 #{finding.id}",
            summary=(
                f"复核 #{review.id} 尚有 {review.pending_finding_count} 个待处理发现。"
            ),
            status=decision_status,
            target=MaintenanceCardTarget(
                object_type="DEMAND_REVIEW_FINDING",
                object_id=finding.id,
                observed_version=finding.version,
                navigation_path=f"/platform/maintenance/reviews/{review.id}",
            ),
            observed_at=_observed_at(finding, review),
            payload=ReviewFindingPayload(
                finding_id=finding.id,
                review_id=review.id,
                severity=severity,
                blocking=bool(finding.blocking),
                remaining_pending_count=review.pending_finding_count,
                observed_version=finding.version,
            ),
        )

    def build_report(
        self, session, actor: ActorContext, report_job_id: int
    ) -> ReportCard | None:
        job = self.ai_report_repository.get_job(
            session, actor.tenant_id, report_job_id
        )
        if job is None:
            raise NotFoundError("ai_report_job", report_job_id)
        status = _enum_value(job.status)
        if status not in REPORT_CARD_STATUSES:
            return None
        version = self.ai_report_repository.latest_version(
            session, actor.tenant_id, report_job_id
        )
        if version is None:
            return None
        version_status = _enum_value(version.status)
        report_type = _enum_value(job.report_type)
        return ReportCard(
            title=_title(job.title, f"报告 {job.report_code}"),
            summary=f"报告 {job.report_code} 当前版本 v{version.version_number}。",
            status=status,
            target=MaintenanceCardTarget(
                object_type="AI_REPORT_JOB",
                object_id=job.id,
                observed_version=version.version_number,
                navigation_path=(
                    f"/platform/maintenance/reports?report_id={job.id}"
                ),
            ),
            observed_at=_observed_at(version, job),
            payload=ReportPayload(
                report_id=job.id,
                report_code=job.report_code,
                report_type=report_type,
                job_status=status,
                version_id=version.id,
                version_number=version.version_number,
                version_status=version_status,
            ),
        )

    def build_cards(
        self,
        session,
        actor: ActorContext,
        references: Iterable[tuple[str, int]],
    ) -> list[MaintenanceBusinessCard]:
        builders = {
            "SCENARIO_DRAFT": self.build_scenario_draft,
            "CALCULATION": self.build_calculation,
            "MODEL_COMPARISON": self.build_model_comparison,
            "INVENTORY_GAP": self.build_inventory_gap,
            "REVIEW_FINDING": self.build_review_finding,
            "REPORT": self.build_report,
        }
        cards: list[MaintenanceBusinessCard] = []
        seen_refs: set[tuple[str, int]] = set()
        for card_type, object_id in references:
            ref = (card_type, object_id)
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            builder = builders.get(card_type)
            if builder is None:
                continue
            card = builder(session, actor, object_id)
            if card is not None:
                cards.append(card)
        return canonicalize_cards(cards)


business_card_service = BusinessCardService()
