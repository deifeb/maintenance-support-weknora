from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
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

    # PLAN05_4D_TASK6_GREEN_A: strict publish receipt lookup.
    def get_rule_by_publish_idempotency_key(
        self,
        session: Session,
        tenant_id: str,
        idempotency_key: str,
    ) -> AllocationRuleVersion | None:
        return session.scalar(
            select(AllocationRuleVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                AllocationRuleVersion.tenant_id == tenant_id,
                AllocationRuleVersion.publish_idempotency_key == idempotency_key,
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

    # PLAN05_4D_TASK6_GREEN_B: stable tenant-scoped rule paging.
    def list_rules_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        lineage_id: str | None = None,
    ) -> tuple[list[AllocationRuleVersion], int]:
        conditions = [
            AllocationRuleVersion.tenant_id == tenant_id,
        ]
        if status is not None:
            conditions.append(AllocationRuleVersion.status == status)
        if lineage_id is not None:
            conditions.append(
                AllocationRuleVersion.lineage_id == lineage_id
            )

        statement = (
            select(AllocationRuleVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(*conditions)
            .order_by(
                AllocationRuleVersion.created_at.desc(),
                AllocationRuleVersion.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_statement = (
            select(func.count())
            .select_from(AllocationRuleVersion)
            .where(*conditions)
        )
        items = list(session.scalars(statement).all())
        total = int(session.scalar(count_statement) or 0)
        return items, total

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
    # PLAN05_4D_TASK6_GREEN_C: tenant-safe plan read/query surface.
    def get_plan(
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
        )

    def list_plans_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        source_demand_list_id: int | None = None,
        rule_id: int | None = None,
    ) -> tuple[list[AllocationPlan], int]:
        conditions = [AllocationPlan.tenant_id == tenant_id]
        if status is not None:
            conditions.append(AllocationPlan.status == status)
        if source_demand_list_id is not None:
            conditions.append(
                AllocationPlan.source_demand_list_id
                == source_demand_list_id
            )
        if rule_id is not None:
            conditions.append(AllocationPlan.rule_id == rule_id)

        statement = (
            select(AllocationPlan)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(*conditions)
            .order_by(
                AllocationPlan.created_at.desc(),
                AllocationPlan.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_statement = (
            select(func.count())
            .select_from(AllocationPlan)
            .where(*conditions)
        )
        items = list(session.scalars(statement).all())
        total = int(session.scalar(count_statement) or 0)
        return items, total

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
