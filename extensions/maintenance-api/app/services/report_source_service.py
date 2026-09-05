from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError, NotFoundError
from app.models.enums import AIReportSourceType, AIReportType
from app.repositories.ai_review_repository import AIReviewRepository
from app.repositories.ai_session_repository import AISessionRepository
from app.repositories.allocation_repository import AllocationRepository
from app.repositories.calculation_group_repository import CalculationGroupRepository
from app.repositories.demand_calculation_repository import DemandCalculationRunRepository
from app.repositories.demand_list_repository import DemandListRepository
from app.repositories.demand_review_repository import DemandReviewRepository
from app.repositories.demand_scenario_repository import DemandScenarioVersionRepository
from app.repositories.inventory_stocktake_repository import InventoryStocktakeRepository
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import ActorContext
from app.services.report_source_policy import (
    ReportSourceRecord,
    build_source_records,
    get_report_source_policy,
)
from app.services.report_version_provenance import source_snapshot_digest


@dataclass(frozen=True)
class ResolvedReportSources:
    records: tuple[ReportSourceRecord, ...]
    session_id: int | None
    scenario_version_id: int | None
    calculation_run_id: int | None
    review_run_id: int | None


@dataclass(frozen=True)
class _NormalizedSource:
    source_id: int
    version: str | None
    legacy_review: bool = False


def _conflict(message: str, *, details: dict[str, Any] | None = None) -> None:
    raise BusinessValidationError(
        f"REPORT_SOURCE_CONFLICT: {message}",
        code="REPORT_SOURCE_CONFLICT",
        details=details,
    )


def _required(report_type: AIReportType, missing: list[AIReportSourceType]) -> None:
    raise BusinessValidationError(
        "REPORT_SOURCE_REQUIRED: required report source is missing",
        code="REPORT_SOURCE_REQUIRED",
        details={
            "report_type": report_type.value,
            "missing_source_types": [source_type.value for source_type in missing],
        },
    )


def _version_conflict(
    source_type: AIReportSourceType,
    source_id: int,
    supplied: str,
    authoritative: str,
) -> None:
    error = BusinessValidationError(
        "REPORT_SOURCE_VERSION_CONFLICT: supplied source version is stale",
        code="REPORT_SOURCE_VERSION_CONFLICT",
        details={
            "source_type": source_type.value,
            "source_id": source_id,
            "supplied_version": supplied,
            "authoritative_version": authoritative,
        },
    )
    error.status_code = 409
    raise error


def _value(row: Any, field: str, default: Any = None) -> Any:
    return getattr(row, field, default)


def _fields(row: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {name: _value(row, name) for name in names}


def _safe_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).casefold()
            if (
                normalized == "path"
                or normalized.endswith("_path")
                or normalized.endswith("tenant_id")
                or any(
                    marker in normalized
                    for marker in (
                        "api_key",
                        "credential",
                        "jwt",
                        "password",
                        "secret",
                        "token",
                    )
                )
            ):
                continue
            safe[str(key)] = _safe_evidence(nested)
        return safe
    if isinstance(value, list):
        return [_safe_evidence(item) for item in value]
    return value


