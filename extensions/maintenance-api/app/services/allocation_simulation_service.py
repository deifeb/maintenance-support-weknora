from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.db.session import SessionLocal
from app.models import (
    AllocationRuleVersion,
    AllocationSimulation,
    AllocationSimulationResult,
    DemandList,
    DemandListItem,
    InventoryBalance,
    InventoryLot,
    SparePart,
    WarehouseLocation,
)
from app.schemas.allocation import (
    AllocationSimulationProgressRead,
    AllocationSimulationResultsSummaryRead,
    AllocationSimulationSummaryRead,
    RuleSnapshot,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.allocation_rule_service import AllocationRuleService
from app.services.allocation_scoring import RankedCandidate, rank_candidates
from app.services.snapshot_service import snapshot_service

_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_ZERO = Decimal("0")
_CRITICALITY = {
    "CRITICAL": Decimal("4"),
    "HIGH": Decimal("3"),
    "MEDIUM": Decimal("2"),
    "LOW": Decimal("1"),
}
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(password|secret|token|api[_-]?key)\s*=\s*[^,\s;]+"
)


@dataclass(frozen=True, slots=True)
class SimulationSummary:
    id: int
    tenant_id: str
    status: str
    version: int
    rule_hash: str
    progress: AllocationSimulationProgressRead
    blockers: list[dict[str, Any]]
    results_summary: AllocationSimulationResultsSummaryRead
    high_priority_regression: Decimal
    completed_at: datetime | None
    error_code: str | None
    error_summary: str | None


@dataclass(frozen=True, slots=True)
class _SimulationCandidate:
    balance_id: int
    metrics: dict[str, Decimal]
    warehouse_priority: int
    location_priority: int
    expiry_date: date | None
    lot_code: str
    frozen: bool
    expired: bool
    available: bool


