from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
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
    AllocationPlanActionResult,
    AllocationPlanConfirmCommand,
    AllocationPlanExecuteCommand,
    AllocationPlanExecutionLineResult,
    AllocationPlanExecutionResult,
    AllocationPlanLineEditCommand,
    AllocationPlanLineRead,
    AllocationPlanPreviewCommand,
    AllocationPlanRead,
    AllocationPlanRegenerateCommand,
    AllocationPlanRegenerationResult,
    AllocationPlanSummaryRead,
    AllocationPlanVoidCommand,
)
from app.schemas.inventory_ledger import MAX_INVENTORY_QUANTITY
from app.schemas.inventory_reservation import ReserveCommand
from app.security.actor import ActorContext, MaintenanceRole
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_scoring import rank_candidates
from app.services.allocation_simulation_service import AllocationSimulationService
from app.services.inventory_reservation_service import InventoryReservationService
from app.services.snapshot_service import snapshot_service

_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_ZERO = Decimal("0")
_INVENTORY_QUANTUM = Decimal("0.0001")
_ONE_INVENTORY_UNIT = Decimal("1.0000")
_REPAIR_STATUSES = {"AWAITING_REPAIR", "IN_REPAIR"}
_EXECUTION_TERMINAL_EVENTS = (
    "EXECUTION_COMPLETED",
    "EXECUTION_PARTIALLY_COMPLETED",
    "EXECUTION_FAILED",
)
_EXPECTED_INVENTORY_LINE_CODES = frozenset(
    {
        "INSUFFICIENT_AVAILABLE_INVENTORY",
        "INVENTORY_VERSION_CONFLICT",
        "INVENTORY_REQUIRED_BALANCE_NOT_ELIGIBLE",
        "INVENTORY_SERIAL_SELECTION_REQUIRED",
        "INVENTORY_SERIAL_SELECTION_CONFLICT",
        "INVENTORY_SERIAL_QUANTITY_INVALID",
        "INVENTORY_STATE_CONFLICT",
        "INVENTORY_STATE_TARGET_MISMATCH",
        "INVENTORY_ALLOCATION_EXCEEDS_ON_HAND",
        "FEFO_SELECTION_INVALID",
        "LOT_EXPIRED",
        "LOT_FROZEN",
        "LOT_QUARANTINED",
        "SERIAL_STATE_CONFLICT",
        "RESERVATION_EXPIRED",
        "RESOURCE_CONFLICT",
    }
)


