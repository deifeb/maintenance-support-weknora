from __future__ import annotations

import hashlib
from decimal import Decimal
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    CalculationGroup,
    CalculationItemDecision,
    DemandCalculationRun,
    DemandRunItemResult,
    DemandScenarioVersion,
)
from app.models.enums import (
    CalculationDecisionType,
    CalculationGroupStatus,
    CalculationStatus,
    ScenarioVersionStatus,
)
from app.repositories.calculation_group_repository import (
    CalculationGroupChildRepository,
    CalculationGroupRepository,
    CalculationItemDecisionRepository,
)
from app.schemas.calculation_group import (
    CalculationComparisonRow,
    CalculationGroupComparisonRead,
    CalculationItemDecisionRead,
    ComparisonCandidateCell,
)
from app.schemas.common import PageData
from app.schemas.model_recommendation import (
    CandidateRecommendation,
)
from app.security.actor import ActorContext
from app.services.demand_calculation_service import (
    CandidateExecutionSpec,
    DemandCalculationService,
    calculation_service,
)
from app.services.model_recommendation_service import (
    ModelRecommendationService,
    model_recommendation_service,
)
from app.services.snapshot_service import snapshot_service


class CalculationGroupService:
    DECISION_RISK_RULE_VERSION = "DEMAND-DECISION-RISK-1"

    def __init__(self) -> None:
        self.group_repository = CalculationGroupRepository()
        self.child_repository = (
            CalculationGroupChildRepository()
        )
        self.decision_repository = (
            CalculationItemDecisionRepository()
        )
        self.calculation_service: DemandCalculationService = (
            calculation_service
        )
        self.recommendation_service: (
            ModelRecommendationService
        ) = model_recommendation_service

    def _locked_version(
        self,
        session: Session,
        actor: ActorContext,
        scenario_version_id: int,
    ) -> DemandScenarioVersion:
        version = session.scalar(
            select(DemandScenarioVersion)
            .where(
                DemandScenarioVersion.tenant_id
                == actor.tenant_id,
                DemandScenarioVersion.id
                == scenario_version_id,
            )
            .with_for_update()
        )
        if version is None:
            raise NotFoundError(
                "demand_scenario_version",
                scenario_version_id,
            )
        if version.status is not ScenarioVersionStatus.PUBLISHED:
            raise ConflictError(
                "scenario version must be published",
                code="SCENARIO_NOT_PUBLISHED",
            )
        return version

    @staticmethod
    def _request_hash(
        *,
        scenario_version_id: int,
        primary_candidate_key: str,
        selected_candidate_keys: list[str],
        random_seed: int,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "scenario_version_id": scenario_version_id,
                "primary_candidate_key": (
                    primary_candidate_key
                ),
                "selected_candidate_keys": sorted(
                    selected_candidate_keys
                ),
                "random_seed": random_seed,
            }
        )

    @staticmethod
    def _calculation_idempotency_key(
        group_idempotency_key: str,
        candidate_key: str,
        attempt_number: int,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{group_idempotency_key}:"
                f"{candidate_key}:"
                f"{attempt_number}"
            ).encode("utf-8")
        ).hexdigest()
        return f"group:{digest}"

    @staticmethod
    def _candidate_map(
        items: list[CandidateRecommendation],
    ) -> dict[str, CandidateRecommendation]:
        return {
            item.candidate_key: item
            for item in items
        }

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        scenario_version_id: int,
        primary_candidate_key: str,
        selected_candidate_keys: list[str],
        idempotency_key: str,
        random_seed: int = 20260723,
    ) -> CalculationGroup:
        selected = list(dict.fromkeys(selected_candidate_keys))
        if (
            not selected
            or len(selected) != len(selected_candidate_keys)
        ):
            raise BusinessValidationError(
                "selected candidates must be non-empty and unique",
                code="INVALID_CANDIDATE_SELECTION",
            )
        if primary_candidate_key not in selected:
            raise BusinessValidationError(
                "primary candidate must be selected",
                code="PRIMARY_CANDIDATE_NOT_SELECTED",
            )
        request_hash = self._request_hash(
            scenario_version_id=scenario_version_id,
            primary_candidate_key=primary_candidate_key,
            selected_candidate_keys=selected,
            random_seed=random_seed,
        )
        existing = (
            self.group_repository.get_by_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ConflictError(
                    "idempotency key was reused",
                    code="IDEMPOTENCY_KEY_REUSED",
                )
            loaded = self.group_repository.get(
                session,
                actor.tenant_id,
                existing.id,
            )
            assert loaded is not None
            return loaded

        try:
            self._locked_version(
                session,
                actor,
                scenario_version_id,
            )
            recommendation = (
                self.recommendation_service.recommend(
                    session,
                    actor,
                    scenario_version_id,
                )
            )
            candidates = self._candidate_map(
                recommendation.items
            )
            invalid = [
                key
                for key in selected
                if (
                    key not in candidates
                    or not candidates[key].applicable
                )
            ]
            if invalid:
                raise BusinessValidationError(
                    "selected candidate is not applicable",
                    code="CANDIDATE_NOT_APPLICABLE",
                    details={"candidate_keys": invalid},
                )

            group = self.group_repository.create(
                session,
                actor.tenant_id,
                {
                    "scenario_version_id": (
                        scenario_version_id
                    ),
                    "status": CalculationGroupStatus.PENDING,
                    "primary_candidate_key": (
                        primary_candidate_key
                    ),
                    "recommendation_snapshot_json": (
                        recommendation.model_dump(mode="json")
                    ),
                    "parameter_snapshot_json": {
                        "random_seed": random_seed,
                        "selected_candidate_keys": selected,
                    },
                    "idempotency_key": idempotency_key,
                    "request_hash": request_hash,
                    "created_by_user_id": actor.user_id,
                    "created_by_request_id": actor.request_id,
                },
            )
            self.group_repository.append_event(
                session,
                actor.tenant_id,
                group.id,
                event_type="group.created",
                payload={
                    "status": CalculationGroupStatus.PENDING.value,
                    "primary_candidate_key": (
                        primary_candidate_key
                    ),
                },
            )
            for key in selected:
                candidate = candidates[key]
                calculation = (
                    self.calculation_service.submit_candidate(
                        session,
                        actor,
                        scenario_version_id=(
                            scenario_version_id
                        ),
                        spec=CandidateExecutionSpec(
                            candidate_key=key,
                            reliability_model=(
                                candidate.reliability_model
                            ),
                            execution_mode=(
                                candidate.execution_mode
                            ),
                            random_seed=random_seed,
                        ),
                        idempotency_key=(
                            self._calculation_idempotency_key(
                                idempotency_key,
                                key,
                                1,
                            )
                        ),
                    )
                )
                child = self.child_repository.create_attempt(
                    session,
                    actor.tenant_id,
                    group.id,
                    {
                        "candidate_key": key,
                        "reliability_model": (
                            candidate.reliability_model
                        ),
                        "execution_mode": (
                            candidate.execution_mode
                        ),
                        "calculation_id": calculation.id,
                        "is_primary": (
                            key == primary_candidate_key
                        ),
                        "selection_reason": ";".join(
                            candidate.reasons
                        ),
                    },
                )
                self.group_repository.append_event(
                    session,
                    actor.tenant_id,
                    group.id,
                    child_id=child.id,
                    event_type="child.queued",
                    payload={
                        "candidate_key": key,
                        "calculation_id": calculation.id,
                        "attempt_number": 1,
                    },
                )
            session.commit()
        except Exception:
            session.rollback()
            raise

        loaded = self.group_repository.get(
            session,
            actor.tenant_id,
            group.id,
        )
        assert loaded is not None
        return loaded

    def get(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
    ) -> CalculationGroup:
        group = self.group_repository.get(
            session,
            actor.tenant_id,
            group_id,
        )
        if group is None:
            raise NotFoundError(
                "calculation_group",
                group_id,
            )
        return group

    @staticmethod
    def _aggregate_status(
        group: CalculationGroup,
    ) -> CalculationGroupStatus:
        statuses = [
            child.calculation.status
            for child in group.current_children
        ]
        if not statuses or all(
            status is CalculationStatus.PENDING
            for status in statuses
        ):
            return CalculationGroupStatus.PENDING
        if any(
            status
            in {
                CalculationStatus.PENDING,
                CalculationStatus.RUNNING,
            }
            for status in statuses
        ):
            return CalculationGroupStatus.RUNNING
        successful = {
            CalculationStatus.SUCCEEDED,
            CalculationStatus.PARTIAL_SUCCESS,
        }
        if all(status in successful for status in statuses):
            return CalculationGroupStatus.COMPLETED
        if all(
            status is CalculationStatus.FAILED
            for status in statuses
        ):
            return CalculationGroupStatus.FAILED
        if all(
            status is CalculationStatus.CANCELLED
            for status in statuses
        ):
            return CalculationGroupStatus.CANCELLED
        if any(status in successful for status in statuses):
            return CalculationGroupStatus.PARTIALLY_COMPLETED
        if any(
            status is CalculationStatus.INTERRUPTED
            for status in statuses
        ):
            return CalculationGroupStatus.INTERRUPTED
        return CalculationGroupStatus.FAILED

    def refresh_status_internal(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
        *,
        commit: bool = False,
    ) -> CalculationGroup:
        group = self.group_repository.get(
            session,
            tenant_id,
            group_id,
        )
        if group is None:
            raise NotFoundError(
                "calculation_group",
                group_id,
            )
        next_status = self._aggregate_status(group)
        if group.status is not next_status:
            previous = group.status
            group.status = next_status
            group.version += 1
            session.flush()
            self.group_repository.append_event(
                session,
                tenant_id,
                group.id,
                event_type="group.status_changed",
                payload={
                    "from": previous.value,
                    "to": next_status.value,
                },
            )
        if commit:
            session.commit()
            loaded = self.group_repository.get(
                session,
                tenant_id,
                group_id,
            )
            assert loaded is not None
            return loaded
        session.flush()
        return group

    def refresh_status(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
    ) -> CalculationGroup:
        return self.refresh_status_internal(
            session,
            actor.tenant_id,
            group_id,
            commit=True,
        )

    @staticmethod
    def _retry_idempotency_key(
        idempotency_key: str,
        candidate_key: str,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{idempotency_key}:"
                f"{candidate_key}"
            ).encode("utf-8")
        ).hexdigest()
        return f"retry:{digest}"

    def retry_failed(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
        *,
        idempotency_key: str,
    ) -> CalculationGroup:
        group = self.get(session, actor, group_id)
        replay_keys = {
            self._retry_idempotency_key(
                idempotency_key,
                child.candidate_key,
            )
            for child in group.current_children
        }
        if any(
            child.calculation.idempotency_key
            in replay_keys
            for child in group.current_children
        ):
            return group
        retryable = [
            child
            for child in group.current_children
            if child.calculation.status
            in {
                CalculationStatus.FAILED,
                CalculationStatus.INTERRUPTED,
            }
        ]
        if not retryable:
            raise ConflictError(
                "calculation group has no retryable children",
                code="CALCULATION_GROUP_NOT_RETRYABLE",
            )
        try:
            for child in retryable:
                calculation = (
                    self.calculation_service.retry_candidate(
                        session,
                        actor,
                        source=child.calculation,
                        idempotency_key=(
                            self._retry_idempotency_key(
                                idempotency_key,
                                child.candidate_key,
                            )
                        ),
                    )
                )
                created = self.child_repository.create_attempt(
                    session,
                    actor.tenant_id,
                    group.id,
                    {
                        "candidate_key": child.candidate_key,
                        "reliability_model": (
                            child.reliability_model
                        ),
                        "execution_mode": (
                            child.execution_mode
                        ),
                        "calculation_id": calculation.id,
                        "is_primary": child.is_primary,
                        "selection_reason": (
                            child.selection_reason
                        ),
                    },
                )
                self.group_repository.append_event(
                    session,
                    actor.tenant_id,
                    group.id,
                    child_id=created.id,
                    event_type="child.queued",
                    payload={
                        "candidate_key": (
                            child.candidate_key
                        ),
                        "calculation_id": calculation.id,
                        "attempt_number": (
                            created.attempt_number
                        ),
                    },
                )
            self.refresh_status_internal(
                session,
                actor.tenant_id,
                group.id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return self.get(session, actor, group.id)

    def cancel_running(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
        *,
        idempotency_key: str,
    ) -> CalculationGroup:
        group = self.get(session, actor, group_id)
        if any(
            event.event_type == "group.cancel_requested"
            and event.payload_json.get("idempotency_key")
            == idempotency_key
            for event in self.group_repository.list_events(
                session,
                actor.tenant_id,
                group.id,
            )
        ):
            return group
        changed = False
        for child in group.current_children:
            calculation = child.calculation
            if calculation.status not in {
                CalculationStatus.PENDING,
                CalculationStatus.RUNNING,
            }:
                continue
            changed = True
            calculation.cancel_requested = True
            if calculation.status is CalculationStatus.PENDING:
                calculation.status = CalculationStatus.CANCELLED
                self.group_repository.append_event(
                    session,
                    actor.tenant_id,
                    group.id,
                    child_id=child.id,
                    event_type="child.cancelled",
                    payload={
                        "candidate_key": (
                            child.candidate_key
                        )
                    },
                )
        if not changed:
            raise ConflictError(
                "calculation group has no running children",
                code="CALCULATION_GROUP_NOT_CANCELLABLE",
            )
        self.group_repository.append_event(
            session,
            actor.tenant_id,
            group.id,
            event_type="group.cancel_requested",
            payload={"idempotency_key": idempotency_key},
        )
        self.refresh_status_internal(
            session,
            actor.tenant_id,
            group.id,
        )
        session.commit()
        return self.get(session, actor, group.id)

    def events(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
        *,
        after_sequence: int = 0,
    ):
        self.get(session, actor, group_id)
        return self.group_repository.list_events(
            session,
            actor.tenant_id,
            group_id,
            after_sequence=after_sequence,
        )

    @staticmethod
    def _successful_children(group: CalculationGroup):
        successful = {
            CalculationStatus.SUCCEEDED,
            CalculationStatus.PARTIAL_SUCCESS,
        }
        return [
            child
            for child in group.current_children
            if child.calculation.status in successful
        ]

    def comparison(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
    ) -> CalculationGroupComparisonRead:
        group = self.get(session, actor, group_id)
        terminal_statuses = {
            CalculationGroupStatus.COMPLETED,
            CalculationGroupStatus.PARTIALLY_COMPLETED,
            CalculationGroupStatus.FAILED,
            CalculationGroupStatus.CANCELLED,
            CalculationGroupStatus.INTERRUPTED,
        }
        if group.status not in terminal_statuses:
            raise ConflictError(
                "calculation group is not terminal",
                code="CALCULATION_GROUP_NOT_TERMINAL",
            )
        successful = self._successful_children(group)
        if not successful:
            raise ConflictError(
                "calculation group has no successful candidates",
                code="CALCULATION_GROUP_HAS_NO_RESULTS",
            )
        child_by_calculation = {
            child.calculation_id: child
            for child in successful
        }
        result_rows = session.execute(
            select(
                DemandRunItemResult,
                DemandCalculationRun.calculation_id,
            )
            .join(
                DemandCalculationRun,
                DemandRunItemResult.calculation_run_id
                == DemandCalculationRun.id,
            )
            .where(
                DemandRunItemResult.tenant_id
                == actor.tenant_id,
                DemandCalculationRun.tenant_id
                == actor.tenant_id,
                DemandCalculationRun.calculation_id.in_(
                    child_by_calculation
                ),
                DemandCalculationRun.is_current_attempt.is_(
                    True
                ),
                DemandRunItemResult.calculation_status.in_(
                    ["CALCULATED", "FALLBACK"]
                ),
            )
        ).all()
        by_spare: dict[
            int,
            dict[int, DemandRunItemResult],
        ] = {}
        for result, calculation_id in result_rows:
            child = child_by_calculation[calculation_id]
            by_spare.setdefault(
                result.spare_part_id,
                {},
            )[child.id] = result

        decisions = {
            decision.spare_part_id: decision
            for decision in session.scalars(
                select(CalculationItemDecision).where(
                    CalculationItemDecision.tenant_id
                    == actor.tenant_id,
                    CalculationItemDecision.group_id
                    == group.id,
                )
            ).all()
        }
        rows: list[CalculationComparisonRow] = []
        for spare_part_id, child_results in by_spare.items():
            source_child = next(
                (
                    child
                    for child in successful
                    if child.is_primary
                    and child.id in child_results
                ),
                next(
                    child
                    for child in successful
                    if child.id in child_results
                ),
            )
            identity = child_results[source_child.id]
            cells: dict[str, ComparisonCandidateCell] = {}
            for child in group.current_children:
                item = child_results.get(child.id)
                cells[child.candidate_key] = (
                    ComparisonCandidateCell(
                        child_id=child.id,
                        candidate_key=child.candidate_key,
                        reliability_model=(
                            child.reliability_model
                        ),
                        execution_mode=child.execution_mode,
                        status=(
                            "SUCCEEDED"
                            if item is not None
                            else "NO_RESULT"
                        ),
                        item_status=(
                            item.calculation_status.value
                            if item is not None
                            else None
                        ),
                        recommended_quantity=(
                            item.recommended_spare_quantity
                            if item is not None
                            else None
                        ),
                        expected_demand=(
                            item.expected_demand
                            if item is not None
                            else None
                        ),
                        p50=item.p50 if item else None,
                        p95=item.p95 if item else None,
                        p99=item.p99 if item else None,
                        usable_inventory=(
                            item.usable_inventory
                            if item is not None
                            else None
                        ),
                        net_demand_gap=(
                            item.net_demand_gap
                            if item is not None
                            else None
                        ),
                        shortage_risk_level=(
                            item.shortage_risk_level.value
                            if item is not None
                            else None
                        ),
                        warnings=(
                            list(item.warning_codes_json or [])
                            if item is not None
                            else []
                        ),
                    )
                )
            decision = decisions.get(spare_part_id)
            rows.append(
                CalculationComparisonRow(
                    spare_part_id=spare_part_id,
                    spare_part_code=(
                        identity.spare_part_code_snapshot
                    ),
                    spare_part_name=(
                        identity.spare_part_name_snapshot
                    ),
                    criticality_level=(
                        identity.criticality_level
                    ),
                    system_child_id=source_child.id,
                    candidates=cells,
                    decision=(
                        CalculationItemDecisionRead.model_validate(
                            decision
                        )
                        if decision is not None
                        else None
                    ),
                )
            )
        rows.sort(
            key=lambda row: (
                row.spare_part_code,
                row.spare_part_id,
            )
        )
        return CalculationGroupComparisonRead(
            group_id=group.id,
            group_status=group.status,
            primary_candidate_key=group.primary_candidate_key,
            candidate_keys=[
                child.candidate_key
                for child in group.current_children
            ],
            risk_rule_version=self.DECISION_RISK_RULE_VERSION,
            rows=rows,
        )

    @staticmethod
    def _is_material_warning(warnings: list[str]) -> bool:
        material_tokens = (
            "MISSING",
            "NON_CONVERGENCE",
            "NOT_CONVERGED",
            "HIGH",
        )
        return any(
            any(token in warning.upper() for token in material_tokens)
            for warning in warnings
        )

    def save_decision(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
        *,
        spare_part_id: int,
        expected_version: int,
        selected_child_id: int,
        final_quantity: Decimal,
        reason: str | None,
    ) -> CalculationItemDecision:
        locked_group = self.group_repository.get_for_update(
            session,
            actor.tenant_id,
            group_id,
        )
        if locked_group is None:
            raise NotFoundError(
                "calculation_group",
                group_id,
            )
        comparison = self.comparison(
            session,
            actor,
            group_id,
        )
        row = next(
            (
                item
                for item in comparison.rows
                if item.spare_part_id == spare_part_id
            ),
            None,
        )
        if row is None:
            raise NotFoundError(
                "calculation_comparison_item",
                spare_part_id,
            )
        selected = next(
            (
                cell
                for cell in row.candidates.values()
                if cell.child_id == selected_child_id
            ),
            None,
        )
        if (
            selected is None
            or selected.status != "SUCCEEDED"
            or selected.recommended_quantity is None
        ):
            raise BusinessValidationError(
                "selected child has no successful current result",
                code="CALCULATION_DECISION_INVALID_CHILD",
            )
        source = next(
            cell
            for cell in row.candidates.values()
            if cell.child_id == row.system_child_id
        )
        assert source.recommended_quantity is not None
        selected_quantity = selected.recommended_quantity
        changed_candidate = (
            selected_child_id != row.system_child_id
        )
        changed_quantity = final_quantity != selected_quantity
        clean_reason = (reason or "").strip()
        if (
            changed_candidate or changed_quantity
        ) and not clean_reason:
            raise BusinessValidationError(
                "a reason is required for a non-default decision",
                code="CALCULATION_DECISION_REASON_REQUIRED",
            )

        existing = self.decision_repository.get_for_update(
            session,
            actor.tenant_id,
            group_id,
            spare_part_id,
        )
        actual_version = (
            existing.version if existing is not None else 0
        )
        if actual_version != expected_version:
            raise ConflictError(
                "calculation decision version conflict",
                code="CALCULATION_DECISION_VERSION_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": actual_version,
                },
            )

        ten_percent_reduction = (
            selected_quantity > 0
            and final_quantity
            <= selected_quantity * Decimal("0.90")
        )
        critical_reduction = (
            (row.criticality_level or "").upper()
            in {"HIGH", "CRITICAL"}
            and final_quantity < selected_quantity
        )
        successful_cells = [
            cell
            for cell in row.candidates.values()
            if (
                cell.status == "SUCCEEDED"
                and cell.p50 is not None
                and cell.p99 is not None
            )
        ]
        outside_all_ranges = (
            bool(successful_cells)
            and all(
                final_quantity < cell.p50
                or final_quantity > cell.p99
                for cell in successful_cells
            )
        )
        source_quantity = source.recommended_quantity
        non_primary_material_difference = (
            changed_candidate
            and source_quantity > 0
            and abs(
                selected_quantity - source_quantity
            ) / source_quantity
            >= Decimal("0.10")
        )
        material_warning = self._is_material_warning(
            selected.warnings
        )
        requires_admin = any(
            (
                ten_percent_reduction,
                critical_reduction,
                outside_all_ranges,
                non_primary_material_difference,
                material_warning,
            )
        )
        if changed_quantity:
            decision_type = (
                CalculationDecisionType.MANUAL_QUANTITY
            )
        elif changed_candidate:
            decision_type = (
                CalculationDecisionType.ALTERNATIVE_CANDIDATE
            )
        else:
            decision_type = (
                CalculationDecisionType.SYSTEM_RECOMMENDATION
            )
        try:
            decision = self.decision_repository.upsert(
                session,
                actor.tenant_id,
                group_id,
                spare_part_id,
                {
                    "source_child_id": row.system_child_id,
                    "selected_child_id": selected_child_id,
                    "original_quantity": (
                        source.recommended_quantity
                    ),
                    "final_quantity": final_quantity,
                    "decision_type": decision_type,
                    "reason": clean_reason or None,
                    "risk": (
                        "HIGH" if requires_admin else "LOW"
                    ),
                    "requires_admin_confirmation": (
                        requires_admin
                    ),
                    "confirmed_by_admin": False,
                    "risk_rule_version": (
                        self.DECISION_RISK_RULE_VERSION
                    ),
                    "decided_by_user_id": actor.user_id,
                    "decided_by_request_id": (
                        actor.request_id
                    ),
                },
            )
            self.group_repository.append_event(
                session,
                actor.tenant_id,
                group_id,
                event_type="decision.updated",
                payload={
                    "spare_part_id": spare_part_id,
                    "decision_id": decision.id,
                    "decision_version": decision.version,
                    "risk": decision.risk,
                    "requires_admin_confirmation": (
                        decision.requires_admin_confirmation
                    ),
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return decision

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        status: CalculationGroupStatus | None = None,
    ) -> PageData[dict[str, object]]:
        rows, total = self.group_repository.list_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status.value if status else None,
        )
        return PageData[dict[str, object]](
            items=[
                {
                    "id": row.id,
                    "scenario_version_id": (
                        row.scenario_version_id
                    ),
                    "status": row.status.value,
                    "primary_candidate_key": (
                        row.primary_candidate_key
                    ),
                    "last_event_sequence": (
                        row.last_event_sequence
                    ),
                    "version": row.version,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )


calculation_group_service = CalculationGroupService()
