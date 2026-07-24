from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIReviewFinding, AIReviewRun


class AIReviewRepository:
    def create_run(
        self,
        session: Session,
        *,
        input_snapshot: dict[str, Any],
        rule_set_version: str = "1.0",
        session_id: int | None = None,
        calculation_run_id: int | None = None,
        scenario_version_id: int | None = None,
    ) -> AIReviewRun:
        row = AIReviewRun(
            session_id=session_id,
            calculation_run_id=calculation_run_id,
            scenario_version_id=scenario_version_id,
            rule_set_version=rule_set_version,
            input_snapshot_json=input_snapshot,
        )
        session.add(row)
        session.flush()
        return row

    def add_finding(
        self, session: Session, run_id: int, payload: dict[str, Any]
    ) -> AIReviewFinding:
        row = AIReviewFinding(review_run_id=run_id, **payload)
        session.add(row)
        session.flush()
        return row

    def list_findings(self, session: Session, run_id: int) -> list[AIReviewFinding]:
        return list(
            session.scalars(
                select(AIReviewFinding)
                .where(AIReviewFinding.review_run_id == run_id)
                .order_by(AIReviewFinding.id)
            ).all()
        )


ai_review_repository = AIReviewRepository()