class ReportSourceService:
    def __init__(
        self,
        *,
        ai_session_repository: Any | None = None,
        scenario_repository: Any | None = None,
        calculation_run_repository: Any | None = None,
        calculation_group_repository: Any | None = None,
        demand_list_repository: Any | None = None,
        demand_review_repository: Any | None = None,
        allocation_repository: Any | None = None,
        stocktake_repository: Any | None = None,
        legacy_review_repository: Any | None = None,
    ) -> None:
        self.ai_session_repository = ai_session_repository or AISessionRepository()
        self.scenario_repository = scenario_repository or DemandScenarioVersionRepository()
        self.calculation_run_repository = (
            calculation_run_repository or DemandCalculationRunRepository()
        )
        self.calculation_group_repository = (
            calculation_group_repository or CalculationGroupRepository()
        )
        self.demand_list_repository = demand_list_repository or DemandListRepository()
        self.demand_review_repository = demand_review_repository or DemandReviewRepository()
        self.allocation_repository = allocation_repository or AllocationRepository()
        self.stocktake_repository = stocktake_repository or InventoryStocktakeRepository()
        self.legacy_review_repository = legacy_review_repository or AIReviewRepository()

    def resolve_for_create(
        self,
        session: Session,
        actor: ActorContext,
        payload: AIReportCreateRequest,
    ) -> ResolvedReportSources:
        report_type = AIReportType(payload.report_type)
        normalized = self._normalize(payload)
        policy = get_report_source_policy(report_type)
        disallowed = set(normalized) - policy.allowed
        if disallowed:
            _conflict(
                "source type is not allowed for report type",
                details={
                    "report_type": report_type.value,
                    "source_types": sorted(row.value for row in disallowed),
                },
            )
        missing = [source_type for source_type in policy.required if source_type not in normalized]
        if missing:
            _required(report_type, missing)

        rows = self._read_sources(session, actor.tenant_id, policy.order, normalized)
        self._add_inherited_sources(
            session,
            actor.tenant_id,
            report_type,
            normalized,
            rows,
        )
        self._validate_linked_sources(report_type, rows)

        records = tuple(
            self._build_record(
                session,
                actor.tenant_id,
                source_type,
                normalized[source_type],
                rows[source_type],
            )
            for source_type in policy.order
            if source_type in normalized
        )
        return ResolvedReportSources(
            records=records,
            session_id=(
                normalized[AIReportSourceType.AI_SESSION].source_id
                if AIReportSourceType.AI_SESSION in normalized
                else None
            ),
            scenario_version_id=(
                normalized[AIReportSourceType.SCENARIO_VERSION].source_id
                if AIReportSourceType.SCENARIO_VERSION in normalized
                else None
            ),
            calculation_run_id=(
                normalized[AIReportSourceType.CALCULATION_RUN].source_id
                if AIReportSourceType.CALCULATION_RUN in normalized
                else None
            ),
            review_run_id=payload.review_run_id,
        )

    def _normalize(
        self,
        payload: AIReportCreateRequest,
    ) -> dict[AIReportSourceType, _NormalizedSource]:
        normalized: dict[AIReportSourceType, _NormalizedSource] = {}
        for source in payload.source_refs:
            self._merge_source(
                normalized,
                source.type,
                _NormalizedSource(source.id, source.version),
            )

        legacy = (
            (AIReportSourceType.AI_SESSION, payload.session_id, False),
            (AIReportSourceType.SCENARIO_VERSION, payload.scenario_version_id, False),
            (AIReportSourceType.CALCULATION_RUN, payload.calculation_run_id, False),
            (AIReportSourceType.DEMAND_REVIEW, payload.review_run_id, True),
        )
        for source_type, source_id, legacy_review in legacy:
            if source_id is None:
                continue
            if legacy_review and source_type in normalized:
                _conflict(
                    "legacy review_run_id and explicit DEMAND_REVIEW identify distinct domains"
                )
            self._merge_source(
                normalized,
                source_type,
                _NormalizedSource(source_id, None, legacy_review=legacy_review),
            )
        return normalized

    @staticmethod
    def _merge_source(
        normalized: dict[AIReportSourceType, _NormalizedSource],
        source_type: AIReportSourceType,
        candidate: _NormalizedSource,
    ) -> None:
        current = normalized.get(source_type)
        if current is None:
            normalized[source_type] = candidate
            return
        versions_conflict = (
            current.version is not None
            and candidate.version is not None
            and current.version != candidate.version
        )
        if current.source_id != candidate.source_id or versions_conflict:
            _conflict(
                "multiple references for one source type disagree",
                details={"source_type": source_type.value},
            )
        if current.version is None and candidate.version is not None:
            normalized[source_type] = candidate

    def _read_sources(
        self,
        session: Session,
        tenant_id: str,
        order: tuple[AIReportSourceType, ...],
        normalized: dict[AIReportSourceType, _NormalizedSource],
    ) -> dict[AIReportSourceType, Any]:
        rows: dict[AIReportSourceType, Any] = {}
        for source_type in order:
            source = normalized.get(source_type)
            if source is None:
                continue
            row = self._read_one(session, tenant_id, source_type, source)
            if row is None:
                raise NotFoundError(source_type.value.lower(), source.source_id)
            authoritative = self._source_version(source_type, row, source.legacy_review)
            if source.version is not None and source.version != authoritative:
                _version_conflict(
                    source_type,
                    source.source_id,
                    source.version,
                    authoritative,
                )
            rows[source_type] = row
        return rows

    def _read_one(
        self,
        session: Session,
        tenant_id: str,
        source_type: AIReportSourceType,
        source: _NormalizedSource,
    ) -> Any | None:
        if source.legacy_review:
            return self.legacy_review_repository.get_run(
                session, tenant_id, source.source_id
            )
        repository = {
            AIReportSourceType.AI_SESSION: self.ai_session_repository,
            AIReportSourceType.SCENARIO_VERSION: self.scenario_repository,
            AIReportSourceType.CALCULATION_RUN: self.calculation_run_repository,
            AIReportSourceType.CALCULATION_GROUP: self.calculation_group_repository,
            AIReportSourceType.DEMAND_LIST: self.demand_list_repository,
            AIReportSourceType.DEMAND_REVIEW: self.demand_review_repository,
            AIReportSourceType.ALLOCATION_PLAN: self.allocation_repository,
            AIReportSourceType.INVENTORY_STOCKTAKE: self.stocktake_repository,
        }[source_type]
        return repository.get(session, tenant_id, source.source_id)

    def _add_inherited_sources(
        self,
        session: Session,
        tenant_id: str,
        report_type: AIReportType,
        normalized: dict[AIReportSourceType, _NormalizedSource],
        rows: dict[AIReportSourceType, Any],
    ) -> None:
        inherited: tuple[AIReportSourceType, int | None] | None = None
        if report_type is AIReportType.DEMAND_CALCULATION:
            run = rows[AIReportSourceType.CALCULATION_RUN]
            calculation = _value(run, "calculation")
            inherited = (
                AIReportSourceType.SCENARIO_VERSION,
                _value(calculation, "scenario_version_id"),
            )
        elif report_type is AIReportType.DEMAND_REVIEW:
            review_source = normalized[AIReportSourceType.DEMAND_REVIEW]
            if review_source.legacy_review:
                if AIReportSourceType.DEMAND_LIST in normalized:
                    _conflict(
                        "legacy review runs do not materialize C2D-B demand lists"
                    )
                return
            review = rows[AIReportSourceType.DEMAND_REVIEW]
            inherited = (
                AIReportSourceType.DEMAND_LIST,
                _value(review, "derived_demand_list_id"),
            )
        if inherited is None:
            return
        source_type, source_id = inherited
        supplied = normalized.get(source_type)
        if supplied is not None and supplied.source_id != source_id:
            _conflict("optional source does not match its persisted parent link")
        if source_id is None:
            if supplied is not None:
                _conflict("optional source is not materialized by its persisted parent")
            return
        if supplied is None:
            normalized[source_type] = _NormalizedSource(source_id, None)
        if source_type not in rows:
            source = normalized[source_type]
            row = self._read_one(session, tenant_id, source_type, source)
            if row is None:
                raise NotFoundError(source_type.value.lower(), source.source_id)
            if source.version is not None:
                authoritative = self._source_version(source_type, row, False)
                if source.version != authoritative:
                    _version_conflict(
                        source_type,
                        source.source_id,
                        source.version,
                        authoritative,
                    )
            rows[source_type] = row

    @staticmethod
    def _validate_linked_sources(
        report_type: AIReportType,
        rows: dict[AIReportSourceType, Any],
    ) -> None:
        demand_list = rows.get(AIReportSourceType.DEMAND_LIST)
        allocation = rows.get(AIReportSourceType.ALLOCATION_PLAN)
        review = rows.get(AIReportSourceType.DEMAND_REVIEW)
        if report_type is AIReportType.INVENTORY_GAP and allocation is not None:
            if (
                _value(allocation, "source_demand_list_id") != _value(demand_list, "id")
                or str(_value(allocation, "source_demand_list_version"))
                != str(_value(demand_list, "version_number"))
            ):
                _conflict("allocation plan does not belong to the demand-list version")
        if report_type is AIReportType.SPARE_PART_RISK and review is not None:
            if (
                _value(review, "source_demand_list_id") != _value(demand_list, "id")
                or str(_value(review, "source_demand_list_version"))
                != str(_value(demand_list, "version_number"))
            ):
                _conflict("demand review does not belong to the demand-list version")

    @staticmethod
    def _source_version(
        source_type: AIReportSourceType,
        row: Any,
        legacy_review: bool,
    ) -> str:
        del legacy_review
        field = {
            AIReportSourceType.AI_SESSION: "version",
            AIReportSourceType.SCENARIO_VERSION: "version",
            AIReportSourceType.CALCULATION_RUN: "attempt_number",
            AIReportSourceType.CALCULATION_GROUP: "version",
            AIReportSourceType.DEMAND_LIST: "version_number",
            AIReportSourceType.DEMAND_REVIEW: "version",
            AIReportSourceType.ALLOCATION_PLAN: "version",
            AIReportSourceType.INVENTORY_STOCKTAKE: "version",
        }[source_type]
        return str(_value(row, field))

    def _build_record(
        self,
        session: Session,
        tenant_id: str,
        source_type: AIReportSourceType,
        source: _NormalizedSource,
        row: Any,
    ) -> ReportSourceRecord:
        if source.legacy_review:
            return tuple(build_source_records(review_run=row))[0]
        evidence = _safe_evidence(
            jsonable_encoder(
                self._persisted_evidence(session, tenant_id, source_type, row)
            )
        )
        lineage = _value(row, "lineage_id")
        if source_type is AIReportSourceType.DEMAND_REVIEW:
            lineage = _value(row, "source_lineage_id")
        lineage_id = str(lineage) if lineage is not None else None
        return ReportSourceRecord(
            source_type=source_type,
            source_id=str(_value(row, "id")),
            source_version=self._source_version(source_type, row, False),
            source_lineage_id=lineage_id,
            source_digest=source_snapshot_digest(evidence),
            evidence=evidence,
        )

    def _persisted_evidence(
        self,
        session: Session,
        tenant_id: str,
        source_type: AIReportSourceType,
        row: Any,
    ) -> dict[str, Any]:
        if source_type is AIReportSourceType.AI_SESSION:
            return _fields(row, ("id", "version", "session_code"))
        if source_type is AIReportSourceType.SCENARIO_VERSION:
            return _fields(
                row, ("id", "version", "version_code", "formula_version")
            )
        if source_type is AIReportSourceType.CALCULATION_RUN:
            calculation = _value(row, "calculation")
            return {
                **_fields(
                    row,
                    (
                        "id",
                        "attempt_number",
                        "calculation_id",
                        "run_mode",
                        "engine_version",
                        "formula_version",
                    ),
                ),
                "input_snapshot_hash": _value(calculation, "input_snapshot_hash"),
                "inventory_snapshot_at": _value(calculation, "inventory_snapshot_at"),
            }
        if source_type is AIReportSourceType.CALCULATION_GROUP:
            children = [
                _fields(
                    child,
                    (
                        "id",
                        "candidate_key",
                        "reliability_model",
                        "execution_mode",
                        "calculation_id",
                        "attempt_number",
                        "is_primary",
                        "selection_reason",
                    ),
                )
                for child in _value(row, "current_children", ())
            ]
            decisions = [
                _fields(
                    decision,
                    (
                        "id",
                        "spare_part_id",
                        "source_child_id",
                        "selected_child_id",
                        "original_quantity",
                        "final_quantity",
                        "decision_type",
                        "reason",
                        "risk",
                        "risk_rule_version",
                        "version",
                    ),
                )
                for decision in _value(row, "decisions", ())
            ]
            return {
                **_fields(
                    row,
                    (
                        "id",
                        "version",
                        "status",
                        "scenario_version_id",
                        "primary_candidate_key",
                        "recommendation_snapshot_json",
                        "parameter_snapshot_json",
                    ),
                ),
                "candidates": children,
                "decisions": decisions,
            }
        if source_type is AIReportSourceType.DEMAND_LIST:
            items = [
                _fields(
                    item,
                    (
                        "id",
                        "version",
                        "spare_part_id",
                        "spare_part_code_snapshot",
                        "spare_part_name_snapshot",
                        "spare_part_unit_snapshot",
                        "criticality_level_snapshot",
                        "original_quantity",
                        "final_quantity",
                        "decision_type",
                        "decision_risk",
                        "risk_rule_version",
                        "decision_snapshot_json",
                        "inventory_snapshot_json",
                    ),
                )
                for item in _value(row, "items", ())
            ]
            return {
                **_fields(
                    row,
                    (
                        "id",
                        "version_number",
                        "lineage_id",
                        "status",
                        "scenario_version_id",
                        "calculation_group_id",
                        "published_at",
                    ),
                ),
                "items": items,
            }
        if source_type is AIReportSourceType.DEMAND_REVIEW:
            findings = self.demand_review_repository.list_findings(
                session, tenant_id, row.id
            )
            decisions = self.demand_review_repository.list_decisions(
                session, tenant_id, row.id
            )
            return {
                **_fields(
                    row,
                    (
                        "id",
                        "version",
                        "status",
                        "rule_set_version",
                        "input_hash",
                        "source_demand_list_id",
                        "source_demand_list_version",
                        "source_lineage_id",
                        "source_version_number",
                        "derived_demand_list_id",
                        "total_finding_count",
                        "blocking_finding_count",
                        "pending_finding_count",
                        "pending_blocking_finding_count",
                    ),
                ),
                "findings": [
                    _fields(
                        finding,
                        (
                            "id",
                            "version",
                            "finding_key",
                            "rule_code",
                            "finding_type",
                            "severity",
                            "blocking",
                            "requires_admin_acceptance",
                            "source_demand_list_item_id",
                            "effect_key",
                            "evidence_snapshot_json",
                            "suggestion_snapshot_json",
                            "decision_status",
                        ),
                    )
                    for finding in findings
                ],
                "decisions": [
                    _fields(
                        decision,
                        (
                            "id",
                            "finding_id",
                            "action",
                            "suggested_quantity",
                            "final_quantity",
                            "reason",
                            "review_version_before",
                            "review_version_after",
                            "finding_version_before",
                            "finding_version_after",
                            "before_snapshot_json",
                            "after_snapshot_json",
                            "occurred_at",
                        ),
                    )
                    for decision in decisions
                ],
            }
        if source_type is AIReportSourceType.ALLOCATION_PLAN:
            lines = self.allocation_repository.list_plan_lines(session, tenant_id, row.id)
            return {
                **_fields(
                    row,
                    (
                        "id",
                        "version",
                        "status",
                        "source_demand_list_id",
                        "source_demand_list_version",
                        "rule_id",
                        "inventory_fingerprint",
                    ),
                ),
                "lines": [
                    _fields(
                        line,
                        (
                            "id",
                            "version",
                            "demand_list_item_id",
                            "spare_part_id",
                            "demand_quantity",
                            "allocated_quantity",
                            "gap_quantity",
                            "recommended_balance_id",
                            "expected_balance_version",
                            "risks_json",
                            "status",
                        ),
                    )
                    for line in lines
                ],
            }
        lines = self.stocktake_repository.list_lines(session, tenant_id, row.id)
        return {
            **_fields(
                row,
                (
                    "id",
                    "version",
                    "status",
                    "warehouse_id",
                    "location_id",
                    "snapshot_at",
                    "confirmed_at",
                ),
            ),
            "lines": [
                _fields(
                    line,
                    (
                        "id",
                        "version",
                        "balance_id",
                        "spare_part_id",
                        "lot_id",
                        "serial_item_id",
                        "system_quantity",
                        "counted_quantity",
                        "variance_quantity",
                        "snapshot_balance_version",
                        "resolution",
                        "conflict_details_json",
                    ),
                )
                for line in lines
            ],
        }


report_source_service = ReportSourceService()
