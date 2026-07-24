from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from maintenance_ai.enums import ReviewBlockingLevel, ReviewSeverity
from maintenance_ai.reviewing import ReviewFindingInput
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import (
    AIReviewFinding,
    AIReviewRun,
    DemandCalculationRun,
    DemandRunItemResult,
    SparePart,
)
from app.models.enums import AIBlockingLevel, AIReviewRunStatus, AISeverity
from app.repositories.ai_review_repository import AIReviewRepository
from app.services.ai_review_engine import AIReviewEngine, ReviewContext


@dataclass(slots=True)
class AIReviewResult:
    run: AIReviewRun
    findings: list[AIReviewFinding]

    @property
    def id(self) -> int:
        return self.run.id


def load_review_context(session: Session, calculation_run_id: int) -> ReviewContext:
    run = session.get(DemandCalculationRun, calculation_run_id)
    if run is None:
        raise NotFoundError("demand_calculation_run", calculation_run_id)
    rows = list(
        session.scalars(
            select(DemandRunItemResult).where(
                DemandRunItemResult.calculation_run_id == calculation_run_id
            )
        ).all()
    )
    items = []
    for row in rows:
        spare = session.get(SparePart, row.spare_part_id)
        items.append(
            {
                "spare_part_id": row.spare_part_id,
                "spare_part_code": row.spare_part_code_snapshot,
                "recommended_spare_quantity": row.recommended_spare_quantity,
                "usable_inventory": row.usable_inventory,
                "net_demand_gap": row.net_demand_gap,
                "inventory_coverage_rate": row.inventory_coverage_rate,
                "target_service_level": row.target_service_level,
                "selected_reliability_profile_id": row.selected_reliability_profile_id,
                "selected_repair_profile_id": row.selected_repair_profile_id,
                "is_repairable": bool(spare and spare.is_repairable),
                "is_active": bool(spare and spare.is_active),
                "common_shock_ratio": (
                    row.common_shock_demand / row.recommended_spare_quantity
                    if row.recommended_spare_quantity
                    else 0
                ),
                "calculation_reference": f"run:{calculation_run_id}",
                "warning_codes": row.warning_codes_json or [],
            }
        )
    calculation = run.calculation
    snapshot = calculation.input_snapshot_json if calculation else {}
    return ReviewContext(
        scenario_snapshot=snapshot,
        calculation_items=items,
        evidence_items=[],
    )


class AIReviewService:
    def __init__(
        self,
        *,
        engine,
        explainer=None,
        context_loader: Callable[[Session, int], ReviewContext] = load_review_context,
        repository: AIReviewRepository | None = None,
    ) -> None:
        self.engine = engine
        self.explainer = explainer
        self.context_loader = context_loader
        self.repository = repository or AIReviewRepository()

    async def create_demand_list_review(
        self,
        session: Session,
        *,
        calculation_run_id: int | None,
        created_by: str,
        session_id: int | None = None,
        context: ReviewContext | None = None,
    ) -> AIReviewResult:
        del created_by
        loaded = context or self.context_loader(session, int(calculation_run_id))
        run = self.repository.create_run(
            session,
            input_snapshot={
                "scenario_snapshot": loaded.scenario_snapshot,
                "calculation_items": loaded.calculation_items,
                "evidence_items": loaded.evidence_items,
            },
            rule_set_version=getattr(self.engine, "rule_set_version", "1.0"),
            session_id=session_id,
            calculation_run_id=calculation_run_id,
            scenario_version_id=loaded.scenario_snapshot.get("scenario_version_id"),
        )
        run.status = AIReviewRunStatus.RUNNING
        session.flush()
        drafts = self.engine.run(loaded)
        rows: list[AIReviewFinding] = []
        fallback_count = 0
        for draft in drafts:
            spare_id = draft.affected_spare_part_id
            if spare_id is not None and session.get(SparePart, spare_id) is None:
                spare_id = None
            payload = {
                "rule_code": draft.rule_code,
                "rule_version": draft.rule_version,
                "category": draft.category,
                "severity": AISeverity(draft.severity),
                "blocking_level": AIBlockingLevel(draft.blocking_level),
                "affected_entity_type": draft.affected_entity_type,
                "affected_entity_id": draft.affected_entity_id,
                "affected_spare_part_id": spare_id,
                "finding_title": draft.finding_title,
                "deterministic_message": draft.deterministic_message,
                "observed_value_json": draft.observed_value,
                "expected_range_json": draft.expected_range,
                "evidence_references_json": draft.evidence_references,
                "suggested_actions_json": draft.suggested_actions,
            }
            row = self.repository.add_finding(session, run.id, payload)
            if self.explainer is not None:
                try:
                    explanation_input = ReviewFindingInput(
                        rule_code=draft.rule_code,
                        title=draft.finding_title,
                        deterministic_message=draft.deterministic_message,
                        severity=ReviewSeverity(draft.severity),
                        blocking_level=ReviewBlockingLevel(draft.blocking_level),
                        evidence_ids=tuple(draft.evidence_references),
                        observed_value=None
                        if draft.observed_value is None
                        else str(draft.observed_value),
                        expected_range=None
                        if draft.expected_range is None
                        else str(draft.expected_range),
                    )
                    explanation = await self.explainer.explain(explanation_input)
                    row.llm_explanation_json = explanation.model_dump(mode="json")
                except Exception as exc:
                    fallback_count += 1
                    row.llm_explanation_json = {
                        "summary": draft.deterministic_message,
                        "suggested_actions": draft.suggested_actions,
                        "fallback": True,
                        "reason": type(exc).__name__,
                    }
            else:
                row.llm_explanation_json = {
                    "summary": draft.deterministic_message,
                    "suggested_actions": draft.suggested_actions,
                    "fallback": True,
                    "reason": "EXPLAINER_NOT_CONFIGURED",
                }
                fallback_count += 1
            rows.append(row)
        run.status = AIReviewRunStatus.COMPLETED
        run.summary_json = {
            "finding_count": len(rows),
            "fallback_explanations": fallback_count,
            "severity_counts": {
                severity: sum(1 for row in rows if row.severity.value == severity)
                for severity in ("INFO", "WARNING", "ERROR", "CRITICAL")
            },
        }
        session.commit()
        session.refresh(run)
        return AIReviewResult(run=run, findings=rows)


ai_review_service = AIReviewService(engine=AIReviewEngine())
