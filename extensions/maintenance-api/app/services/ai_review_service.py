from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from maintenance_ai.enums import (
    ReviewBlockingLevel,
    ReviewSeverity,
)
from maintenance_ai.reviewing import (
    ReviewFindingInput,
)
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.models import (
    AIReviewFinding,
    AIReviewRun,
)
from app.models.enums import (
    AIBlockingLevel,
    AIReviewFindingStatus,
    AIReviewRunStatus,
    AISeverity,
)
from app.repositories import (
    DemandCalculationRepository,
    DemandCalculationRunRepository,
    DemandRunItemResultRepository,
    SparePartRepository,
)
from app.repositories.ai_review_repository import (
    AIReviewRepository,
)
from app.security.actor import (
    ActorContext,
    MaintenanceRole,
)
from app.security.permissions import require_role
from app.services.ai_review_engine import (
    AIReviewEngine,
    ReviewContext,
)


@dataclass(slots=True)
class AIReviewResult:
    run: AIReviewRun
    findings: list[AIReviewFinding]

    @property
    def id(self) -> int:
        return self.run.id


def load_review_context(
    session: Session,
    actor: ActorContext,
    calculation_run_id: int,
) -> ReviewContext:
    run = (
        DemandCalculationRunRepository()
        .get_by_id(
            session,
            actor.tenant_id,
            calculation_run_id,
        )
    )
    if run is None:
        raise NotFoundError(
            "demand_calculation_run",
            calculation_run_id,
        )

    rows = (
        DemandRunItemResultRepository()
        .list_for_run(
            session,
            actor.tenant_id,
            calculation_run_id,
        )
    )
    spare_repository = SparePartRepository()
    items = []
    for row in rows:
        spare = spare_repository.get_by_id(
            session,
            actor.tenant_id,
            row.spare_part_id,
        )
        items.append(
            {
                "spare_part_id": (
                    row.spare_part_id
                ),
                "spare_part_code": (
                    row
                    .spare_part_code_snapshot
                ),
                "recommended_spare_quantity": (
                    row
                    .recommended_spare_quantity
                ),
                "usable_inventory": (
                    row.usable_inventory
                ),
                "net_demand_gap": (
                    row.net_demand_gap
                ),
                "inventory_coverage_rate": (
                    row
                    .inventory_coverage_rate
                ),
                "target_service_level": (
                    row.target_service_level
                ),
                "selected_reliability_profile_id": (
                    row
                    .selected_reliability_profile_id
                ),
                "selected_repair_profile_id": (
                    row
                    .selected_repair_profile_id
                ),
                "is_repairable": bool(
                    spare
                    and spare.is_repairable
                ),
                "is_active": bool(
                    spare
                    and spare.is_active
                ),
                "common_shock_ratio": (
                    row.common_shock_demand
                    / row
                    .recommended_spare_quantity
                    if (
                        row
                        .recommended_spare_quantity
                    )
                    else 0
                ),
                "calculation_reference": (
                    f"run:{calculation_run_id}"
                ),
                "warning_codes": (
                    row.warning_codes_json or []
                ),
            }
        )

    calculation = (
        DemandCalculationRepository()
        .get_by_id(
            session,
            actor.tenant_id,
            run.calculation_id,
        )
    )
    if calculation is None:
        raise NotFoundError(
            "demand_calculation",
            run.calculation_id,
        )
    snapshot = (
        calculation.input_snapshot_json or {}
    )
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
        context_loader: Callable[
            [
                Session,
                ActorContext,
                int,
            ],
            ReviewContext,
        ] = load_review_context,
        repository: (
            AIReviewRepository | None
        ) = None,
    ) -> None:
        self.engine = engine
        self.explainer = explainer
        self.context_loader = context_loader
        self.repository = (
            repository
            or AIReviewRepository()
        )

    async def create_demand_list_review(
        self,
        session: Session,
        actor: ActorContext,
        *,
        calculation_run_id: int | None,
        session_id: int | None = None,
        context: ReviewContext | None = None,
    ) -> AIReviewResult:
        if (
            context is None
            and calculation_run_id is None
        ):
            raise BusinessValidationError(
                (
                    "calculation_run_id is "
                    "required when review "
                    "context is absent"
                ),
                code=(
                    "REVIEW_CONTEXT_REQUIRED"
                ),
            )
        loaded = (
            context
            if context is not None
            else self.context_loader(
                session,
                actor,
                int(calculation_run_id),
            )
        )
        try:
            run = self.repository.create_run(
                session,
                actor.tenant_id,
                input_snapshot={
                    "scenario_snapshot": (
                        loaded
                        .scenario_snapshot
                    ),
                    "calculation_items": (
                        loaded
                        .calculation_items
                    ),
                    "evidence_items": (
                        loaded.evidence_items
                    ),
                },
                rule_set_version=getattr(
                    self.engine,
                    "rule_set_version",
                    "1.0",
                ),
                session_id=session_id,
                calculation_run_id=(
                    calculation_run_id
                ),
                scenario_version_id=(
                    loaded
                    .scenario_snapshot
                    .get(
                        "scenario_version_id"
                    )
                ),
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_review_context",
                (
                    calculation_run_id
                    or session_id
                    or "linked-resource"
                ),
            ) from exc

        run.status = AIReviewRunStatus.RUNNING
        session.flush()
        drafts = self.engine.run(loaded)
        rows: list[AIReviewFinding] = []
        fallback_count = 0
        spare_repository = SparePartRepository()
        for draft in drafts:
            spare_id = (
                draft.affected_spare_part_id
            )
            if (
                spare_id is not None
                and spare_repository
                .get_by_id(
                    session,
                    actor.tenant_id,
                    spare_id,
                )
                is None
            ):
                spare_id = None
            payload = {
                "rule_code": draft.rule_code,
                "rule_version": (
                    draft.rule_version
                ),
                "category": draft.category,
                "severity": AISeverity(
                    draft.severity
                ),
                "blocking_level": (
                    AIBlockingLevel(
                        draft.blocking_level
                    )
                ),
                "affected_entity_type": (
                    draft
                    .affected_entity_type
                ),
                "affected_entity_id": (
                    draft.affected_entity_id
                ),
                "affected_spare_part_id": (
                    spare_id
                ),
                "finding_title": (
                    draft.finding_title
                ),
                "deterministic_message": (
                    draft
                    .deterministic_message
                ),
                "observed_value_json": (
                    draft.observed_value
                ),
                "expected_range_json": (
                    draft.expected_range
                ),
                "evidence_references_json": (
                    draft
                    .evidence_references
                ),
                "suggested_actions_json": (
                    draft.suggested_actions
                ),
            }
            row = self.repository.add_finding(
                session,
                actor.tenant_id,
                run.id,
                payload,
            )
            if self.explainer is not None:
                try:
                    explanation_input = (
                        ReviewFindingInput(
                            rule_code=(
                                draft.rule_code
                            ),
                            title=(
                                draft
                                .finding_title
                            ),
                            deterministic_message=(
                                draft
                                .deterministic_message
                            ),
                            severity=(
                                ReviewSeverity(
                                    draft.severity
                                )
                            ),
                            blocking_level=(
                                ReviewBlockingLevel(
                                    draft
                                    .blocking_level
                                )
                            ),
                            evidence_ids=tuple(
                                draft
                                .evidence_references
                            ),
                            observed_value=(
                                None
                                if (
                                    draft
                                    .observed_value
                                    is None
                                )
                                else str(
                                    draft
                                    .observed_value
                                )
                            ),
                            expected_range=(
                                None
                                if (
                                    draft
                                    .expected_range
                                    is None
                                )
                                else str(
                                    draft
                                    .expected_range
                                )
                            ),
                        )
                    )
                    explanation = (
                        await self.explainer
                        .explain(
                            explanation_input
                        )
                    )
                    row.llm_explanation_json = (
                        explanation.model_dump(
                            mode="json"
                        )
                    )
                except Exception as exc:
                    fallback_count += 1
                    row.llm_explanation_json = {
                        "summary": (
                            draft
                            .deterministic_message
                        ),
                        "suggested_actions": (
                            draft
                            .suggested_actions
                        ),
                        "fallback": True,
                        "reason": (
                            type(exc).__name__
                        ),
                    }
            else:
                row.llm_explanation_json = {
                    "summary": (
                        draft
                        .deterministic_message
                    ),
                    "suggested_actions": (
                        draft.suggested_actions
                    ),
                    "fallback": True,
                    "reason": (
                        "EXPLAINER_NOT_CONFIGURED"
                    ),
                }
                fallback_count += 1
            rows.append(row)

        run.status = AIReviewRunStatus.COMPLETED
        run.summary_json = {
            "finding_count": len(rows),
            "fallback_explanations": (
                fallback_count
            ),
            "severity_counts": {
                severity: sum(
                    1
                    for row in rows
                    if (
                        row.severity.value
                        == severity
                    )
                )
                for severity in (
                    "INFO",
                    "WARNING",
                    "ERROR",
                    "CRITICAL",
                )
            },
        }
        session.commit()
        session.refresh(run)
        return AIReviewResult(
            run=run,
            findings=rows,
        )

    def get_review(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
    ) -> AIReviewRun:
        row = self.repository.get_run(
            session,
            actor.tenant_id,
            review_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_review",
                review_id,
            )
        return row

    def list_findings(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
    ) -> list[AIReviewFinding]:
        self.get_review(
            session,
            actor,
            review_id,
        )
        try:
            return self.repository.list_findings(
                session,
                actor.tenant_id,
                review_id,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_review",
                review_id,
            ) from exc

    def get_finding(
        self,
        session: Session,
        actor: ActorContext,
        finding_id: int,
    ) -> AIReviewFinding:
        row = self.repository.get_finding(
            session,
            actor.tenant_id,
            finding_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_review_finding",
                finding_id,
            )
        return row

    def transition_finding(
        self,
        session: Session,
        actor: ActorContext,
        finding_id: int,
        *,
        status: AIReviewFindingStatus,
        comment: str | None,
    ) -> AIReviewFinding:
        row = self.get_finding(
            session,
            actor,
            finding_id,
        )
        if (
            status
            is AIReviewFindingStatus
            .ACCEPTED_RISK
            and row.severity
            is AISeverity.CRITICAL
        ):
            require_role(
                actor,
                MaintenanceRole.ADMIN,
            )
            raise BusinessValidationError(
                (
                    "critical finding requires "
                    "secondary confirmation"
                ),
                code=(
                    "CRITICAL_RISK_"
                    "CONFIRMATION_REQUIRED"
                ),
            )

        row.status = status
        row.resolution_comment = comment
        row.resolved_at = datetime.now(
            timezone.utc
        )
        row.resolved_by = actor.user_id
        session.commit()
        session.refresh(row)
        return row


ai_review_service = AIReviewService(
    engine=AIReviewEngine()
)
