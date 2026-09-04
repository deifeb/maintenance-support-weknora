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
from app.models.enums import AIReportSourceType
from app.services.report_version_provenance import source_snapshot_digest


@dataclass(frozen=True)
class ReportSourceRecord:
    source_type: AIReportSourceType
    source_id: str
    source_version: str
    source_lineage_id: str | None
    source_digest: str | None
    evidence: dict[str, Any]


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
