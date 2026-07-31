from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import ceil
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import (
    DemandCalculationRun,
    DemandRunItemResult,
    SparePart,
)
from app.models.calculation_group import (
    CalculationGroup,
    CalculationGroupChild,
    CalculationItemDecision,
)
from app.models.demand_list import DemandListEvent
from app.models.enums import (
    CalculationStatus,
    DemandListEventType,
    DemandListStatus,
    ItemCalculationStatus,
)
from app.repositories.demand_list_repository import (
    DemandListItemRepository,
    DemandListRepository,
)
from app.schemas.common import PageData
from app.schemas.demand_list import (
    DemandListCreateRequest,
    DemandListRead,
    DemandListSummaryRead,
)
from app.security.actor import (
    ActorContext,
    MaintenanceRole,
)
from app.services.calculation_group_service import (
    CalculationGroupService,
)
from app.services.demand_decision_policy import (
    DecisionCandidateEvidence,
    evaluate_decision_risk,
)
from app.services.snapshot_service import snapshot_service

_SNAPSHOT_DECIMAL_QUANTUM = Decimal("0.000001")


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(
        value.quantize(_SNAPSHOT_DECIMAL_QUANTUM),
        "f",
    )


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _snapshot_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_string(value)
    if isinstance(value, float):
        return _decimal_string(
            Decimal(str(value))
        )
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _snapshot_json(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _snapshot_json(item)
            for item in value
        ]
    return deepcopy(value)


