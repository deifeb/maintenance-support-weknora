from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.models import (
    AIReviewRun,
    AISession,
    DemandCalculation,
    DemandCalculationRun,
    DemandScenarioVersion,
)
from app.models.enums import AIReportSourceType, AIReportType
from app.services.report_version_provenance import source_snapshot_digest


@dataclass(frozen=True)
class ReportSourceRecord:
    source_type: AIReportSourceType
    source_id: str
    source_version: str
    source_lineage_id: str | None
    source_digest: str | None
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ReportSourcePolicy:
    required: tuple[AIReportSourceType, ...]
    optional: tuple[AIReportSourceType, ...]

    @property
    def order(self) -> tuple[AIReportSourceType, ...]:
        return self.required + self.optional

    @property
    def allowed(self) -> frozenset[AIReportSourceType]:
        return frozenset(self.order)


_ALL_SOURCE_TYPES = tuple(AIReportSourceType)


REPORT_SOURCE_POLICIES: dict[AIReportType, ReportSourcePolicy] = {
    AIReportType.DEMAND_CALCULATION: ReportSourcePolicy(
        required=(AIReportSourceType.CALCULATION_RUN,),
        optional=(AIReportSourceType.SCENARIO_VERSION,),
    ),
    AIReportType.MODEL_COMPARISON: ReportSourcePolicy(
        required=(AIReportSourceType.CALCULATION_GROUP,),
        optional=(),
    ),
    AIReportType.DEMAND_REVIEW: ReportSourcePolicy(
        required=(AIReportSourceType.DEMAND_REVIEW,),
        optional=(AIReportSourceType.DEMAND_LIST,),
    ),
    AIReportType.INVENTORY_GAP: ReportSourcePolicy(
        required=(AIReportSourceType.DEMAND_LIST,),
        optional=(AIReportSourceType.ALLOCATION_PLAN,),
    ),
    AIReportType.ALLOCATION_PLAN: ReportSourcePolicy(
        required=(AIReportSourceType.ALLOCATION_PLAN,),
        optional=(),
    ),
    AIReportType.STOCKTAKE: ReportSourcePolicy(
        required=(AIReportSourceType.INVENTORY_STOCKTAKE,),
        optional=(),
    ),
    AIReportType.SPARE_PART_RISK: ReportSourcePolicy(
        required=(AIReportSourceType.DEMAND_LIST,),
        optional=(AIReportSourceType.DEMAND_REVIEW,),
    ),
    AIReportType.MANAGEMENT_DECISION: ReportSourcePolicy(
        required=(),
        optional=_ALL_SOURCE_TYPES,
    ),
}


def get_report_source_policy(report_type: AIReportType | str) -> ReportSourcePolicy:
    return REPORT_SOURCE_POLICIES[AIReportType(report_type)]


def build_source_records(
    *,
    ai_session: AISession | None = None,
    scenario_version: DemandScenarioVersion | None = None,
    calculation_run: DemandCalculationRun | None = None,
    calculation: DemandCalculation | None = None,
    review_run: AIReviewRun | None = None,
) -> Sequence[ReportSourceRecord]:
    candidates = (
        (
            AIReportSourceType.AI_SESSION,
            ai_session,
            lambda row: str(row.version),
            lambda row: {
                "id": row.id,
                "version": row.version,
                "session_code": row.session_code,
            },
        ),
        (
            AIReportSourceType.SCENARIO_VERSION,
            scenario_version,
            lambda row: str(row.version),
            lambda row: {
                "id": row.id,
                "version": row.version,
                "version_code": row.version_code,
                "formula_version": row.formula_version,
            },
        ),
        (
            AIReportSourceType.CALCULATION_RUN,
            calculation_run,
            lambda row: str(row.attempt_number),
            lambda row: {
                "id": row.id,
                "version": row.attempt_number,
                "calculation_id": row.calculation_id,
                "engine_version": row.engine_version,
                "input_snapshot_hash": (
                    calculation.input_snapshot_hash
                    if calculation is not None
                    else None
                ),
            },
        ),
        (
            AIReportSourceType.DEMAND_REVIEW,
            review_run,
            lambda row: str(row.version),
            lambda row: {
                "id": row.id,
                "version": row.version,
                "rule_set_version": row.rule_set_version,
                "scenario_version_id": row.scenario_version_id,
                "calculation_run_id": row.calculation_run_id,
            },
        ),
    )
    return tuple(
        ReportSourceRecord(
            source_type=source_type,
            source_id=str(row.id),
            source_version=version_for(row),
            source_lineage_id=None,
            source_digest=source_snapshot_digest(evidence_for(row)),
            evidence=evidence_for(row),
        )
        for source_type, row, version_for, evidence_for in candidates
        if row is not None
    )