class AllocationSimulationService:
    def submit(
        self,
        session: Session,
        actor: ActorContext,
        *,
        candidate_rule_id: int,
        baseline_rule_id: int | None,
        source_demand_list_id: int,
        sample_ref: str | None,
        idempotency_key: str,
        expected_rule_version: int | None = None,
    ) -> AllocationSimulation:
        self._require_contributor(actor)
        clean_key = self._normalize_idempotency_key(actor, idempotency_key)
        request_hash = snapshot_service.canonical_hash(
            {
                "candidate_rule_id": candidate_rule_id,
                "expected_rule_version": expected_rule_version,
                "baseline_rule_id": baseline_rule_id,
                "source_demand_list_id": source_demand_list_id,
                "sample_ref": sample_ref,
            }
        )

        existing = session.scalar(
            select(AllocationSimulation).where(
                AllocationSimulation.tenant_id == actor.tenant_id,
                AllocationSimulation.idempotency_key == clean_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                self._raise_conflict(
                    actor,
                    "allocation simulation idempotency key was reused",
                    code="IDEMPOTENCY_KEY_REUSED",
                    details={"idempotency_key": clean_key},
                )
            return existing

        candidate_rule = self._require_rule(
            session,
            actor,
            candidate_rule_id,
        )
        if (
            expected_rule_version is not None
            and candidate_rule.version != expected_rule_version
        ):
            self._raise_conflict(
                actor,
                "allocation rule version conflict",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={
                    "expected_version": expected_rule_version,
                    "actual_version": candidate_rule.version,
                    "retryable": False,
                },
            )

        baseline_rule = (
            self._require_rule(session, actor, baseline_rule_id)
            if baseline_rule_id is not None
            else None
        )
        demand_list = self._require_demand_list(
            session,
            actor,
            source_demand_list_id,
        )

        inventory = self._inventory_state(session, actor.tenant_id)
        input_snapshot = {
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "as_of_date": datetime.now(timezone.utc).date().isoformat(),
            "sample_ref": sample_ref,
            "candidate_rule": self._rule_snapshot(candidate_rule),
            "baseline_rule": (
                self._rule_snapshot(baseline_rule)
                if baseline_rule is not None
                else None
            ),
            "demand_list": self._demand_snapshot(
                session,
                actor.tenant_id,
                demand_list,
            ),
            "inventory": inventory,
        }
        fingerprint = snapshot_service.canonical_hash(inventory)

        simulation = AllocationSimulation(
            tenant_id=actor.tenant_id,
            candidate_rule_id=candidate_rule.id,
            baseline_rule_id=(
                baseline_rule.id if baseline_rule is not None else None
            ),
            source_demand_list_id=demand_list.id,
            sample_ref=sample_ref,
            input_snapshot_json=input_snapshot,
            inventory_fingerprint=fingerprint,
            status="PENDING",
            blockers_json=[],
            idempotency_key=clean_key,
            request_hash=request_hash,
            version=1,
        )
        session.add(simulation)
        session.flush()
        return simulation

    def claim(
        self,
        session: Session,
        tenant_id: str,
        simulation_id: int,
    ) -> AllocationSimulation | None:
        simulation = session.scalar(
            select(AllocationSimulation)
            .where(
                AllocationSimulation.tenant_id == tenant_id,
                AllocationSimulation.id == simulation_id,
            )
            .with_for_update()
        )
        if simulation is None or simulation.status != "PENDING":
            return None

        simulation.status = "RUNNING"
        simulation.started_at = datetime.now(timezone.utc)
        simulation.completed_at = None
        simulation.error_code = None
        simulation.error_summary = None
        simulation.version += 1
        session.flush()
        return simulation

    def run_claimed(
        self,
        session: Session,
        tenant_id: str,
        simulation_id: int,
    ) -> AllocationSimulation:
        simulation = session.scalar(
            select(AllocationSimulation)
            .where(
                AllocationSimulation.tenant_id == tenant_id,
                AllocationSimulation.id == simulation_id,
            )
            .with_for_update()
        )
        if simulation is None:
            raise NotFoundError("allocation_simulation", simulation_id)
        if simulation.status == "COMPLETED":
            return simulation
        if simulation.status != "RUNNING":
            raise ConflictError(
                "allocation simulation is not running",
                code="ALLOCATION_SIMULATION_STATE_CONFLICT",
                details={"status": simulation.status},
            )

        self._assert_inventory_fingerprint(
            session,
            simulation,
            phase="start",
        )
        results, blockers = self._score_frozen_snapshot(simulation)

        session.execute(
            delete(AllocationSimulationResult).where(
                AllocationSimulationResult.tenant_id == tenant_id,
                AllocationSimulationResult.simulation_id == simulation_id,
            )
        )
        session.add_all(results)
        session.flush()

        self._assert_inventory_fingerprint(
            session,
            simulation,
            phase="end",
        )

        simulation.blockers_json = blockers
        simulation.status = "COMPLETED"
        simulation.completed_at = datetime.now(timezone.utc)
        simulation.error_code = None
        simulation.error_summary = None
        simulation.version += 1
        self._mark_candidate_rule_simulated(session, simulation)
        session.flush()
        return simulation

    def cancel(
        self,
        session: Session,
        actor: ActorContext,
        simulation_id: int,
        *,
        expected_version: int,
    ) -> AllocationSimulation:
        self._require_contributor(actor)
        simulation = session.scalar(
            select(AllocationSimulation)
            .where(
                AllocationSimulation.tenant_id == actor.tenant_id,
                AllocationSimulation.id == simulation_id,
            )
            .with_for_update()
        )
        if simulation is None:
            self._raise_not_found(actor, "allocation_simulation", simulation_id)
        if simulation.status == "CANCELLED":
            return simulation
        if simulation.version != expected_version:
            self._raise_conflict(
                actor,
                "allocation simulation version conflict",
                code="ALLOCATION_SIMULATION_VERSION_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": simulation.version,
                },
            )
        if simulation.status not in {"PENDING", "RUNNING"}:
            self._raise_conflict(
                actor,
                "allocation simulation cannot be cancelled",
                code="ALLOCATION_SIMULATION_STATE_CONFLICT",
                details={"status": simulation.status},
            )

        simulation.status = "CANCELLED"
        simulation.completed_at = datetime.now(timezone.utc)
        simulation.version += 1
        session.flush()
        return simulation

    def fail_safely(
        self,
        tenant_id: str,
        simulation_id: int,
        error: Exception,
    ) -> None:
        session = SessionLocal()
        try:
            simulation = session.scalar(
                select(AllocationSimulation)
                .where(
                    AllocationSimulation.tenant_id == tenant_id,
                    AllocationSimulation.id == simulation_id,
                )
                .with_for_update()
            )
            if simulation is None:
                return
            if simulation.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                return

            simulation.status = "FAILED"
            simulation.completed_at = datetime.now(timezone.utc)
            simulation.error_code = "ALLOCATION_SIMULATION_FAILED"
            simulation.error_summary = self._sanitize_error(error)
            simulation.version += 1
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def latest_for_rule(
        self,
        session: Session,
        tenant_id: str,
        rule_id: int,
    ) -> SimulationSummary | None:
        simulation = session.scalar(
            select(AllocationSimulation)
            .where(
                AllocationSimulation.tenant_id == tenant_id,
                AllocationSimulation.candidate_rule_id == rule_id,
            )
            .order_by(
                AllocationSimulation.id.desc(),
            )
            .limit(1)
        )
        if simulation is None:
            return None
        return self._summary(session, simulation)

    # PLAN05_4D_TASK6_GREEN_B: public latest simulation read.
    def latest_read_for_rule(
        self,
        session: Session,
        tenant_id: str,
        rule_id: int,
    ) -> AllocationSimulationSummaryRead | None:
        summary = self.latest_for_rule(
            session,
            tenant_id,
            rule_id,
        )
        if summary is None:
            return None
        return AllocationSimulationSummaryRead(
            id=summary.id,
            status=summary.status,
            version=summary.version,
            progress=summary.progress,
            blockers=list(summary.blockers),
            results_summary=summary.results_summary,
            completed_at=summary.completed_at,
            error_code=summary.error_code,
            error_summary=summary.error_summary,
        )

    # PLAN05_4D_TASK6_GREEN_D: exact submitted-resource read.
    def read(
        self,
        session: Session,
        simulation: AllocationSimulation,
    ) -> AllocationSimulationSummaryRead:
        summary = self._summary(
            session,
            simulation,
        )
        return AllocationSimulationSummaryRead(
            id=summary.id,
            status=summary.status,
            version=summary.version,
            progress=summary.progress,
            blockers=list(summary.blockers),
            results_summary=summary.results_summary,
            completed_at=summary.completed_at,
            error_code=summary.error_code,
            error_summary=summary.error_summary,
        )

    def _summary(
        self,
        session: Session,
        simulation: AllocationSimulation,
    ) -> SimulationSummary:
        snapshot = simulation.input_snapshot_json or {}
        candidate_rule = snapshot.get("candidate_rule") or {}
        rule_hash = str(candidate_rule.get("canonical_hash") or "")
        regression = self._high_priority_regression(
            session,
            simulation,
        )
        results = list(
            session.scalars(
                select(AllocationSimulationResult)
                .where(
                    AllocationSimulationResult.tenant_id
                    == simulation.tenant_id,
                    AllocationSimulationResult.simulation_id
                    == simulation.id,
                )
                .order_by(AllocationSimulationResult.id.asc())
            ).all()
        )
        results_summary = AllocationSimulationResultsSummaryRead(
            total_rows=len(results),
            demand_item_count=len(
                {
                    result.demand_list_item_id
                    for result in results
                }
            ),
            high_priority_regression=regression,
        )
        return SimulationSummary(
            id=simulation.id,
            tenant_id=simulation.tenant_id,
            status=simulation.status,
            version=simulation.version,
            rule_hash=rule_hash,
            progress=self._progress(simulation.status),
            blockers=list(simulation.blockers_json or []),
            results_summary=results_summary,
            high_priority_regression=regression,
            completed_at=simulation.completed_at,
            error_code=simulation.error_code,
            error_summary=simulation.error_summary,
        )

    @staticmethod
    def _progress(status: str) -> AllocationSimulationProgressRead:
        if status == "PENDING":
            return AllocationSimulationProgressRead(
                phase="QUEUED",
                percent=0,
            )
        if status == "RUNNING":
            return AllocationSimulationProgressRead(
                phase="RUNNING",
                percent=None,
            )
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return AllocationSimulationProgressRead(
                phase="TERMINAL",
                percent=100,
            )
        raise ValueError(
            f"unsupported allocation simulation status: {status}"
        )

    def _high_priority_regression(
        self,
        session: Session,
        simulation: AllocationSimulation,
    ) -> Decimal:
        snapshot = simulation.input_snapshot_json or {}
        demand = snapshot.get("demand_list") or {}
        items = demand.get("items") or []
        high_priority_ids = {
            int(item["id"])
            for item in items
            if str(item.get("criticality_level") or "").upper()
            in {"CRITICAL", "HIGH"}
        }
        if not high_priority_ids:
            return _ZERO

        results = list(
            session.scalars(
                select(AllocationSimulationResult)
                .where(
                    AllocationSimulationResult.tenant_id
                    == simulation.tenant_id,
                    AllocationSimulationResult.simulation_id
                    == simulation.id,
                    AllocationSimulationResult.demand_list_item_id.in_(
                        high_priority_ids
                    ),
                )
                .order_by(AllocationSimulationResult.id.asc())
            ).all()
        )
        top_by_item: dict[int, dict[str, Decimal]] = {}
        for result in results:
            values = top_by_item.setdefault(result.demand_list_item_id, {})
            if (
                result.baseline_rank == 1
                and result.baseline_score is not None
            ):
                values["baseline"] = result.baseline_score
            if (
                result.candidate_rank == 1
                and result.candidate_score is not None
            ):
                values["candidate"] = result.candidate_score

        maximum = _ZERO
        for values in top_by_item.values():
            baseline = values.get("baseline")
            candidate = values.get("candidate")
            if baseline is None or candidate is None:
                continue
            maximum = max(maximum, baseline - candidate)
        return max(_ZERO, maximum)

    def _score_frozen_snapshot(
        self,
        simulation: AllocationSimulation,
    ) -> tuple[list[AllocationSimulationResult], list[dict[str, Any]]]:
        snapshot = simulation.input_snapshot_json
        candidate_payload = snapshot["candidate_rule"]
        baseline_payload = snapshot.get("baseline_rule")
        candidate_rule = RuleSnapshot(**candidate_payload["snapshot"])
        baseline_rule = (
            RuleSnapshot(**baseline_payload["snapshot"])
            if baseline_payload is not None
            else None
        )
        demand = snapshot["demand_list"]
        inventory = list(snapshot["inventory"])
        as_of = date.fromisoformat(snapshot["as_of_date"])

        results: list[AllocationSimulationResult] = []
        blockers: list[dict[str, Any]] = []
        for item in demand["items"]:
            candidate_ranked = rank_candidates(
                candidate_rule,
                self._candidates(
                    candidate_rule,
                    item,
                    inventory,
                    as_of=as_of,
                ),
            )
            baseline_ranked = (
                rank_candidates(
                    baseline_rule,
                    self._candidates(
                        baseline_rule,
                        item,
                        inventory,
                        as_of=as_of,
                    ),
                )
                if baseline_rule is not None
                else []
            )

            if not candidate_ranked:
                blockers.append(
                    {
                        "code": "ALLOCATION_HARD_RULE_BLOCKER",
                        "demand_list_item_id": int(item["id"]),
                        "message": "no eligible inventory candidate",
                    }
                )

            results.extend(
                self._result_rows(
                    simulation,
                    int(item["id"]),
                    baseline_ranked,
                    candidate_ranked,
                )
            )
        return results, blockers

    def _result_rows(
        self,
        simulation: AllocationSimulation,
        demand_list_item_id: int,
        baseline: list[RankedCandidate],
        candidate: list[RankedCandidate],
    ) -> list[AllocationSimulationResult]:
        baseline_map = {
            ranked.balance_id: (index, ranked)
            for index, ranked in enumerate(baseline, start=1)
        }
        candidate_map = {
            ranked.balance_id: (index, ranked)
            for index, ranked in enumerate(candidate, start=1)
        }

        ordered_ids: list[int] = []
        for ranked in candidate + baseline:
            if ranked.balance_id not in ordered_ids:
                ordered_ids.append(ranked.balance_id)

        if not ordered_ids:
            return [
                AllocationSimulationResult(
                    tenant_id=simulation.tenant_id,
                    simulation_id=simulation.id,
                    demand_list_item_id=demand_list_item_id,
                    candidate_balance_id=None,
                    baseline_rank=None,
                    candidate_rank=None,
                    baseline_score=None,
                    candidate_score=None,
                    score_delta=None,
                    reasons_json=[
                        {
                            "code": "NO_ELIGIBLE_CANDIDATE",
                            "message": "no eligible inventory candidate",
                        }
                    ],
                )
            ]

        rows: list[AllocationSimulationResult] = []
        for balance_id in ordered_ids:
            baseline_entry = baseline_map.get(balance_id)
            candidate_entry = candidate_map.get(balance_id)
            baseline_score = (
                baseline_entry[1].score
                if baseline_entry is not None
                else None
            )
            candidate_score = (
                candidate_entry[1].score
                if candidate_entry is not None
                else None
            )
            score_delta = (
                candidate_score - baseline_score
                if baseline_score is not None
                and candidate_score is not None
                else None
            )
            reasons: list[dict[str, Any]] = []
            if baseline_entry is None:
                reasons.append({"code": "BASELINE_NOT_ELIGIBLE"})
            if candidate_entry is None:
                reasons.append({"code": "CANDIDATE_NOT_ELIGIBLE"})

            rows.append(
                AllocationSimulationResult(
                    tenant_id=simulation.tenant_id,
                    simulation_id=simulation.id,
                    demand_list_item_id=demand_list_item_id,
                    candidate_balance_id=balance_id,
                    baseline_rank=(
                        baseline_entry[0]
                        if baseline_entry is not None
                        else None
                    ),
                    candidate_rank=(
                        candidate_entry[0]
                        if candidate_entry is not None
                        else None
                    ),
                    baseline_score=baseline_score,
                    candidate_score=candidate_score,
                    score_delta=score_delta,
                    reasons_json=reasons,
                )
            )
        return rows

    def _candidates(
        self,
        rule: RuleSnapshot,
        item: dict[str, Any],
        inventory: list[dict[str, Any]],
        *,
        as_of: date,
    ) -> list[_SimulationCandidate]:
        warehouse_ids = {
            int(value)
            for value in rule.scope.get("warehouse_ids", [])
        }
        spare_part_ids = {
            int(value)
            for value in rule.scope.get("spare_part_ids", [])
        }
        part_categories = {
            str(value)
            for value in rule.scope.get("part_categories", [])
        }

        candidates: list[_SimulationCandidate] = []
        for balance in inventory:
            if int(balance["spare_part_id"]) != int(item["spare_part_id"]):
                continue
            if warehouse_ids and int(balance["warehouse_id"]) not in warehouse_ids:
                continue
            if spare_part_ids and int(item["spare_part_id"]) not in spare_part_ids:
                continue
            if part_categories and str(item.get("category") or "") not in part_categories:
                continue

            expiry_value = balance.get("expiry_date")
            expiry = (
                date.fromisoformat(str(expiry_value))
                if expiry_value
                else None
            )
            expired = expiry is not None and expiry < as_of
            available_quantity = Decimal(
                str(balance["available_quantity"])
            )
            available = (
                available_quantity > _ZERO
                and bool(balance["location_active"])
                and bool(balance["location_pickable"])
                and str(balance["lot_quality_status"]) == "AVAILABLE"
            )
            metrics = {
                key: self._metric(
                    key,
                    item,
                    balance,
                    expiry=expiry,
                    as_of=as_of,
                )
                for key in rule.weights
            }
            candidates.append(
                _SimulationCandidate(
                    balance_id=int(balance["id"]),
                    metrics=metrics,
                    warehouse_priority=int(balance["warehouse_priority"]),
                    location_priority=int(balance["location_priority"]),
                    expiry_date=expiry,
                    lot_code=str(balance.get("lot_code") or ""),
                    frozen=bool(balance["lot_frozen"]),
                    expired=expired,
                    available=available,
                )
            )
        return candidates

    @staticmethod
    def _metric(
        name: str,
        item: dict[str, Any],
        balance: dict[str, Any],
        *,
        expiry: date | None,
        as_of: date,
    ) -> Decimal:
        normalized = name.casefold()
        balance_metrics = {
            "availability": "available_quantity",
            "available_quantity": "available_quantity",
            "on_hand": "on_hand_quantity",
            "on_hand_quantity": "on_hand_quantity",
            "reserved": "reserved_quantity",
            "reserved_quantity": "reserved_quantity",
            "damaged": "damaged_quantity",
            "damaged_quantity": "damaged_quantity",
            "quarantined": "quarantined_quantity",
            "quarantined_quantity": "quarantined_quantity",
            "in_transit": "in_transit_quantity",
            "in_transit_quantity": "in_transit_quantity",
        }
        field = balance_metrics.get(normalized)
        if field is not None:
            return Decimal(str(balance[field]))
        if normalized in {"criticality", "criticality_level"}:
            return _CRITICALITY.get(
                str(item.get("criticality_level") or "").upper(),
                _ZERO,
            )
        if normalized in {"demand", "demand_quantity"}:
            return Decimal(str(item["final_quantity"]))
        if normalized == "expiry_days":
            if expiry is None:
                return Decimal("999999")
            return Decimal(max((expiry - as_of).days, 0))
        return _ZERO

    def _assert_inventory_fingerprint(
        self,
        session: Session,
        simulation: AllocationSimulation,
        *,
        phase: str,
    ) -> None:
        current = snapshot_service.canonical_hash(
            self._inventory_state(session, simulation.tenant_id)
        )
        if current != simulation.inventory_fingerprint:
            raise BusinessValidationError(
                "inventory changed during allocation simulation",
                code="ALLOCATION_SIMULATION_INVENTORY_CHANGED",
                details={
                    "phase": phase,
                    "expected_fingerprint": simulation.inventory_fingerprint,
                    "actual_fingerprint": current,
                },
            )

    def _mark_candidate_rule_simulated(
        self,
        session: Session,
        simulation: AllocationSimulation,
    ) -> None:
        rule = session.scalar(
            select(AllocationRuleVersion)
            .where(
                AllocationRuleVersion.tenant_id == simulation.tenant_id,
                AllocationRuleVersion.id == simulation.candidate_rule_id,
            )
            .with_for_update()
        )
        if rule is None or rule.status != "DRAFT":
            return

        frozen = simulation.input_snapshot_json["candidate_rule"]
        current_hash = AllocationRuleService.snapshot(rule).canonical_hash
        if current_hash != frozen["canonical_hash"]:
            return

        rule.status = "SIMULATED"
        rule.version += 1

    def _demand_snapshot(
        self,
        session: Session,
        tenant_id: str,
        demand_list: DemandList,
    ) -> dict[str, Any]:
        items = list(
            session.scalars(
                select(DemandListItem)
                .where(
                    DemandListItem.tenant_id == tenant_id,
                    DemandListItem.demand_list_id == demand_list.id,
                )
                .order_by(DemandListItem.id.asc())
            ).all()
        )
        result_items: list[dict[str, Any]] = []
        for item in items:
            spare_part = session.scalar(
                select(SparePart).where(
                    SparePart.tenant_id == tenant_id,
                    SparePart.id == item.spare_part_id,
                )
            )
            result_items.append(
                {
                    "id": item.id,
                    "spare_part_id": item.spare_part_id,
                    "spare_part_code": item.spare_part_code_snapshot,
                    "spare_part_name": item.spare_part_name_snapshot,
                    "category": (
                        spare_part.category
                        if spare_part is not None
                        else None
                    ),
                    "criticality_level": item.criticality_level_snapshot,
                    "final_quantity": format(item.final_quantity, "f"),
                    "source_snapshot": item.source_snapshot_json,
                }
            )

        return {
            "id": demand_list.id,
            "lineage_id": demand_list.lineage_id,
            "version_number": demand_list.version_number,
            "version": demand_list.version,
            "status": self._enum_value(demand_list.status),
            "is_current": demand_list.is_current,
            "items": result_items,
        }

    def _inventory_state(
        self,
        session: Session,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        balances = list(
            session.scalars(
                select(InventoryBalance)
                .where(InventoryBalance.tenant_id == tenant_id)
                .order_by(InventoryBalance.id.asc())
            ).all()
        )
        result: list[dict[str, Any]] = []
        for balance in balances:
            location = session.scalar(
                select(WarehouseLocation).where(
                    WarehouseLocation.tenant_id == tenant_id,
                    WarehouseLocation.id == balance.location_id,
                )
            )
            lot = (
                session.scalar(
                    select(InventoryLot).where(
                        InventoryLot.tenant_id == tenant_id,
                        InventoryLot.id == balance.lot_id,
                    )
                )
                if balance.lot_id is not None
                else None
            )
            available = balance.available_quantity
            result.append(
                {
                    "id": balance.id,
                    "warehouse_id": balance.warehouse_id,
                    "location_id": balance.location_id,
                    "spare_part_id": balance.spare_part_id,
                    "lot_id": balance.lot_id,
                    "on_hand_quantity": format(
                        balance.on_hand_quantity,
                        "f",
                    ),
                    "reserved_quantity": format(
                        balance.reserved_quantity,
                        "f",
                    ),
                    "damaged_quantity": format(
                        balance.damaged_quantity,
                        "f",
                    ),
                    "quarantined_quantity": format(
                        balance.quarantined_quantity,
                        "f",
                    ),
                    "in_transit_quantity": format(
                        balance.in_transit_quantity,
                        "f",
                    ),
                    "available_quantity": format(available, "f"),
                    "version": balance.version,
                    "warehouse_priority": balance.warehouse_id,
                    "location_priority": balance.location_id,
                    "location_active": (
                        bool(location.is_active)
                        if location is not None
                        else False
                    ),
                    "location_pickable": (
                        bool(location.is_pickable)
                        if location is not None
                        else False
                    ),
                    "lot_code": (
                        lot.lot_code if lot is not None else ""
                    ),
                    "lot_quality_status": (
                        lot.quality_status
                        if lot is not None
                        else "AVAILABLE"
                    ),
                    "lot_frozen": (
                        bool(lot.is_frozen)
                        if lot is not None
                        else False
                    ),
                    "expiry_date": (
                        lot.expiry_date.isoformat()
                        if lot is not None
                        and lot.expiry_date is not None
                        else None
                    ),
                }
            )
        return result

    @staticmethod
    def _rule_snapshot(
        rule: AllocationRuleVersion,
    ) -> dict[str, Any]:
        snapshot = AllocationRuleService.snapshot(rule)
        return {
            "id": rule.id,
            "lineage_id": rule.lineage_id,
            "version_number": rule.version_number,
            "version": rule.version,
            "status": rule.status,
            "canonical_hash": snapshot.canonical_hash,
            "snapshot": snapshot.model_dump(mode="json"),
        }

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _sanitize_error(error: Exception) -> str:
        summary = " ".join(str(error).split())
        summary = _SENSITIVE_VALUE.sub(
            lambda match: f"{match.group(1)}=[REDACTED]",
            summary,
        )
        if not summary:
            summary = error.__class__.__name__
        return summary[:500]

    @staticmethod
    def _normalize_idempotency_key(
        actor: ActorContext,
        value: str,
    ) -> str:
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
    def _require_rule(
        session: Session,
        actor: ActorContext,
        rule_id: int,
    ) -> AllocationRuleVersion:
        rule = session.scalar(
            select(AllocationRuleVersion).where(
                AllocationRuleVersion.tenant_id == actor.tenant_id,
                AllocationRuleVersion.id == rule_id,
            )
        )
        if rule is None:
            AllocationSimulationService._raise_not_found(
                actor,
                "allocation_rule",
                rule_id,
            )
        return rule

    @staticmethod
    def _require_demand_list(
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
    ) -> DemandList:
        demand_list = session.scalar(
            select(DemandList).where(
                DemandList.tenant_id == actor.tenant_id,
                DemandList.id == demand_list_id,
            )
        )
        if demand_list is None:
            AllocationSimulationService._raise_not_found(
                actor,
                "demand_list",
                demand_list_id,
            )
        return demand_list

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


allocation_simulation_service = AllocationSimulationService()