class DemandListService:
    def __init__(
        self,
        *,
        repository: DemandListRepository | None = None,
        item_repository: (
            DemandListItemRepository | None
        ) = None,
        calculation_group_service: (
            CalculationGroupService | None
        ) = None,
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else DemandListRepository()
        )
        self.item_repository = (
            item_repository
            if item_repository is not None
            else DemandListItemRepository()
        )
        self.calculation_group_service = (
            calculation_group_service
            if calculation_group_service is not None
            else CalculationGroupService()
        )

    @staticmethod
    def _require_contributor(
        actor: ActorContext,
    ) -> None:
        if actor.role not in {
            MaintenanceRole.CONTRIBUTOR,
            MaintenanceRole.ADMIN,
        }:
            raise InsufficientMaintenanceRoleError(
                required_role=(
                    MaintenanceRole.CONTRIBUTOR.value
                ),
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _request_hash(
        *,
        calculation_group_id: int,
        name: str,
        description: str | None,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "calculation_group_id": (
                    calculation_group_id
                ),
                "name": name,
                "description": description,
            }
        )

    @staticmethod
    def _idempotent_response(
        receipt: DemandListEvent,
        request_hash: str,
    ) -> DemandListRead:
        if (
            receipt.event_type
            is not DemandListEventType.CREATED
        ):
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            )
        if receipt.request_hash != request_hash:
            raise ConflictError(
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "demand_list",
                    "retryable": False,
                },
            )
        if receipt.response_snapshot_json is None:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            )
        try:
            return (
                DemandListRead.model_validate(
                    receipt.response_snapshot_json
                )
                .model_copy(deep=True)
            )
        except ValidationError as exc:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            ) from exc

    @staticmethod
    def _successful_children(
        group: CalculationGroup,
    ) -> list[CalculationGroupChild]:
        successful = {
            CalculationStatus.SUCCEEDED,
            CalculationStatus.PARTIAL_SUCCESS,
        }
        return [
            child
            for child in group.current_children
            if child.calculation.status in successful
        ]

    @staticmethod
    def _result_map(
        session: Session,
        actor: ActorContext,
        successful_children: list[
            CalculationGroupChild
        ],
    ) -> dict[tuple[int, int], tuple[
        DemandRunItemResult,
        DemandCalculationRun,
    ]]:
        if not successful_children:
            return {}
        calculation_ids = {
            child.calculation_id
            for child in successful_children
        }
        rows = session.execute(
            select(
                DemandRunItemResult,
                DemandCalculationRun,
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
                    calculation_ids
                ),
                DemandCalculationRun.is_current_attempt.is_(
                    True
                ),
                DemandRunItemResult.calculation_status.in_(
                    {
                        ItemCalculationStatus.CALCULATED,
                        ItemCalculationStatus.FALLBACK,
                    }
                ),
            )
        ).all()
        return {
            (
                run.calculation_id,
                result.spare_part_id,
            ): (result, run)
            for result, run in rows
        }

    @staticmethod
    def _source_snapshot(
        result: DemandRunItemResult,
    ) -> dict[str, Any]:
        decimal_fields = (
            "target_service_level",
            "expected_demand",
            "variance",
            "standard_deviation",
            "p50",
            "p80",
            "p90",
            "p95",
            "p99",
            "target_quantile_demand",
            "gross_replacement_demand",
            "repair_pipeline_demand",
            "repair_pipeline_peak",
            "net_consumption_demand",
            "recommended_spare_quantity",
            "on_hand_quantity",
            "available_quantity",
            "in_transit_quantity",
            "safety_stock_reserved",
            "usable_inventory",
            "net_demand_gap",
            "inventory_coverage_rate",
            "minimum_inventory_point",
            "maximum_simultaneous_gap",
            "common_shock_demand",
        )
        snapshot: dict[str, Any] = {
            "result_id": result.id,
            "calculation_run_id": (
                result.calculation_run_id
            ),
            "spare_part_id": result.spare_part_id,
            "spare_part_code": (
                result.spare_part_code_snapshot
            ),
            "spare_part_name": (
                result.spare_part_name_snapshot
            ),
            "criticality_level": (
                result.criticality_level
            ),
            "calculation_status": _enum_value(
                result.calculation_status
            ),
            "selected_model_type": _enum_value(
                result.selected_model_type
            ),
            "failure_process_mode": _enum_value(
                result.failure_process_mode
            ),
            "selected_reliability_profile_id": (
                result.selected_reliability_profile_id
            ),
            "selected_repair_profile_id": (
                result.selected_repair_profile_id
            ),
            "selection_reason_json": _snapshot_json(
                result.selection_reason_json
            ),
            "is_manually_overridden": (
                result.is_manually_overridden
            ),
            "shortage_risk_level": _enum_value(
                result.shortage_risk_level
            ),
        }
        for field_name in decimal_fields:
            snapshot[field_name] = _decimal_string(
                getattr(result, field_name)
            )
        return snapshot

    @staticmethod
    def _inventory_snapshot(
        result: DemandRunItemResult,
    ) -> dict[str, str | None]:
        fields = (
            "on_hand_quantity",
            "available_quantity",
            "in_transit_quantity",
            "safety_stock_reserved",
            "usable_inventory",
            "net_demand_gap",
            "inventory_coverage_rate",
            "minimum_inventory_point",
            "maximum_simultaneous_gap",
        )
        return {
            field_name: _decimal_string(
                getattr(result, field_name)
            )
            for field_name in fields
        }

    @staticmethod
    def _decision_snapshot(
        decision: Any,
    ) -> dict[str, Any]:
        return {
            "id": decision.id,
            "source_child_id": (
                decision.source_child_id
            ),
            "selected_child_id": (
                decision.selected_child_id
            ),
            "original_quantity": _decimal_string(
                decision.original_quantity
            ),
            "final_quantity": _decimal_string(
                decision.final_quantity
            ),
            "decision_type": _enum_value(
                decision.decision_type
            ),
            "reason": decision.reason,
            "risk": decision.risk,
            "requires_admin_confirmation": (
                decision.requires_admin_confirmation
            ),
            "confirmed_by_admin": (
                decision.confirmed_by_admin
            ),
            "risk_rule_version": (
                decision.risk_rule_version
            ),
            "decided_by_user_id": (
                decision.decided_by_user_id
            ),
            "decided_by_request_id": (
                decision.decided_by_request_id
            ),
            "version": decision.version,
            "created_at": (
                decision.created_at.isoformat()
            ),
            "updated_at": (
                decision.updated_at.isoformat()
            ),
        }

    @staticmethod
    def _interval_snapshot(
        *,
        system_source_child_id: int,
        selected_child_id: int,
        children: list[CalculationGroupChild],
        results: dict[
            tuple[int, int],
            tuple[
                DemandRunItemResult,
                DemandCalculationRun,
            ],
        ],
        spare_part_id: int,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for child in children:
            pair = results.get(
                (
                    child.calculation_id,
                    spare_part_id,
                )
            )
            if pair is None:
                continue
            result, _ = pair
            candidates.append(
                {
                    "child_id": child.id,
                    "candidate_key": (
                        child.candidate_key
                    ),
                    "reliability_model": (
                        child.reliability_model.value
                    ),
                    "execution_mode": (
                        child.execution_mode.value
                    ),
                    "recommended_quantity": (
                        _decimal_string(
                            result
                            .recommended_spare_quantity
                        )
                    ),
                    "p50": _decimal_string(
                        result.p50
                    ),
                    "p80": _decimal_string(
                        result.p80
                    ),
                    "p90": _decimal_string(
                        result.p90
                    ),
                    "p95": _decimal_string(
                        result.p95
                    ),
                    "p99": _decimal_string(
                        result.p99
                    ),
                    "warnings": list(
                        result.warning_codes_json or []
                    ),
                }
            )
        candidates.sort(
            key=lambda item: (
                item["candidate_key"],
                item["child_id"],
            )
        )
        selected_candidate = next(
            (
                candidate
                for candidate in candidates
                if candidate["child_id"]
                == selected_child_id
            ),
            None,
        )
        if selected_candidate is None:
            raise BusinessValidationError(
                "decision source is invalid",
                code=(
                    "DEMAND_LIST_DECISION_SOURCE_INVALID"
                ),
                details={
                    "selected_child_id": (
                        selected_child_id
                    ),
                    "reason": (
                        "selected_child_has_no_result"
                    ),
                },
            )
        return {
            "system_source_child_id": (
                system_source_child_id
            ),
            "selected_child_id": selected_child_id,
            "selected_p50": (
                selected_candidate["p50"]
            ),
            "selected_p80": (
                selected_candidate["p80"]
            ),
            "selected_p90": (
                selected_candidate["p90"]
            ),
            "selected_p95": (
                selected_candidate["p95"]
            ),
            "selected_p99": (
                selected_candidate["p99"]
            ),
            "candidates": candidates,
        }

    @staticmethod
    def _read_model(
        demand_list: Any,
    ) -> DemandListRead:
        response = (
            DemandListRead.model_validate(
                demand_list
            )
            .model_copy(deep=True)
        )
        response.items.sort(
            key=lambda item: item.id
        )
        response.events.sort(
            key=lambda event: (
                event.occurred_at,
                event.id,
            )
        )
        return response

    def get(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
    ) -> DemandListRead:
        demand_list = self.repository.get(
            session,
            actor.tenant_id,
            demand_list_id,
        )
        if demand_list is None:
            raise NotFoundError(
                "demand_list",
                demand_list_id,
            )
        return self._read_model(demand_list)

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int = 1,
        page_size: int = 20,
        status: DemandListStatus | str | None = None,
        lineage_id: str | None = None,
    ) -> PageData[DemandListSummaryRead]:
        rows, total = self.repository.list_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            lineage_id=lineage_id,
        )
        items = [
            DemandListSummaryRead.model_validate(row)
            for row in rows
        ]
        items.sort(
            key=lambda item: (
                item.created_at,
                item.id,
            ),
            reverse=True,
        )
        return PageData[DemandListSummaryRead](
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            pages=(
                ceil(total / page_size)
                if total
                else 0
            ),
        )

    @staticmethod
    def _risk_evidence(
        item: Any,
    ) -> tuple[
        int,
        int,
        Decimal,
        tuple[DecisionCandidateEvidence, ...],
    ]:
        interval = item.interval_snapshot_json or {}
        source = item.source_snapshot_json or {}
        decision = item.decision_snapshot_json or {}
        source_child_id = interval.get(
            "system_source_child_id"
        )
        decision_source_child_id = decision.get(
            "source_child_id"
        )
        selected_child_id = interval.get(
            "selected_child_id"
        )
        selected_quantity_raw = source.get(
            "recommended_spare_quantity"
        )
        candidate_rows = interval.get("candidates")

        if (
            source_child_id is None
            or decision_source_child_id is None
            or source_child_id
            != decision_source_child_id
            or selected_child_id is None
            or selected_quantity_raw is None
            or not isinstance(candidate_rows, list)
        ):
            raise BusinessValidationError(
                "demand list source is invalid",
                code="DEMAND_LIST_SOURCE_INVALID",
                details={
                    "item_id": item.id,
                    "reason": "risk_snapshot_incomplete",
                },
            )

        try:
            candidates = tuple(
                DecisionCandidateEvidence(
                    child_id=int(candidate["child_id"]),
                    recommended_quantity=Decimal(
                        candidate[
                            "recommended_quantity"
                        ]
                    ),
                    p50=(
                        Decimal(candidate["p50"])
                        if candidate.get("p50")
                        is not None
                        else None
                    ),
                    p99=(
                        Decimal(candidate["p99"])
                        if candidate.get("p99")
                        is not None
                        else None
                    ),
                    warnings=tuple(
                        candidate.get("warnings") or ()
                    ),
                )
                for candidate in candidate_rows
            )
            selected_quantity = Decimal(
                selected_quantity_raw
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise BusinessValidationError(
                "demand list source is invalid",
                code="DEMAND_LIST_SOURCE_INVALID",
                details={
                    "item_id": item.id,
                    "reason": "risk_snapshot_invalid",
                },
            ) from exc

        return (
            int(source_child_id),
            int(selected_child_id),
            selected_quantity,
            candidates,
        )

    def update_item(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
        item_id: int,
        *,
        expected_version: int,
        final_quantity: Decimal,
        adjustment_reason: str,
    ) -> DemandListRead:
        self._require_contributor(actor)

        reason = adjustment_reason.strip()
        if not reason:
            raise BusinessValidationError(
                "adjustment reason is required",
                code=(
                    "DEMAND_LIST_ADJUSTMENT_REASON_REQUIRED"
                ),
            )
        if len(reason) > 1000:
            raise BusinessValidationError(
                "adjustment reason is invalid",
                code=(
                    "DEMAND_LIST_ADJUSTMENT_REASON_INVALID"
                ),
            )
        if final_quantity < 0:
            raise BusinessValidationError(
                "final quantity is invalid",
                code="DEMAND_LIST_QUANTITY_INVALID",
            )
        if expected_version < 1:
            raise BusinessValidationError(
                "expected version is invalid",
                code="DEMAND_LIST_VERSION_INVALID",
            )

        normalized_quantity = final_quantity.quantize(
            _SNAPSHOT_DECIMAL_QUANTUM
        )

        try:
            demand_list = self.repository.get_for_update(
                session,
                actor.tenant_id,
                demand_list_id,
            )
            if demand_list is None:
                raise NotFoundError(
                    "demand_list",
                    demand_list_id,
                )
            if (
                demand_list.status
                is not DemandListStatus.DRAFT
            ):
                raise ConflictError(
                    "demand list is not editable",
                    code="DEMAND_LIST_NOT_EDITABLE",
                )
            if demand_list.version != expected_version:
                raise ConflictError(
                    "demand list version conflict",
                    code="DEMAND_LIST_VERSION_CONFLICT",
                    details={
                        "expected_version": (
                            expected_version
                        ),
                        "actual_version": (
                            demand_list.version
                        ),
                        "conflict_object": "demand_list",
                        "retryable": False,
                    },
                )

            item = self.item_repository.get_for_update(
                session,
                actor.tenant_id,
                demand_list_id,
                item_id,
            )
            if item is None:
                raise NotFoundError(
                    "demand_list_item",
                    item_id,
                )

            (
                source_child_id,
                selected_child_id,
                selected_quantity,
                candidates,
            ) = self._risk_evidence(item)
            evaluation = evaluate_decision_risk(
                source_child_id=source_child_id,
                selected_child_id=selected_child_id,
                source_quantity=item.original_quantity,
                selected_quantity=selected_quantity,
                final_quantity=normalized_quantity,
                criticality_level=(
                    item.criticality_level_snapshot
                ),
                successful_candidates=candidates,
            )

            previous_quantity = item.final_quantity
            previous_item_version = item.version

            item.final_quantity = normalized_quantity
            item.decision_type = (
                evaluation.decision_type
            )
            item.decision_reason = reason
            item.decision_risk = evaluation.risk
            item.requires_admin_confirmation = (
                evaluation
                .requires_admin_confirmation
            )
            item.confirmed_by_admin = False
            item.risk_rule_version = (
                evaluation.rule_version
            )
            item.version += 1
            demand_list.version += 1
            session.flush()

            self.repository.append_event(
                session,
                actor.tenant_id,
                demand_list_id=demand_list.id,
                event_type=(
                    DemandListEventType.ITEM_UPDATED
                ),
                actor_user_id=actor.user_id,
                actor_roles=[actor.role.value],
                request_id=actor.request_id,
                before_summary={
                    "item_id": item.id,
                    "final_quantity": (
                        _decimal_string(
                            previous_quantity
                        )
                    ),
                    "version": previous_item_version,
                },
                after_summary={
                    "item_id": item.id,
                    "final_quantity": (
                        _decimal_string(
                            normalized_quantity
                        )
                    ),
                    "version": item.version,
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return self.get(
            session,
            actor,
            demand_list_id,
        )

    def create_from_group(
        self,
        session: Session,
        actor: ActorContext,
        *,
        calculation_group_id: int,
        name: str,
        description: str | None,
        idempotency_key: str,
    ) -> DemandListRead:
        self._require_contributor(actor)
        payload = DemandListCreateRequest(
            calculation_group_id=(
                calculation_group_id
            ),
            name=name,
            description=description,
        )
        clean_key = idempotency_key.strip()
        if not clean_key:
            raise BusinessValidationError(
                "idempotency key is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
        if len(clean_key) > 128:
            raise BusinessValidationError(
                "idempotency key is invalid",
                code="INVALID_IDEMPOTENCY_KEY",
            )
        request_hash = self._request_hash(
            calculation_group_id=(
                payload.calculation_group_id
            ),
            name=payload.name,
            description=payload.description,
        )
        existing = (
            self.repository
            .get_event_by_idempotency_key(
                session,
                actor.tenant_id,
                clean_key,
            )
        )
        if existing is not None:
            return self._idempotent_response(
                existing,
                request_hash,
            )

        try:
            locked = (
                self.calculation_group_service
                .group_repository.get_for_update(
                    session,
                    actor.tenant_id,
                    payload.calculation_group_id,
                )
            )
            if locked is None:
                raise NotFoundError(
                    "calculation_group",
                    payload.calculation_group_id,
                )
            comparison = (
                self.calculation_group_service.comparison(
                    session,
                    actor,
                    payload.calculation_group_id,
                )
            )
            incomplete = sorted(
                row.spare_part_id
                for row in comparison.rows
                if row.decision is None
            )
            if incomplete:
                raise BusinessValidationError(
                    "calculation decisions are incomplete",
                    code=(
                        "DEMAND_LIST_DECISIONS_INCOMPLETE"
                    ),
                    details={
                        "spare_part_ids": incomplete,
                    },
                )

            decision_models = {
                decision.spare_part_id: decision
                for decision in session.scalars(
                    select(CalculationItemDecision).where(
                        CalculationItemDecision.tenant_id
                        == actor.tenant_id,
                        CalculationItemDecision.group_id
                        == payload.calculation_group_id,
                    )
                ).all()
            }

            group = (
                self.calculation_group_service.get(
                    session,
                    actor,
                    payload.calculation_group_id,
                )
            )
            all_child_by_id = {
                child.id: child
                for child in group.children
            }
            successful_children = (
                self._successful_children(group)
            )
            successful_child_by_id = {
                child.id: child
                for child in successful_children
            }
            results = self._result_map(
                session,
                actor,
                successful_children,
            )

            selected_sources: list[
                tuple[
                    Any,
                    CalculationGroupChild,
                    DemandRunItemResult,
                    DemandCalculationRun,
                    SparePart,
                ]
            ] = []
            for row in sorted(
                comparison.rows,
                key=lambda item: item.spare_part_id,
            ):
                decision = decision_models.get(
                    row.spare_part_id
                )
                if decision is None:
                    raise BusinessValidationError(
                        "calculation decisions are incomplete",
                        code=(
                            "DEMAND_LIST_DECISIONS_INCOMPLETE"
                        ),
                        details={
                            "spare_part_ids": [
                                row.spare_part_id
                            ],
                        },
                    )

                spare = session.scalar(
                    select(SparePart).where(
                        SparePart.tenant_id
                        == actor.tenant_id,
                        SparePart.id
                        == row.spare_part_id,
                    )
                )
                if spare is None:
                    raise BusinessValidationError(
                        "demand list source is invalid",
                        code="DEMAND_LIST_SOURCE_INVALID",
                        details={
                            "spare_part_id": (
                                row.spare_part_id
                            ),
                            "reason": (
                                "spare_part_not_found"
                            ),
                        },
                    )
                if not (spare.unit or "").strip():
                    raise BusinessValidationError(
                        "demand list source is invalid",
                        code="DEMAND_LIST_SOURCE_INVALID",
                        details={
                            "spare_part_id": spare.id,
                            "reason": (
                                "spare_part_unit_missing"
                            ),
                        },
                    )

                selected_child_id = (
                    decision.selected_child_id
                )
                child = all_child_by_id.get(
                    selected_child_id
                )
                if child is None:
                    raise BusinessValidationError(
                        "decision source is invalid",
                        code=(
                            "DEMAND_LIST_DECISION_SOURCE_INVALID"
                        ),
                        details={
                            "spare_part_id": spare.id,
                            "selected_child_id": (
                                selected_child_id
                            ),
                            "reason": (
                                "selected_child_not_found"
                            ),
                        },
                    )
                if not child.is_current_attempt:
                    raise BusinessValidationError(
                        "decision source is invalid",
                        code=(
                            "DEMAND_LIST_DECISION_SOURCE_INVALID"
                        ),
                        details={
                            "spare_part_id": spare.id,
                            "selected_child_id": child.id,
                            "reason": (
                                "selected_child_not_current"
                            ),
                        },
                    )
                if (
                    child.id
                    not in successful_child_by_id
                ):
                    raise BusinessValidationError(
                        "decision source is invalid",
                        code=(
                            "DEMAND_LIST_DECISION_SOURCE_INVALID"
                        ),
                        details={
                            "spare_part_id": spare.id,
                            "selected_child_id": child.id,
                            "reason": (
                                "selected_child_not_successful"
                            ),
                        },
                    )

                pair = results.get(
                    (
                        child.calculation_id,
                        row.spare_part_id,
                    )
                )
                if pair is None:
                    raise BusinessValidationError(
                        "decision source is invalid",
                        code=(
                            "DEMAND_LIST_DECISION_SOURCE_INVALID"
                        ),
                        details={
                            "spare_part_id": spare.id,
                            "selected_child_id": child.id,
                            "reason": (
                                "selected_child_has_no_result"
                            ),
                        },
                    )

                result, run = pair
                selected_sources.append(
                    (
                        decision,
                        child,
                        result,
                        run,
                        spare,
                    )
                )

            demand_list = (
                self.repository.create_version(
                    session,
                    actor.tenant_id,
                    {
                        "name": payload.name,
                        "description": (
                            payload.description
                        ),
                        "scenario_version_id": (
                            group.scenario_version_id
                        ),
                        "calculation_group_id": group.id,
                        "status": (
                            DemandListStatus.DRAFT
                        ),
                        "is_current": False,
                        "created_by_user_id": (
                            actor.user_id
                        ),
                        "created_by_request_id": (
                            actor.request_id
                        ),
                    },
                )
            )
            for (
                decision,
                child,
                result,
                run,
                spare,
            ) in selected_sources:
                self.repository.add_item(
                    session,
                    actor.tenant_id,
                    demand_list_id=demand_list.id,
                    spare_part_id=spare.id,
                    original_quantity=(
                        decision.original_quantity
                    ),
                    final_quantity=(
                        decision.final_quantity
                    ),
                    source_snapshot=(
                        self._source_snapshot(result)
                    ),
                    spare_part_code_snapshot=(
                        result
                        .spare_part_code_snapshot
                    ),
                    spare_part_name_snapshot=(
                        result
                        .spare_part_name_snapshot
                    ),
                    spare_part_unit_snapshot=(
                        spare.unit
                    ),
                    criticality_level_snapshot=(
                        result.criticality_level
                    ),
                    source_calculation_group_id=(
                        group.id
                    ),
                    source_group_child_id=child.id,
                    source_calculation_id=(
                        child.calculation_id
                    ),
                    source_calculation_run_id=run.id,
                    source_result_id=result.id,
                    reliability_model=(
                        result.selected_model_type
                        or child.reliability_model
                    ),
                    execution_mode=(
                        child.execution_mode
                    ),
                    decision_type=(
                        decision.decision_type
                    ),
                    decision_reason=decision.reason,
                    decision_risk=decision.risk,
                    requires_admin_confirmation=(
                        decision
                        .requires_admin_confirmation
                    ),
                    confirmed_by_admin=(
                        decision.confirmed_by_admin
                    ),
                    risk_rule_version=(
                        decision.risk_rule_version
                    ),
                    decision_snapshot_json=(
                        self._decision_snapshot(
                            decision
                        )
                    ),
                    interval_snapshot_json=(
                        self._interval_snapshot(
                            system_source_child_id=(
                                decision.source_child_id
                            ),
                            selected_child_id=(
                                child.id
                            ),
                            children=(
                                successful_children
                            ),
                            results=results,
                            spare_part_id=spare.id,
                        )
                    ),
                    parameter_snapshot_json=(
                        _snapshot_json(
                            result
                            .parameter_snapshot_json
                        )
                    ),
                    warning_snapshot_json=list(
                        result.warning_codes_json or []
                    ),
                    inventory_snapshot_json=(
                        self._inventory_snapshot(
                            result
                        )
                    ),
                )

            event = self.repository.append_event(
                session,
                actor.tenant_id,
                demand_list_id=demand_list.id,
                event_type=DemandListEventType.CREATED,
                actor_user_id=actor.user_id,
                actor_roles=[actor.role.value],
                request_id=actor.request_id,
                idempotency_key=clean_key,
                request_hash=request_hash,
                after_summary={
                    "status": (
                        DemandListStatus.DRAFT.value
                    ),
                    "item_count": len(
                        selected_sources
                    ),
                },
                response_snapshot={
                    "id": demand_list.id,
                },
            )
            loaded = self.repository.get(
                session,
                actor.tenant_id,
                demand_list.id,
            )
            assert loaded is not None
            response = self._read_model(
                loaded
            )
            stored_response = response.model_dump(
                mode="json"
            )
            event.response_snapshot_json = (
                stored_response
            )
            session.flush()
            session.commit()
            return response
        except IntegrityError:
            session.rollback()
            winner = (
                self.repository
                .get_event_by_idempotency_key(
                    session,
                    actor.tenant_id,
                    clean_key,
                )
            )
            if winner is None:
                raise
            return self._idempotent_response(
                winner,
                request_hash,
            )
        except Exception:
            session.rollback()
            raise


demand_list_service = DemandListService()
