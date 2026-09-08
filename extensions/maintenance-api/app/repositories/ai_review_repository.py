from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIModelCall,
    AIReviewFinding,
    AIReviewRun,
    AISession,
    DemandCalculationRun,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import AIReviewFindingStatus
from app.repositories.base import tenant_loader_criteria

ModelT = TypeVar("ModelT")


def _owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT | None:
    return session.scalar(
        select(model)
        .options(tenant_loader_criteria(tenant_id))
        .execution_options(populate_existing=True)
        .where(
            model.id == identifier,
            model.tenant_id == tenant_id,
        )
    )


def _require_owned(
    session: Session,
    tenant_id: str,
    model: type[ModelT],
    identifier: int,
) -> ModelT:
    row = _owned(
        session,
        tenant_id,
        model,
        identifier,
    )
    if row is None:
        raise LookupError(
            f"{model.__name__} {identifier} not found"
        )
    return row


class AIReviewRepository:
    def create_run(
        self,
        session: Session,
        tenant_id: str,
        *,
        input_snapshot: dict[str, Any],
        rule_set_version: str = "1.0",
        session_id: int | None = None,
        calculation_run_id: int | None = None,
        scenario_version_id: int | None = None,
    ) -> AIReviewRun:
        if session_id is not None:
            _require_owned(
                session,
                tenant_id,
                AISession,
                session_id,
            )
        if calculation_run_id is not None:
            _require_owned(
                session,
                tenant_id,
                DemandCalculationRun,
                calculation_run_id,
            )
        if scenario_version_id is not None:
            _require_owned(
                session,
                tenant_id,
                DemandScenarioVersion,
                scenario_version_id,
            )
        row = AIReviewRun(
            tenant_id=tenant_id,
            session_id=session_id,
            calculation_run_id=calculation_run_id,
            scenario_version_id=scenario_version_id,
            rule_set_version=rule_set_version,
            input_snapshot_json=input_snapshot,
        )
        session.add(row)
        session.flush()
        return row

    def get_run(
        self,
        session: Session,
        tenant_id: str,
        run_id: int,
    ) -> AIReviewRun | None:
        return _owned(
            session,
            tenant_id,
            AIReviewRun,
            run_id,
        )

    def add_finding(
        self,
        session: Session,
        tenant_id: str,
        run_id: int,
        payload: dict[str, Any],
    ) -> AIReviewFinding:
        _require_owned(
            session,
            tenant_id,
            AIReviewRun,
            run_id,
        )
        clean = {
            key: value
            for key, value in payload.items()
            if key not in {
                "tenant_id",
                "review_run_id",
                "status",
                "resolved_at",
                "resolved_by",
                "resolution_comment",
            }
        }
        model_call_id = clean.get(
            "llm_model_call_id"
        )
        if model_call_id is not None:
            _require_owned(
                session,
                tenant_id,
                AIModelCall,
                int(model_call_id),
            )
        spare_id = clean.get(
            "affected_spare_part_id"
        )
        if spare_id is not None:
            _require_owned(
                session,
                tenant_id,
                SparePart,
                int(spare_id),
            )
        row = AIReviewFinding(
            tenant_id=tenant_id,
            review_run_id=run_id,
            status=AIReviewFindingStatus.OPEN,
            **clean,
        )
        session.add(row)
        session.flush()
        return row

    def get_finding(
        self,
        session: Session,
        tenant_id: str,
        finding_id: int,
    ) -> AIReviewFinding | None:
        return _owned(
            session,
            tenant_id,
            AIReviewFinding,
            finding_id,
        )

    def list_findings(
        self,
        session: Session,
        tenant_id: str,
        run_id: int,
    ) -> list[AIReviewFinding]:
        _require_owned(
            session,
            tenant_id,
            AIReviewRun,
            run_id,
        )
        return list(
            session.scalars(
                select(AIReviewFinding)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .where(
                    AIReviewFinding.tenant_id == tenant_id,
                    AIReviewFinding.review_run_id == run_id,
                )
                .order_by(AIReviewFinding.id)
            ).all()
        )


ai_review_repository = AIReviewRepository()