class AllocationPlanService:
    def __init__(
        self,
        *,
        repository: AllocationRepository | None = None,
        reservation_service: InventoryReservationService | None = None,
    ) -> None:
        self.repository = repository or AllocationRepository()
        self.reservation_service = reservation_service or InventoryReservationService()
        self._snapshot_helper = AllocationSimulationService()

    def create(
        self,
        session: Session,
        actor: ActorContext,
        source_demand_list_id: int,
        *,
        idempotency_key: str,
        expected_source_version: int | None = None,
    ) -> AllocationPlan:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {
                "source_demand_list_id": int(source_demand_list_id),
                "expected_source_version": expected_source_version,
            }
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
        if (
            expected_source_version is not None
            and source.version != expected_source_version
        ):
            self._raise_conflict(
                actor,
                "allocation source version conflict",
                code="ALLOCATION_SOURCE_NOT_CURRENT",
                details={
                    "fact": "source",
                    "source_demand_list_id": source.id,
                    "expected_version": expected_source_version,
                    "actual_version": source.version,
                    "retryable": False,
                    "suggested_action": "select_or_publish_current_source",
                },
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

    # PLAN05_4D_TASK6_GREEN_C: viewer-safe plan reads.
    def list_read(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        source_demand_list_id: int | None = None,
        rule_id: int | None = None,
    ) -> tuple[list[AllocationPlanSummaryRead], int]:
        plans, total = self.repository.list_plans_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            source_demand_list_id=source_demand_list_id,
            rule_id=rule_id,
        )
        return [self._plan_summary_read(plan) for plan in plans], total

    def get_read(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
    ) -> AllocationPlanRead:
        plan = self.repository.get_plan(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)
        return self._plan_read(session, plan)

    def void(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
        *,
        command: AllocationPlanVoidCommand,
    ) -> AllocationPlanActionResult:
        self._require_contributor(actor)
        plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)

        if plan.status == "VOIDED":
            existing = self._latest_plan_event(
                session,
                actor.tenant_id,
                plan.id,
                "VOIDED",
            )
            if existing is None or not isinstance(
                existing.response_snapshot_json,
                dict,
            ):
                self._raise_conflict(
                    actor,
                    "allocation void response is unavailable",
                    code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                    details={"retryable": False},
                )
            return AllocationPlanActionResult.model_validate(
                existing.response_snapshot_json
            ).model_copy(deep=True)

        self._require_plan_version(actor, plan, command.expected_version)
        if plan.status not in {"DRAFT", "PREVIEWED", "CONFIRMED"}:
            self._raise_conflict(
                actor,
                "allocation plan cannot be voided in its current state",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={
                    "status": plan.status,
                    "retryable": False,
                },
            )

        before = self._plan_snapshot(session, plan)
        plan.status = "VOIDED"
        plan.version += 1
        session.flush()
        event = self._add_event(
            session,
            actor,
            plan,
            event_type="VOIDED",
            before=before,
            after=self._plan_snapshot(session, plan),
            response=None,
        )
        session.flush()
        result = AllocationPlanActionResult(
            plan_id=plan.id,
            event_id=event.id,
            status=plan.status,
            version=plan.version,
        )
        event.response_snapshot_json = snapshot_service.normalize(
            result.model_dump(mode="json")
        )
        session.flush()
        return result

    def regenerate(
        self,
        session: Session,
        actor: ActorContext,
        source_plan_id: int,
        *,
        command: AllocationPlanRegenerateCommand,
        idempotency_key: str,
    ) -> AllocationPlanRegenerationResult:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {
                "action": "REGENERATE",
                "source_plan_id": int(source_plan_id),
                "command": command.model_dump(mode="json"),
            }
        )

        existing = self._find_action_event(
            session,
            actor.tenant_id,
            source_plan_id,
            event_types=("PLAN_REGENERATED",),
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay_action_event(
                actor,
                existing,
                request_hash=request_hash,
                result_type=AllocationPlanRegenerationResult,
            )

        source_plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            source_plan_id,
        )
        if source_plan is None:
            self._raise_not_found(
                actor,
                "allocation_plan",
                source_plan_id,
            )

        existing = self._find_action_event(
            session,
            actor.tenant_id,
            source_plan.id,
            event_types=("PLAN_REGENERATED",),
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay_action_event(
                actor,
                existing,
                request_hash=request_hash,
                result_type=AllocationPlanRegenerationResult,
            )

        self._require_plan_version(
            actor,
            source_plan,
            command.expected_version,
        )
        source = self._resolve_regeneration_source(
            session,
            actor,
            source_plan,
        )
        before = self._plan_snapshot(session, source_plan)
        new_plan = self.create(
            session,
            actor,
            source.id,
            idempotency_key=self._regeneration_plan_key(
                source_plan.id,
                clean_key,
            ),
            expected_source_version=source.version,
        )

        created = self.repository.get_plan_created_event(
            session,
            actor.tenant_id,
            new_plan.id,
        )
        if created is not None:
            created_after = dict(created.after_snapshot_json or {})
            created_after["regenerated_from_plan_id"] = source_plan.id
            created.after_snapshot_json = snapshot_service.normalize(
                created_after
            )

        event = self._add_event(
            session,
            actor,
            source_plan,
            event_type="PLAN_REGENERATED",
            idempotency_key=clean_key,
            request_hash=request_hash,
            before=before,
            after={
                "source_plan": before,
                "new_plan_id": new_plan.id,
                "source_demand_list_id": source.id,
                "source_demand_list_version": source.version,
            },
            response=None,
        )
        session.flush()
        result = AllocationPlanRegenerationResult(
            source_plan_id=source_plan.id,
            new_plan_id=new_plan.id,
            event_id=event.id,
            status=new_plan.status,
            version=new_plan.version,
        )
        event.response_snapshot_json = snapshot_service.normalize(
            result.model_dump(mode="json")
        )
        session.flush()
        return result

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

    def confirm(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
        *,
        command: AllocationPlanConfirmCommand,
        idempotency_key: str,
    ) -> AllocationPlanActionResult:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {
                "action": "CONFIRM",
                "plan_id": int(plan_id),
                "expected_version": command.expected_version,
            }
        )
        plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)

        existing = self._find_action_event(
            session,
            actor.tenant_id,
            plan.id,
            event_types=("CONFIRMED",),
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay_action_event(
                actor,
                existing,
                request_hash=request_hash,
                result_type=AllocationPlanActionResult,
            )

        if plan.status != "PREVIEWED":
            self._raise_conflict(
                actor,
                "allocation plan can only be confirmed from PREVIEWED",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={"status": plan.status},
            )
        self._require_plan_version(actor, plan, command.expected_version)

        latest_preview = self._latest_plan_event(
            session,
            actor.tenant_id,
            plan.id,
            "PREVIEWED",
        )
        preview_response = (
            latest_preview.response_snapshot_json
            if latest_preview is not None
            else None
        )
        preview_version = (
            preview_response.get("version")
            if isinstance(preview_response, dict)
            else None
        )
        if preview_version != plan.version:
            self._raise_conflict(
                actor,
                "allocation plan must be previewed again before confirmation",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={
                    "fact": "preview",
                    "latest_preview_event_id": (
                        latest_preview.id if latest_preview is not None else None
                    ),
                    "preview_version": preview_version,
                    "plan_version": plan.version,
                    "suggested_action": "preview_again",
                },
            )

        lines = self._current_plan_lines(
            session,
            actor.tenant_id,
            plan.id,
        )
        for line in lines:
            self._validate_confirm_quantity(actor, plan, line)

        before = self._plan_snapshot(session, plan)
        plan.status = "CONFIRMED"
        plan.version += 1
        session.flush()
        after = {
            "plan": self._plan_snapshot(session, plan),
            "confirmed_preview_event_id": latest_preview.id,
            "confirmed_preview_snapshot": {
                "before": latest_preview.before_snapshot_json,
                "after": latest_preview.after_snapshot_json,
                "response": latest_preview.response_snapshot_json,
            },
        }
        event = self._add_event(
            session,
            actor,
            plan,
            event_type="CONFIRMED",
            idempotency_key=clean_key,
            request_hash=request_hash,
            before=before,
            after=after,
            response=None,
        )
        session.flush()
        result = AllocationPlanActionResult(
            plan_id=plan.id,
            event_id=event.id,
            status=plan.status,
            version=plan.version,
        )
        event.response_snapshot_json = snapshot_service.normalize(
            result.model_dump(mode="json")
        )
        session.flush()
        return result

    def execute(
        self,
        session: Session,
        actor: ActorContext,
        plan_id: int,
        *,
        command: AllocationPlanExecuteCommand,
        idempotency_key: str,
    ) -> AllocationPlanExecutionResult:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {
                "action": "EXECUTE",
                "plan_id": int(plan_id),
                "expected_version": command.expected_version,
            }
        )
        plan = self.repository.get_plan_for_update(
            session,
            actor.tenant_id,
            plan_id,
        )
        if plan is None:
            self._raise_not_found(actor, "allocation_plan", plan_id)

        terminal = self._find_action_event(
            session,
            actor.tenant_id,
            plan.id,
            event_types=_EXECUTION_TERMINAL_EVENTS,
            idempotency_key=clean_key,
        )
        if terminal is not None:
            return self._replay_action_event(
                actor,
                terminal,
                request_hash=request_hash,
                result_type=AllocationPlanExecutionResult,
            )

        if plan.status != "CONFIRMED":
            self._raise_conflict(
                actor,
                "allocation plan cannot start a new execution in its current state",
                code="ALLOCATION_PLAN_STATE_CONFLICT",
                details={
                    "status": plan.status,
                    "retryable": False,
                    "suggested_action": "regenerate",
                },
            )
        self._require_plan_version(actor, plan, command.expected_version)

        source = session.scalar(
            select(DemandList)
            .where(
                DemandList.tenant_id == actor.tenant_id,
                DemandList.id == plan.source_demand_list_id,
            )
            .with_for_update()
        )
        if (
            source is None
            or self._enum_value(source.status) != "PUBLISHED"
            or not bool(source.is_current)
            or source.version != plan.source_demand_list_version
        ):
            self._raise_conflict(
                actor,
                "allocation source is no longer the frozen current published version",
                code="ALLOCATION_SOURCE_NOT_CURRENT",
                details={
                    "fact": "source",
                    "source_demand_list_id": plan.source_demand_list_id,
                    "expected_version": plan.source_demand_list_version,
                    "actual_version": source.version if source is not None else None,
                    "retryable": False,
                    "suggested_action": "regenerate",
                },
            )

        rule = self.repository.get_rule_for_update(
            session,
            actor.tenant_id,
            plan.rule_id,
        )
        created = self.repository.get_plan_created_event(
            session,
            actor.tenant_id,
            plan.id,
        )
        frozen_rule_version = None
        if created is not None:
            created_snapshot = created.after_snapshot_json or {}
            frozen_rule_version = (created_snapshot.get("rule") or {}).get("version")
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
                    "actual_version": rule.version if rule is not None else None,
                    "retryable": False,
                    "suggested_action": "regenerate",
                },
            )

        before_execution = self._plan_snapshot(session, plan)
        execution_as_of = datetime.now(timezone.utc).date()
        plan.status = "EXECUTING"
        plan.version += 1
        session.flush()
        start_event = self._add_event(
            session,
            actor,
            plan,
            event_type="EXECUTION_STARTED",
            idempotency_key=clean_key,
            request_hash=request_hash,
            before=before_execution,
            after={
                "plan": self._plan_snapshot(session, plan),
                "execution_as_of": execution_as_of.isoformat(),
            },
            response={
                "plan_id": plan.id,
                "status": plan.status,
                "version": plan.version,
                "execution_as_of": execution_as_of.isoformat(),
            },
        )
        session.flush()
        execution_id = start_event.id

        lines = self._current_plan_lines(
            session,
            actor.tenant_id,
            plan.id,
        )
        ordered_lines = sorted(
            lines,
            key=lambda line: (
                line.recommended_balance_id is None,
                line.recommended_balance_id or 0,
                line.id,
            ),
        )
        owned_versions: dict[int, int] = {}
        line_results: list[AllocationPlanExecutionLineResult] = []

        for line in ordered_lines:
            if line.allocated_quantity <= _ZERO:
                result = AllocationPlanExecutionLineResult(
                    line_id=line.id,
                    outcome="GAP_RETAINED",
                    retryable=False,
                )
                self._store_line_execution_result(
                    session,
                    actor,
                    plan,
                    line,
                    result,
                    execution_id=execution_id,
                    event_type="LINE_EXECUTION_SKIPPED",
                )
                line_results.append(result)
                continue

            if (
                line.recommended_balance_id is None
                or line.expected_balance_version is None
            ):
                result = self._allocation_line_conflict_result(
                    line,
                    cause_code="INVENTORY_REQUIRED_BALANCE_NOT_ELIGIBLE",
                    cause_details={
                        "fact": "recommended_balance",
                        "retryable": False,
                    },
                )
                self._store_line_execution_result(
                    session,
                    actor,
                    plan,
                    line,
                    result,
                    execution_id=execution_id,
                    event_type="LINE_EXECUTION_CONFLICT",
                    error_code="ALLOCATION_INVENTORY_CONFLICT",
                )
                line_results.append(result)
                continue

            balance_id = line.recommended_balance_id
            current_balance = session.scalar(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == actor.tenant_id,
                    InventoryBalance.id == balance_id,
                )
            )
            expected_version = owned_versions.get(
                balance_id,
                line.expected_balance_version,
            )
            precheck_details: dict[str, Any] | None = None
            precheck_code: str | None = None
            if current_balance is None:
                precheck_code = "INVENTORY_REQUIRED_BALANCE_NOT_ELIGIBLE"
                precheck_details = {"retryable": True}
            elif current_balance.spare_part_id != line.spare_part_id:
                precheck_code = "INVENTORY_REQUIRED_BALANCE_NOT_ELIGIBLE"
                precheck_details = {
                    "actual_spare_part_id": current_balance.spare_part_id,
                    "retryable": False,
                }
            elif (
                line.recommended_lot_id is not None
                and current_balance.lot_id != line.recommended_lot_id
            ):
                precheck_code = "INVENTORY_REQUIRED_BALANCE_NOT_ELIGIBLE"
                precheck_details = {
                    "expected_lot_id": line.recommended_lot_id,
                    "actual_lot_id": current_balance.lot_id,
                    "retryable": False,
                }
            elif current_balance.version != expected_version:
                precheck_code = "INVENTORY_VERSION_CONFLICT"
                precheck_details = {
                    "expected_version": expected_version,
                    "actual_version": current_balance.version,
                    "retryable": True,
                }

            if precheck_code is not None:
                result = self._allocation_line_conflict_result(
                    line,
                    cause_code=precheck_code,
                    cause_details=precheck_details,
                    expected_version=expected_version,
                )
                self._store_line_execution_result(
                    session,
                    actor,
                    plan,
                    line,
                    result,
                    execution_id=execution_id,
                    event_type="LINE_EXECUTION_CONFLICT",
                    error_code="ALLOCATION_INVENTORY_CONFLICT",
                )
                line_results.append(result)
                continue

            quantity = line.allocated_quantity.quantize(_INVENTORY_QUANTUM)
            reserve_command = ReserveCommand(
                owner_type="ALLOCATION_PLAN",
                owner_id=str(plan.id),
                spare_part_id=line.spare_part_id,
                warehouse_id=current_balance.warehouse_id,
                requested_quantity=quantity,
                allow_partial=False,
                expected_balance_versions={balance_id: expected_version},
                as_of=execution_as_of,
                serial_item_id=line.recommended_serial_item_id,
                expires_at=None,
            )
            allocation_context = {
                "allocation_plan_id": plan.id,
                "allocation_plan_line_id": line.id,
                "allocation_execution_id": execution_id,
                "execution_as_of": execution_as_of.isoformat(),
                "source_demand_list_id": plan.source_demand_list_id,
                "rule_id": plan.rule_id,
            }
            child_key = (
                f"allocation-plan:{plan.id}:line:{line.id}:execute:{execution_id}"
            )
            try:
                with session.begin_nested():
                    reservation = self.reservation_service.reserve_for_allocation_line(
                        session,
                        actor,
                        command=reserve_command,
                        required_balance_id=balance_id,
                        required_serial_item_id=line.recommended_serial_item_id,
                        allocation_context=allocation_context,
                        idempotency_key=child_key,
                    )
                    result = AllocationPlanExecutionLineResult(
                        line_id=line.id,
                        outcome="RESERVED",
                        reservation_id=reservation.id,
                        retryable=False,
                        details={
                            "balance_id": balance_id,
                            "expected_version": expected_version,
                            "requested_quantity": format(
                                reservation.requested_quantity, ".4f"
                            ),
                            "reserved_quantity": format(
                                reservation.reserved_quantity, ".4f"
                            ),
                            "unfilled_quantity": format(
                                reservation.unfilled_quantity, ".4f"
                            ),
                            "child_idempotency_key": child_key,
                        },
                    )
                    self._store_line_execution_result(
                        session,
                        actor,
                        plan,
                        line,
                        result,
                        execution_id=execution_id,
                        event_type="LINE_EXECUTED",
                    )
            except AppException as exc:
                if not self._is_expected_inventory_line_conflict(exc):
                    raise
                result = self._allocation_line_conflict_result(
                    line,
                    cause_code=exc.code,
                    cause_details=exc.details,
                    expected_version=expected_version,
                )
                self._store_line_execution_result(
                    session,
                    actor,
                    plan,
                    line,
                    result,
                    execution_id=execution_id,
                    event_type="LINE_EXECUTION_CONFLICT",
                    error_code="ALLOCATION_INVENTORY_CONFLICT",
                )

            line_results.append(result)
            if result.outcome == "RESERVED":
                current_after = self._current_balance(
                    session,
                    actor.tenant_id,
                    balance_id,
                )
                owned_versions[balance_id] = (
                    current_after.version
                    if current_after is not None
                    else expected_version
                )

        reserved_count = sum(
            result.outcome == "RESERVED"
            for result in line_results
        )
        conflict_count = sum(
            result.outcome == "CONFLICT"
            for result in line_results
        )
        if conflict_count == 0:
            terminal_status = "COMPLETED"
            terminal_event_type = "EXECUTION_COMPLETED"
        elif reserved_count > 0:
            terminal_status = "PARTIALLY_COMPLETED"
            terminal_event_type = "EXECUTION_PARTIALLY_COMPLETED"
        else:
            terminal_status = "FAILED"
            terminal_event_type = "EXECUTION_FAILED"

        before_terminal = self._plan_snapshot(session, plan)
        plan.status = terminal_status
        plan.version += 1
        session.flush()
        ordered_results = tuple(
            sorted(line_results, key=lambda result: result.line_id)
        )
        response = AllocationPlanExecutionResult(
            plan_id=plan.id,
            execution_id=execution_id,
            execution_as_of=execution_as_of,
            status=plan.status,
            version=plan.version,
            line_results=ordered_results,
        )
        self._add_event(
            session,
            actor,
            plan,
            event_type=terminal_event_type,
            idempotency_key=clean_key,
            request_hash=request_hash,
            before=before_terminal,
            after={
                "plan": self._plan_snapshot(session, plan),
                "execution_id": execution_id,
                "execution_as_of": execution_as_of.isoformat(),
            },
            response=response.model_dump(mode="json"),
        )
        session.flush()
        return response

    @staticmethod
    def _current_balance(
        session: Session,
        tenant_id: str,
        balance_id: int,
    ) -> InventoryBalance | None:
        return session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id == balance_id,
            )
        )

    @staticmethod
    def _current_plan_lines(
        session: Session,
        tenant_id: str,
        plan_id: int,
    ) -> list[AllocationPlanLine]:
        return list(
            session.scalars(
                select(AllocationPlanLine)
                .where(
                    AllocationPlanLine.tenant_id == tenant_id,
                    AllocationPlanLine.plan_id == plan_id,
                )
                .order_by(AllocationPlanLine.id.asc())
            ).all()
        )

    @staticmethod
    def _latest_plan_event(
        session: Session,
        tenant_id: str,
        plan_id: int,
        event_type: str,
    ) -> AllocationPlanEvent | None:
        return session.scalar(
            select(AllocationPlanEvent)
            .where(
                AllocationPlanEvent.tenant_id == tenant_id,
                AllocationPlanEvent.plan_id == plan_id,
                AllocationPlanEvent.event_type == event_type,
            )
            .order_by(AllocationPlanEvent.id.desc())
            .limit(1)
        )

    @staticmethod
    def _find_action_event(
        session: Session,
        tenant_id: str,
        plan_id: int,
        *,
        event_types: tuple[str, ...],
        idempotency_key: str,
    ) -> AllocationPlanEvent | None:
        return session.scalar(
            select(AllocationPlanEvent)
            .where(
                AllocationPlanEvent.tenant_id == tenant_id,
                AllocationPlanEvent.plan_id == plan_id,
                AllocationPlanEvent.event_type.in_(event_types),
                AllocationPlanEvent.idempotency_key == idempotency_key,
            )
            .order_by(AllocationPlanEvent.id.desc())
            .limit(1)
        )

    @staticmethod
    def _replay_action_event(
        actor: ActorContext,
        event: AllocationPlanEvent,
        *,
        request_hash: str,
        result_type: Any,
    ) -> Any:
        if event.request_hash != request_hash:
            AllocationPlanService._raise_conflict(
                actor,
                "allocation action idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "idempotency_key": event.idempotency_key,
                    "retryable": False,
                },
            )
        snapshot = event.response_snapshot_json
        if not isinstance(snapshot, dict):
            AllocationPlanService._raise_conflict(
                actor,
                "allocation idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )
        return result_type.model_validate(snapshot).model_copy(deep=True)

    @staticmethod
    def _validate_confirm_quantity(
        actor: ActorContext,
        plan: AllocationPlan,
        line: AllocationPlanLine,
    ) -> None:
        quantity = line.allocated_quantity
        try:
            quantized = quantity.quantize(_INVENTORY_QUANTUM)
        except InvalidOperation:
            quantized = None
        if (
            not quantity.is_finite()
            or quantized is None
            or quantity != quantized
        ):
            AllocationPlanService._raise_conflict(
                actor,
                "allocation quantity is not exact at inventory precision",
                code="ALLOCATION_INVENTORY_CONFLICT",
                details={
                    "fact": "quantity_precision",
                    "line_id": line.id,
                    "quantity": format(quantity, "f"),
                    "retryable": False,
                    "suggested_action": "edit_and_preview_again",
                },
            )
        if abs(quantized) > MAX_INVENTORY_QUANTITY:
            AllocationPlanService._raise_conflict(
                actor,
                "allocation quantity is outside inventory Numeric(18,4) range",
                code="ALLOCATION_INVENTORY_CONFLICT",
                details={
                    "fact": "quantity_range",
                    "line_id": line.id,
                    "quantity": format(quantity, "f"),
                    "retryable": False,
                    "suggested_action": "edit_and_preview_again",
                },
            )
        if (
            line.recommended_serial_item_id is not None
            and quantity > _ZERO
            and quantized != _ONE_INVENTORY_UNIT
        ):
            AllocationPlanService._raise_conflict(
                actor,
                "serialized allocation quantity must equal one",
                code="ALLOCATION_INVENTORY_CONFLICT",
                details={
                    "fact": "serial_quantity",
                    "line_id": line.id,
                    "serial_item_id": line.recommended_serial_item_id,
                    "quantity": format(quantity, "f"),
                    "retryable": False,
                    "suggested_action": "edit_and_preview_again",
                },
            )

    @staticmethod
    def _is_expected_inventory_line_conflict(exc: AppException) -> bool:
        if exc.code in {"IDEMPOTENCY_KEY_REUSED", "IDEMPOTENT_RESPONSE_UNAVAILABLE"}:
            return False
        return exc.code in _EXPECTED_INVENTORY_LINE_CODES

    @staticmethod
    def _allocation_line_conflict_result(
        line: AllocationPlanLine,
        *,
        cause_code: str,
        cause_details: Any | None,
        expected_version: int | None = None,
    ) -> AllocationPlanExecutionLineResult:
        details: dict[str, Any] = {
            "line_id": line.id,
            "balance_id": line.recommended_balance_id,
            "suggested_action": "regenerate",
            "expected_version": (
                expected_version
                if expected_version is not None
                else line.expected_balance_version
            ),
        }
        cause_retryable = None
        if isinstance(cause_details, dict):
            cause_copy = dict(cause_details)
            cause_retryable = cause_copy.pop("retryable", None)
            details.update(cause_copy)
        elif cause_details is not None:
            details["cause_details"] = cause_details
        if cause_retryable is not None:
            details["cause_retryable"] = bool(cause_retryable)
        return AllocationPlanExecutionLineResult(
            line_id=line.id,
            outcome="CONFLICT",
            error_code="ALLOCATION_INVENTORY_CONFLICT",
            cause_code=cause_code,
            retryable=False,
            suggested_action="regenerate",
            details=details,
        )

    def _store_line_execution_result(
        self,
        session: Session,
        actor: ActorContext,
        plan: AllocationPlan,
        line: AllocationPlanLine,
        result: AllocationPlanExecutionLineResult,
        *,
        execution_id: int,
        event_type: str,
        error_code: str | None = None,
    ) -> None:
        before = self._line_snapshot(line)
        if result.reservation_id is not None:
            line.reservation_id = result.reservation_id
        stored_result = result.model_dump(mode="json")
        stored_result["execution_id"] = execution_id
        line.result_json = stored_result
        line.version += 1
        session.flush()
        self._add_event(
            session,
            actor,
            plan,
            event_type=event_type,
            before=before,
            after={
                "line": self._line_snapshot(line),
                "reservation_id": line.reservation_id,
                "result": stored_result,
            },
            response=stored_result,
            error_code=error_code,
        )
        session.flush()

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

    # PLAN05_4D_TASK6_GREEN_C: public plan read mapping and regeneration.
    @staticmethod
    def _plan_summary_read(
        plan: AllocationPlan,
    ) -> AllocationPlanSummaryRead:
        return AllocationPlanSummaryRead(
            id=plan.id,
            source_demand_list_id=plan.source_demand_list_id,
            source_demand_list_version=plan.source_demand_list_version,
            rule_id=plan.rule_id,
            inventory_fingerprint=plan.inventory_fingerprint,
            status=plan.status,
            version=plan.version,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    @staticmethod
    def _plan_line_read(
        line: AllocationPlanLine,
    ) -> AllocationPlanLineRead:
        return AllocationPlanLineRead(
            id=line.id,
            plan_id=line.plan_id,
            demand_list_item_id=line.demand_list_item_id,
            spare_part_id=line.spare_part_id,
            recommended_balance_id=line.recommended_balance_id,
            recommended_lot_id=line.recommended_lot_id,
            recommended_serial_item_id=line.recommended_serial_item_id,
            demand_quantity=line.demand_quantity,
            allocated_quantity=line.allocated_quantity,
            gap_quantity=line.gap_quantity,
            risks=list(line.risks_json or []),
            manual_override=line.manual_override_json,
            expected_balance_version=line.expected_balance_version,
            reservation_id=line.reservation_id,
            result=line.result_json,
            version=line.version,
        )

    def _plan_read(
        self,
        session: Session,
        plan: AllocationPlan,
    ) -> AllocationPlanRead:
        lines = self.repository.list_plan_lines(
            session,
            plan.tenant_id,
            plan.id,
        )
        summary = self._plan_summary_read(plan)
        return AllocationPlanRead(
            **summary.model_dump(),
            lines=tuple(self._plan_line_read(line) for line in lines),
        )

    def _resolve_regeneration_source(
        self,
        session: Session,
        actor: ActorContext,
        source_plan: AllocationPlan,
    ) -> DemandList:
        old_source = session.scalar(
            select(DemandList).where(
                DemandList.tenant_id == actor.tenant_id,
                DemandList.id == source_plan.source_demand_list_id,
            )
        )
        if old_source is not None and self._source_is_eligible(old_source):
            return old_source

        if old_source is not None:
            current = session.scalar(
                select(DemandList)
                .where(
                    DemandList.tenant_id == actor.tenant_id,
                    DemandList.lineage_id == old_source.lineage_id,
                    DemandList.status == "PUBLISHED",
                    DemandList.is_current.is_(True),
                )
                .order_by(
                    DemandList.version_number.desc(),
                    DemandList.id.desc(),
                )
                .limit(1)
            )
            if current is not None and self._source_is_eligible(current):
                return current

        self._raise_conflict(
            actor,
            "no eligible allocation source is available for regeneration",
            code="ALLOCATION_SOURCE_NOT_CURRENT",
            details={
                "fact": "source",
                "source_demand_list_id": source_plan.source_demand_list_id,
                "retryable": False,
                "suggested_action": "select_or_publish_current_source",
                "regenerate": "/api/v1/demand-lists",
            },
        )
        raise AssertionError("unreachable")

    @staticmethod
    def _regeneration_plan_key(
        source_plan_id: int,
        idempotency_key: str,
    ) -> str:
        digest = snapshot_service.canonical_hash(
            {
                "action": "REGENERATED_PLAN_CREATE",
                "source_plan_id": source_plan_id,
                "idempotency_key": idempotency_key,
            }
        )
        return f"regen:{source_plan_id}:{digest}"

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
            "recommended_lot_id": line.recommended_lot_id,
            "recommended_serial_item_id": line.recommended_serial_item_id,
            "demand_quantity": format(line.demand_quantity, "f"),
            "allocated_quantity": format(line.allocated_quantity, "f"),
            "gap_quantity": format(line.gap_quantity, "f"),
            "expected_balance_version": line.expected_balance_version,
            "reservation_id": line.reservation_id,
            "result": line.result_json,
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
        error_code: str | None = None,
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
            error_code=error_code,
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
