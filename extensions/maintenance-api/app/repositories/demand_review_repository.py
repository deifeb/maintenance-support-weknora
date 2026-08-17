from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.demand_review import (
    DemandReview,
    DemandReviewDecision,
    DemandReviewEvent,
    DemandReviewFinding,
)
from app.models.enums import (
    DemandReviewCommandType,
    DemandReviewSeverity,
)
from app.repositories.base import tenant_loader_criteria

_SEVERITY_ORDER = case(
    (DemandReviewFinding.severity == DemandReviewSeverity.CRITICAL, 0),
    (DemandReviewFinding.severity == DemandReviewSeverity.HIGH, 1),
    (DemandReviewFinding.severity == DemandReviewSeverity.MEDIUM, 2),
    else_=3,
)


class DemandReviewRepository:
    def get(
        self,
        session: Session,
        tenant_id: str,
        review_id: int,
    ) -> DemandReview | None:
        return session.scalar(
            select(DemandReview)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandReview.tenant_id == tenant_id,
                DemandReview.id == review_id,
            )
        )

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        review_id: int,
    ) -> DemandReview | None:
        return session.scalar(
            select(DemandReview)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandReview.tenant_id == tenant_id,
                DemandReview.id == review_id,
            )
            .with_for_update()
        )

    def list_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DemandReview], int]:
        conditions = (DemandReview.tenant_id == tenant_id,)
        rows = list(
            session.scalars(
                select(DemandReview)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(*conditions)
                .order_by(
                    DemandReview.created_at.desc(),
                    DemandReview.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = int(
            session.scalar(
                select(func.count())
                .select_from(DemandReview)
                .where(*conditions)
            )
            or 0
        )
        return rows, total

    @staticmethod
    def _finding_statement(
        tenant_id: str,
        review_id: int,
    ):
        return (
            select(DemandReviewFinding)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandReviewFinding.tenant_id == tenant_id,
                DemandReviewFinding.review_id == review_id,
            )
            .order_by(
                _SEVERITY_ORDER.asc(),
                case(
                    (
                        DemandReviewFinding.source_demand_list_item_id.is_(None),
                        1,
                    ),
                    else_=0,
                ).asc(),
                DemandReviewFinding.source_demand_list_item_id.asc(),
                DemandReviewFinding.finding_key.asc(),
            )
        )

    def list_findings(
        self,
        session: Session,
        tenant_id: str,
        review_id: int,
    ) -> list[DemandReviewFinding]:
        return list(
            session.scalars(
                self._finding_statement(
                    tenant_id,
                    review_id,
                )
            ).all()
        )

    def findings_for_update(
        self,
        session: Session,
        tenant_id: str,
        review_id: int,
    ) -> list[DemandReviewFinding]:
        return list(
            session.scalars(
                self._finding_statement(
                    tenant_id,
                    review_id,
                ).with_for_update()
            ).all()
        )

    def create_review(
        self,
        session: Session,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> DemandReview:
        review = DemandReview(
            tenant_id=tenant_id,
            **dict(data),
        )
        session.add(review)
        session.flush()
        return review

    def append_finding(
        self,
        session: Session,
        tenant_id: str,
        *,
        review_id: int,
        data: Mapping[str, Any],
    ) -> DemandReviewFinding:
        if self.get_for_update(session, tenant_id, review_id) is None:
            raise LookupError("demand review not found")
        finding = DemandReviewFinding(
            tenant_id=tenant_id,
            review_id=review_id,
            **dict(data),
        )
        session.add(finding)
        session.flush()
        return finding

    def append_decision(
        self,
        session: Session,
        tenant_id: str,
        *,
        review_id: int,
        finding_id: int,
        data: Mapping[str, Any],
    ) -> DemandReviewDecision:
        review = self.get_for_update(session, tenant_id, review_id)
        if review is None:
            raise LookupError("demand review not found")
        finding = session.scalar(
            select(DemandReviewFinding).where(
                DemandReviewFinding.tenant_id == tenant_id,
                DemandReviewFinding.review_id == review_id,
                DemandReviewFinding.id == finding_id,
            )
        )
        if finding is None:
            raise LookupError("demand review finding not found")
        decision = DemandReviewDecision(
            tenant_id=tenant_id,
            review_id=review_id,
            finding_id=finding_id,
            **dict(data),
        )
        session.add(decision)
        session.flush()
        return decision

    def append_event(
        self,
        session: Session,
        tenant_id: str,
        *,
        review_id: int,
        data: Mapping[str, Any],
    ) -> DemandReviewEvent:
        if self.get_for_update(session, tenant_id, review_id) is None:
            raise LookupError("demand review not found")
        event = DemandReviewEvent(
            tenant_id=tenant_id,
            review_id=review_id,
            **dict(data),
        )
        session.add(event)
        session.flush()
        return event

    def find_command_event(
        self,
        session: Session,
        tenant_id: str,
        *,
        command_type: DemandReviewCommandType,
        idempotency_key: str,
    ) -> DemandReviewEvent | None:
        return session.scalar(
            select(DemandReviewEvent)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandReviewEvent.tenant_id == tenant_id,
                DemandReviewEvent.command_type == command_type,
                DemandReviewEvent.idempotency_key == idempotency_key,
            )
        )

    def delete_findings(
        self,
        session: Session,
        tenant_id: str,
        review_id: int,
    ) -> None:
        rows: Sequence[DemandReviewFinding] = self.findings_for_update(
            session,
            tenant_id,
            review_id,
        )
        for row in rows:
            session.delete(row)
        session.flush()
