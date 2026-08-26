from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    AllocationPlan,
    AllocationPlanEvent,
    AllocationPlanLine,
    AllocationRuleVersion,
    DemandList,
    InventoryBalance,
    InventoryPolicy,
    SerializedItem,
)
from app.repositories.allocation_repository import AllocationRepository
from app.schemas.allocation import (
    AllocationPlanLineEditCommand,
    AllocationPlanPreviewCommand,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_scoring import rank_candidates
from app.services.allocation_simulation_service import AllocationSimulationService
from app.services.snapshot_service import snapshot_service

_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_ZERO = Decimal("0")
_REPAIR_STATUSES = {"AWAITING_REPAIR", "IN_REPAIR"}


class AllocationPlanService:
    def __init__(
        self,
        *,
        repository: AllocationRepository | None = None,
    ) -> None:
        self.repository = repository or AllocationRepository()
        self._snapshot_helper = AllocationSimulationService()

    def create(
        self,
        session: Session,
        actor: ActorContext,
        source_demand_list_id: int,
        *,
        idempotency_key: str,
    ) -> AllocationPlan:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {"source_demand_list_id": int(source_demand_list_id)}
        )

        existing = self.repository.get_plan_by_idempotency_key(
            session,
            actor.tenant_id,
            clean_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                self._raise_conflict(
                    actor,
                    "allocation plan idempotency key was reused",
                    code="IDEMPOTENCY_KEY_REUSED",
                    details={"idempotency_key": clean_key},
                )
            return existing

        source = self._require_eligible_source(
            session,
            actor,
            source_demand_list_id,
        )
        demand_snapshot = self._snapshot_helper._demand_snapshot(
            session,
            actor.tenant_id,
            source,
        )
        rule = self._select_rule(
            session,
            actor,
            demand_snapshot["items"],
        )
        rule_snapshot = AllocationRuleService.snapshot(rule)
        inventory = self._snapshot_helper._inventory_state(
            session,
            actor.tenant_id,
        )
        fingerprint = snapshot_service.canonical_hash(inventory)

        plan = AllocationPlan(
            tenant_id=actor.tenant_id,
            source_demand_list_id=source.id,
            source_demand_list_version=source.version,
            rule_id=rule.id,
            inventory_fingerprint=fingerprint,
            status="DRAFT",
            idempotency_key=clean_key,
            request_hash=request_hash,
            version=1,
        )
        session.add(plan)
        session.flush()

        inventory_by_id = {int(row["id"]): row for row in inventory}
        as_of = datetime.now(timezone.utc).date()
        for item in demand_snapshot["items"]:
            ranked = rank_candidates(
                rule_snapshot,
                self._snapshot_helper._candidates(
                    rule_snapshot,
                    item,
                    inventory,
                    as_of=as_of,
                ),
            )
            line_values = self._line_values(
                session,
                actor.tenant_id,
                item,
                ranked,
                inventory,
                inventory_by_id,
            )
            session.add(
                AllocationPlanLine(
                    tenant_id=actor.tenant_id,
                    plan_id=plan.id,
                    demand_list_item_id=int(item["id"]),
                    spare_part_id=int(item["spare_part_id"]),
                    version=1,
                    **line_values,
                )
            )
        session.flush()

        self._add_event(
            session,
            actor,
            plan,
            event_type="PLAN_CREATED",
            idempotency_key=clean_key,
            request_hash=request_hash,
            before=None,
            after={
                "source": {
                    "id": source.id,
                    "version": source.version,
                    "status": self._enum_value(source.status),
                    "is_current": source.is_current,
                },
                "rule": {
                    "id": rule.id,
                    "version": rule.version,
                    "status": rule.status,
                },
                "inventory_fingerprint": fingerprint,
            },
            response={"plan_id": plan.id, "status": plan.status},
        )
        session.flush()
        return plan

    def edit_line(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
        line_id: int,
        *,
        command: AllocationPlanLineEditCommand,
    ) -> AllocationPlanLine:
        self._require_contributor(actor)
        plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)
        line = self.repository.get_plan_line_for_update(
            session,
            actor.tenant_id,
            plan_id,
            line_id,
        )
        if line is None:
            self._raise_not_found(actor, "allocation_plan_line", line_id)

        self._require_plan_version(actor, plan, command.expected_plan_version)
        if line.version != command.expected_line_version:
            self._raise_conflict(
                actor,
                "allocation plan line version conflict",
                code="ALLOCATION_PLAN_LINE_VERSION_CONFLICT",
                details={
                    "expected_version": command.expected_line_version,
                    "actual_version": line.version,
                },
            )
        if plan.status not in {"DRAFT", "PREVIEWED"}:
            self._raise_conflict(
                actor,
                "allocation plan line cannot be edited in its current state",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={"status": plan.status},
            )

        cap, cap_details = self._edit_cap(session, actor, line)
        requested = command.allocated_quantity
        if requested > cap:
            self._raise_conflict(
                actor,
                "allocation plan line exceeds current allocation policy",
                code="ALLOCATION_INVENTORY_CONFLICT",
                details={
                    "fact": "policy",
                    "requested_quantity": format(requested, "f"),
                    "allowed_quantity": format(cap, "f"),
                    **cap_details,
                    "regenerate": self._regenerate_suggestion(plan.id),
                },
            )

        before = self._line_snapshot(line)
        previous = line.allocated_quantity
        line.allocated_quantity = requested
        line.gap_quantity = max(line.demand_quantity - requested, _ZERO)
        line.manual_override_json = {
            "reason": command.reason,
            "previous_allocated_quantity": format(previous, "f"),
            "allocated_quantity": format(requested, "f"),
            "actor_user_id": actor.user_id,
            "request_id": actor.request_id,
        }
        line.version += 1
        plan.version += 1
        session.flush()

        self._add_event(
            session,
            actor,
            plan,
            event_type="LINE_EDITED",
            before=before,
            after=self._line_snapshot(line),
            response={"line_id": line.id, "line_version": line.version},
        )
        session.flush()
        return line

    def preview(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
        *,
        command: AllocationPlanPreviewCommand,
    ) -> AllocationPlan:
        self._require_contributor(actor)
        plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)
        self._require_plan_version(actor, plan, command.expected_version)
        if plan.status not in {"DRAFT", "PREVIEWED"}:
            self._raise_conflict(
                actor,
                "allocation plan cannot be previewed in its current state",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={"status": plan.status},
            )

        source = session.scalar(
            select(DemandList)
            .where(
                DemandList.tenant_id == actor.tenant_id,
                DemandList.id == plan.source_demand_list_id,
            )
            .with_for_update()
        )
        if source is None or not self._source_is_eligible(source):
            self._raise_source_conflict(
                actor,
                plan,
                actual_version=(source.version if source is not None else None),
            )
        if source.version != plan.source_demand_list_version:
            self._raise_source_conflict(
                actor,
                plan,
                actual_version=source.version,
            )

        rule = self.repository.get_rule_for_update(
            session,
            actor.tenant_id,
            plan.rule_id,
        )
        frozen = self.repository.get_plan_created_event(
            session,
            actor.tenant_id,
            plan.id,
        )
        frozen_rule_version = None
        if frozen is not None:
            payload = frozen.after_snapshot_json or {}
            frozen_rule_version = (payload.get("rule") or {}).get("version")
        if (
            rule is None
            or rule.status != "PUBLISHED"
            or frozen_rule_version is None
            or int(rule.version) != int(frozen_rule_version)
        ):
            self._raise_conflict(
                actor,
                "allocation rule changed after plan generation",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={
                    "fact": "rule",
                    "rule_id": plan.rule_id,
                    "expected_version": frozen_rule_version,
                    "actual_version": (rule.version if rule is not None else None),
                    "regenerate": self._regenerate_suggestion(plan.id),
                },
            )

        inventory = self._snapshot_helper._inventory_state(
            session,
            actor.tenant_id,
        )
        current_fingerprint = snapshot_service.canonical_hash(inventory)
        if current_fingerprint != plan.inventory_fingerprint:
            self._raise_conflict(
                actor,
                "inventory balance changed after plan generation",
                code="ALLOCATION_INVENTORY_CONFLICT",
                details={
                    "fact": "balance",
                    "expected_fingerprint": plan.inventory_fingerprint,
                    "actual_fingerprint": current_fingerprint,
                    "regenerate": self._regenerate_suggestion(plan.id),
                },
            )

        before = self._plan_snapshot(session, plan)
        demand_snapshot = self._snapshot_helper._demand_snapshot(
            session,
            actor.tenant_id,
            source,
        )
        rule_snapshot = AllocationRuleService.snapshot(rule)
        inventory_by_id = {int(row["id"]): row for row in inventory}
        as_of = datetime.now(timezone.utc).date()
        preview_lines: list[dict[str, Any]] = []
        for item in demand_snapshot["items"]:
            ranked = rank_candidates(
                rule_snapshot,
                self._snapshot_helper._candidates(
                    rule_snapshot,
                    item,
                    inventory,
                    as_of=as_of,
                ),
            )
            values = self._line_values(
                session,
                actor.tenant_id,
                item,
                ranked,
                inventory,
                inventory_by_id,
            )
            preview_lines.append(
                {
                    "demand_list_item_id": int(item["id"]),
                    "recommended_balance_id": values["recommended_balance_id"],
                    "allocated_quantity": format(values["allocated_quantity"], "f"),
                    "gap_quantity": format(values["gap_quantity"], "f"),
                    "risks": values["risks_json"],
                }
            )

        plan.status = "PREVIEWED"
        plan.version += 1
        session.flush()
        after = {
            "plan": self._plan_snapshot(session, plan),
            "recomputed_lines": preview_lines,
        }
        self._add_event(
            session,
            actor,
            plan,
            event_type="PREVIEWED",
            before=before,
            after=after,
            response={"plan_id": plan.id, "status": plan.status, "version": plan.version},
        )
        session.flush()
        return plan

    def _select_rule(
        self,
        session: Session,
        actor: ActorContext,
        items: list[dict[str, Any]],
    ) -> AllocationRuleVersion:
        now = datetime.now(timezone.utc)
        candidates = [
            rule
            for rule in self.repository.list_rules(session, actor.tenant_id)
            if rule.status == "PUBLISHED"
            and self._rule_effective(rule, now)
            and self._rule_matches_items(rule, items)
        ]
        if not candidates:
            self._raise_conflict(
                actor,
                "no published allocation rule matches the demand source",
                code="ALLOCATION_RULE_NOT_AVAILABLE",
                details={
                    "fact": "rule",
                    "regenerate": "/api/v1/allocations/rules",
                },
            )
        if len(candidates) != 1:
            self._raise_conflict(
                actor,
                "multiple published allocation rules match the demand source",
                code="ALLOCATION_RULE_AMBIGUOUS",
                details={"rule_ids": [rule.id for rule in candidates]},
            )
        return candidates[0]

    @staticmethod
    def _rule_effective(rule: AllocationRuleVersion, now: datetime) -> bool:
        def normalized(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        start = normalized(rule.effective_from)
        end = normalized(rule.effective_to)
        return (start is None or start <= now) and (end is None or now < end)

    @staticmethod
    def _rule_matches_items(
        rule: AllocationRuleVersion,
        items: list[dict[str, Any]],
    ) -> bool:
        scope = rule.scope_json or {}
        spare_part_ids = {int(value) for value in scope.get("spare_part_ids", [])}
        categories = {str(value) for value in scope.get("part_categories", [])}
        for item in items:
            if spare_part_ids and int(item["spare_part_id"]) not in spare_part_ids:
                return False
            if categories and str(item.get("category") or "") not in categories:
                return False
        return True

    def _line_values(
        self,
        session: Session,
        tenant_id: str,
        item: dict[str, Any],
        ranked: list[Any],
        inventory: list[dict[str, Any]],
        inventory_by_id: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        demand = Decimal(str(item["final_quantity"]))
        risks = self._risk_context(
            session,
            tenant_id,
            int(item["spare_part_id"]),
            ranked,
            inventory,
        )
        if not ranked:
            risks.insert(
                0,
                {
                    "code": "NO_ELIGIBLE_CANDIDATE",
                    "message": "no eligible inventory candidate",
                },
            )
            return {
                "recommended_balance_id": None,
                "recommended_lot_id": None,
                "recommended_serial_item_id": None,
                "demand_quantity": demand,
                "allocated_quantity": _ZERO,
                "gap_quantity": demand,
                "risks_json": risks,
                "manual_override_json": None,
                "expected_balance_version": None,
                "reservation_id": None,
                "result_json": None,
            }

        top = inventory_by_id[int(ranked[0].balance_id)]
        available = max(Decimal(str(top["available_quantity"])), _ZERO)
        allocated = min(demand, available)
        return {
            "recommended_balance_id": int(top["id"]),
            "recommended_lot_id": top.get("lot_id"),
            "recommended_serial_item_id": None,
            "demand_quantity": demand,
            "allocated_quantity": allocated,
            "gap_quantity": max(demand - allocated, _ZERO),
            "risks_json": risks,
            "manual_override_json": None,
            "expected_balance_version": int(top["version"]),
            "reservation_id": None,
            "result_json": None,
        }

    def _risk_context(
        self,
        session: Session,
        tenant_id: str,
        spare_part_id: int,
        ranked: list[Any],
        inventory: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        for alternate in ranked[1:]:
            risks.append(
                {
                    "code": "ALTERNATIVE_CANDIDATE",
                    "balance_id": int(alternate.balance_id),
                    "advisory_only": True,
                }
            )

        in_transit = sum(
            (
                Decimal(str(row["in_transit_quantity"]))
                for row in inventory
                if int(row["spare_part_id"]) == spare_part_id
            ),
            _ZERO,
        )
        if in_transit > _ZERO:
            risks.append(
                {
                    "code": "IN_TRANSIT_NOT_AVAILABLE",
                    "in_transit_quantity": format(in_transit, "f"),
                    "advisory_only": True,
                }
            )

        repair_count = session.scalar(
            select(SerializedItem.id)
            .where(
                SerializedItem.tenant_id == tenant_id,
                SerializedItem.spare_part_id == spare_part_id,
                SerializedItem.status.in_(_REPAIR_STATUSES),
            )
            .limit(1)
        )
        if repair_count is not None:
            risks.append(
                {
                    "code": "REPAIR_PIPELINE_NOT_AVAILABLE",
                    "advisory_only": True,
                }
            )
        return risks

    def _edit_cap(
        self,
        session: Session,
        actor: ActorContext,
        line: AllocationPlanLine,
    ) -> tuple[Decimal, dict[str, Any]]:
        if line.recommended_balance_id is None:
            return _ZERO, {"policy": "no recommended balance"}
        balance = session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == actor.tenant_id,
                InventoryBalance.id == line.recommended_balance_id,
            )
        )
        if balance is None:
            return _ZERO, {"policy": "recommended balance missing"}

        cap = min(line.demand_quantity, max(balance.available_quantity, _ZERO))
        policy = session.scalar(
            select(InventoryPolicy).where(
                InventoryPolicy.tenant_id == actor.tenant_id,
                InventoryPolicy.warehouse_id == balance.warehouse_id,
                InventoryPolicy.spare_part_id == line.spare_part_id,
            )
        )
        details: dict[str, Any] = {
            "balance_id": balance.id,
            "available_quantity": format(balance.available_quantity, "f"),
        }
        if policy is not None and policy.maximum_stock is not None:
            cap = min(cap, policy.maximum_stock)
            details["policy"] = {
                "id": policy.id,
                "maximum_stock": format(policy.maximum_stock, "f"),
            }
        else:
            details["policy"] = None
        return max(cap, _ZERO), details

    def _require_eligible_source(
        self,
        session: Session,
        actor: ActorContext,
        source_id: int,
    ) -> DemandList:
        source = session.scalar(
            select(DemandList).where(
                DemandList.tenant_id == actor.tenant_id,
                DemandList.id == source_id,
            )
        )
        if source is None or not self._source_is_eligible(source):
            error = ConflictError(
                "allocation source must be confirmed or current published",
                code="ALLOCATION_SOURCE_NOT_CURRENT",
                details={
                    "fact": "source",
                    "source_demand_list_id": source_id,
                    "regenerate": "/api/v1/demand-lists",
                },
            )
            error.request_id = actor.request_id
            raise error
        return source

    @classmethod
    def _source_is_eligible(cls, source: DemandList) -> bool:
        status = cls._enum_value(source.status)
        return status == "CONFIRMED" or (
            status == "PUBLISHED" and bool(source.is_current)
        )

    def _raise_source_conflict(
        self,
        actor: ActorContext,
        plan: AllocationPlan,
        *,
        actual_version: int | None,
    ) -> None:
        self._raise_conflict(
            actor,
            "allocation source changed after plan generation",
            code="ALLOCATION_SOURCE_NOT_CURRENT",
            details={
                "fact": "source",
                "source_demand_list_id": plan.source_demand_list_id,
                "expected_version": plan.source_demand_list_version,
                "actual_version": actual_version,
                "regenerate": self._regenerate_suggestion(plan.id),
            },
        )

    @staticmethod
    def _line_snapshot(line: AllocationPlanLine) -> dict[str, Any]:
        return {
            "id": line.id,
            "plan_id": line.plan_id,
            "demand_list_item_id": line.demand_list_item_id,
            "recommended_balance_id": line.recommended_balance_id,
            "demand_quantity": format(line.demand_quantity, "f"),
            "allocated_quantity": format(line.allocated_quantity, "f"),
            "gap_quantity": format(line.gap_quantity, "f"),
            "expected_balance_version": line.expected_balance_version,
            "manual_override": line.manual_override_json,
            "version": line.version,
        }

    def _plan_snapshot(
        self,
        session: Session,
        plan: AllocationPlan,
    ) -> dict[str, Any]:
        lines = self.repository.list_plan_lines(
            session,
            plan.tenant_id,
            plan.id,
        )
        return {
            "id": plan.id,
            "status": plan.status,
            "version": plan.version,
            "source_demand_list_id": plan.source_demand_list_id,
            "source_demand_list_version": plan.source_demand_list_version,
            "rule_id": plan.rule_id,
            "inventory_fingerprint": plan.inventory_fingerprint,
            "lines": [self._line_snapshot(line) for line in lines],
        }

    @staticmethod
    def _add_event(
        session: Session,
        actor: ActorContext,
        plan: AllocationPlan,
        *,
        event_type: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        response: dict[str, Any] | None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> AllocationPlanEvent:
        event = AllocationPlanEvent(
            tenant_id=actor.tenant_id,
            plan_id=plan.id,
            event_type=event_type,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            before_snapshot_json=(
                snapshot_service.normalize(before) if before is not None else None
            ),
            after_snapshot_json=(
                snapshot_service.normalize(after) if after is not None else None
            ),
            response_snapshot_json=(
                snapshot_service.normalize(response) if response is not None else None
            ),
            error_code=None,
            occurred_at=datetime.now(timezone.utc),
        )
        session.add(event)
        return event

    @staticmethod
    def _normalize_idempotency_key(actor: ActorContext, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            error = BusinessValidationError(
                "idempotency key is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
            error.request_id = actor.request_id
            raise error
        if len(normalized) > 128:
            error = BusinessValidationError(
                "idempotency key is too long",
                code="IDEMPOTENCY_KEY_INVALID",
            )
            error.request_id = actor.request_id
            raise error
        return normalized

    @staticmethod
    def _require_contributor(actor: ActorContext) -> None:
        if _ROLE_RANK[actor.role] < _ROLE_RANK[MaintenanceRole.CONTRIBUTOR]:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.CONTRIBUTOR.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _require_plan_version(
        actor: ActorContext,
        plan: AllocationPlan,
        expected_version: int,
    ) -> None:
        if plan.version != expected_version:
            AllocationPlanService._raise_conflict(
                actor,
                "allocation plan version conflict",
                code="ALLOCATION_PLAN_VERSION_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": plan.version,
                },
            )

    @staticmethod
    def _regenerate_suggestion(plan_id: int) -> str:
        return f"/api/v1/allocations/plans/{plan_id}/regenerate"

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _raise_not_found(
        actor: ActorContext,
        resource: str,
        identifier: int,
    ) -> None:
        error = NotFoundError(resource, identifier)
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _raise_conflict(
        actor: ActorContext,
        message: str,
        *,
        code: str,
        details: Any | None = None,
    ) -> None:
        error = ConflictError(message, code=code, details=details)
        error.request_id = actor.request_id
        raise error


allocation_plan_service = AllocationPlanService()
