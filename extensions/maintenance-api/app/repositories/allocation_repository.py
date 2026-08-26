from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AllocationPlan,
    AllocationPlanEvent,
    AllocationPlanLine,
    AllocationRuleVersion,
)
from app.repositories.base import tenant_loader_criteria
from app.services.snapshot_service import snapshot_service


class AllocationRepository:
    def get_rule(
        self,
        session: Session,
        tenant_id: str,
        rule_id: int,
    ) -> AllocationRuleVersion | None:
        return session.scalar(
            select(AllocationRuleVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationRuleVersion.tenant_id == tenant_id,
                AllocationRuleVersion.id == rule_id,
            )
        )

    def get_rule_for_update(
        self,
        session: Session,
        tenant_id: str,
        rule_id: int,
    ) -> AllocationRuleVersion | None:
        return session.scalar(
            select(AllocationRuleVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationRuleVersion.tenant_id == tenant_id,
                AllocationRuleVersion.id == rule_id,
            )
            .with_for_update()
        )

    def list_rules(
        self,
        session: Session,
        tenant_id: str,
    ) -> list[AllocationRuleVersion]:
        return list(
            session.scalars(
                select(AllocationRuleVersion)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(AllocationRuleVersion.tenant_id == tenant_id)
                .order_by(
                    AllocationRuleVersion.lineage_id.asc(),
                    AllocationRuleVersion.version_number.asc(),
                    AllocationRuleVersion.id.asc(),
                )
            ).all()
        )

    def list_lineage_rules(
        self,
        session: Session,
        tenant_id: str,
        lineage_id: str,
    ) -> list[AllocationRuleVersion]:
        return list(
            session.scalars(
                select(AllocationRuleVersion)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    AllocationRuleVersion.tenant_id == tenant_id,
                    AllocationRuleVersion.lineage_id == lineage_id,
                )
                .order_by(
                    AllocationRuleVersion.version_number.asc(),
                    AllocationRuleVersion.id.asc(),
                )
            ).all()
        )

    def next_lineage_version(
        self,
        session: Session,
        tenant_id: str,
        lineage_id: str,
    ) -> int:
        rules = self.list_lineage_rules(session, tenant_id, lineage_id)
        if not rules:
            return 1
        return max(rule.version_number for rule in rules) + 1

    def create_rule(
        self,
        session: Session,
        tenant_id: str,
        values: dict[str, Any],
    ) -> AllocationRuleVersion:
        rule = AllocationRuleVersion(tenant_id=tenant_id, **values)
        session.add(rule)
        session.flush()
        return rule

    def find_overlapping_published_rules(
        self,
        session: Session,
        *,
        tenant_id: str,
        scope_json: dict[str, Any],
        effective_from: datetime | None,
        effective_to: datetime | None,
        exclude_rule_id: int | None,
    ) -> list[AllocationRuleVersion]:
        conditions = [
            AllocationRuleVersion.tenant_id == tenant_id,
            AllocationRuleVersion.status == "PUBLISHED",
        ]
        if exclude_rule_id is not None:
            conditions.append(AllocationRuleVersion.id != exclude_rule_id)
        if effective_to is not None:
            conditions.append(
                or_(
                    AllocationRuleVersion.effective_from.is_(None),
                    AllocationRuleVersion.effective_from < effective_to,
                )
            )
        if effective_from is not None:
            conditions.append(
                or_(
                    AllocationRuleVersion.effective_to.is_(None),
                    AllocationRuleVersion.effective_to > effective_from,
                )
            )

        candidates = list(
            session.scalars(
                select(AllocationRuleVersion)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(and_(*conditions))
                .order_by(AllocationRuleVersion.id.asc())
            ).all()
        )
        target_scope = snapshot_service.canonical_json(scope_json)
        return [
            rule
            for rule in candidates
            if snapshot_service.canonical_json(rule.scope_json) == target_scope
        ]
    def get_plan_by_idempotency_key(
        self,
        session: Session,
        tenant_id: str,
        idempotency_key: str,
    ) -> AllocationPlan | None:
        return session.scalar(
            select(AllocationPlan)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationPlan.tenant_id == tenant_id,
                AllocationPlan.idempotency_key == idempotency_key,
            )
        )

    def get_plan_for_update(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> AllocationPlan | None:
        return session.scalar(
            select(AllocationPlan)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationPlan.tenant_id == tenant_id,
                AllocationPlan.id == plan_id,
            )
            .with_for_update()
        )

    def get_plan_line_for_update(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
        line_id: int,
    ) -> AllocationPlanLine | None:
        return session.scalar(
            select(AllocationPlanLine)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationPlanLine.tenant_id == tenant_id,
                AllocationPlanLine.plan_id == plan_id,
                AllocationPlanLine.id == line_id,
            )
            .with_for_update()
        )

    def list_plan_lines(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> list[AllocationPlanLine]:
        return list(
            session.scalars(
                select(AllocationPlanLine)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    AllocationPlanLine.tenant_id == tenant_id,
                    AllocationPlanLine.plan_id == plan_id,
                )
                .order_by(AllocationPlanLine.id.asc())
            ).all()
        )

    def get_plan_created_event(
        self,
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> AllocationPlanEvent | None:
        return session.scalar(
            select(AllocationPlanEvent)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationPlanEvent.tenant_id == tenant_id,
                AllocationPlanEvent.plan_id == plan_id,
                AllocationPlanEvent.event_type == "PLAN_CREATED",
            )
            .order_by(AllocationPlanEvent.id.asc())
            .limit(1)
        )
