from __future__ import annotations

import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any, Sequence

from app.models import (
    AIReportJob,
    AIReportVersion,
    AIReviewRun,
    AISession,
    DemandCalculation,
    DemandCalculationRun,
    DemandScenarioVersion,
)

SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.1"
_COMPATIBLE_AUTHORITATIVE_SCHEMA_VERSION = "1.0"
_LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.0"
_AUTHORITATIVE_CAPTURE = "AUTHORITATIVE_CREATE"
_LEGACY_CAPTURE = "LEGACY_RECONSTRUCTED"
_LEGACY_COMPLETENESS = "PERSISTED_LINKS_ONLY"
_ALLOWED_PRIVATE_SEED_KEYS = {
    "_draft_sections",
    "_draft_citations",
}
_PUBLIC_SOURCE_FIELDS = (
    "type",
    "id",
    "version",
    "lineage_id",
    "digest",
)
_LEGACY_PUBLIC_SOURCE_FIELDS = {
    "session": ("id", "version"),
    "scenario_version": ("id", "version"),
    "calculation_run": ("id",),
    "review_run": ("id", "version"),
    "inventory": (),
}

if TYPE_CHECKING:
    from app.services.report_source_policy import ReportSourceRecord


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _json_safe(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )


def seed_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    source = metadata or {}
    return copy.deepcopy(
        {
            key: value
            for key, value in source.items()
            if (
                not key.startswith("_")
                or key in _ALLOWED_PRIVATE_SEED_KEYS
            )
        }
    )


def _generation_seed(
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    seed = seed_metadata(metadata)
    return {
        "metadata": {
            key: value
            for key, value in seed.items()
            if not key.startswith("_")
        },
        "draft_sections": seed.get("_draft_sections", []),
        "draft_citations": seed.get("_draft_citations", []),
    }


def build_authoritative_source_snapshot(
    *,
    report_type: str,
    template_version: str,
    metadata: dict[str, Any] | None,
    source_records: Sequence[ReportSourceRecord] | None = None,
    ai_session: AISession | None = None,
    scenario_version: DemandScenarioVersion | None = None,
    calculation_run: DemandCalculationRun | None = None,
    calculation: DemandCalculation | None = None,
    review_run: AIReviewRun | None = None,
) -> dict[str, Any]:
    if source_records is not None:
        return _json_safe(
            {
                "schema_version": SOURCE_SNAPSHOT_SCHEMA_VERSION,
                "capture_mode": _AUTHORITATIVE_CAPTURE,
                "provenance_completeness": "AUTHORITATIVE",
                "report_type": _enum_value(report_type),
                "template_version": template_version,
                "sources": [
                    {
                        "type": record.source_type.value,
                        "id": record.source_id,
                        "version": record.source_version,
                        "lineage_id": record.source_lineage_id,
                        "digest": record.source_digest,
                        "evidence": record.evidence,
                    }
                    for record in source_records
                ],
                "generation_seed": _generation_seed(metadata),
            }
        )

    session_source = None
    if ai_session is not None:
        session_source = {
            "id": ai_session.id,
            "version": ai_session.version,
            "session_code": ai_session.session_code,
        }

    scenario_source = None
    if scenario_version is not None:
        scenario_source = {
            "id": scenario_version.id,
            "version": scenario_version.version,
            "version_code": scenario_version.version_code,
            "formula_version": scenario_version.formula_version,
            "input_schema_version": (
                scenario_version.input_schema_version
            ),
        }

    calculation_source = None
    if calculation_run is not None:
        calculation_source = {
            "id": calculation_run.id,
            "calculation_id": calculation_run.calculation_id,
            "attempt_number": calculation_run.attempt_number,
            "run_mode": _enum_value(calculation_run.run_mode),
            "engine_version": calculation_run.engine_version,
            "formula_version": calculation_run.formula_version,
            "input_snapshot_hash": (
                calculation.input_snapshot_hash
                if calculation is not None
                else None
            ),
            "inventory_snapshot_at": (
                calculation.inventory_snapshot_at
                if calculation is not None
                else None
            ),
        }

    review_source = None
    if review_run is not None:
        review_source = {
            "id": review_run.id,
            "version": review_run.version,
            "rule_set_version": review_run.rule_set_version,
            "scenario_version_id": review_run.scenario_version_id,
            "calculation_run_id": review_run.calculation_run_id,
        }

    inventory_snapshot_at = (
        calculation.inventory_snapshot_at
        if calculation is not None
        else None
    )

    return _json_safe(
        {
            "schema_version": _COMPATIBLE_AUTHORITATIVE_SCHEMA_VERSION,
            "capture_mode": _AUTHORITATIVE_CAPTURE,
            "report_type": _enum_value(report_type),
            "template_version": template_version,
            "sources": {
                "session": session_source,
                "scenario_version": scenario_source,
                "calculation_run": calculation_source,
                "review_run": review_source,
                "inventory": {
                    "snapshot_at": inventory_snapshot_at,
                },
            },
            "generation_seed": _generation_seed(metadata),
        }
    )


def build_legacy_source_snapshot(
    job: AIReportJob,
    version: AIReportVersion,
) -> dict[str, Any]:
    return _json_safe(
        {
            "schema_version": _LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "capture_mode": _LEGACY_CAPTURE,
            "provenance_completeness": _LEGACY_COMPLETENESS,
            "report_type": _enum_value(job.report_type),
            "template_version": version.template_version,
            "sources": {
                "session": (
                    {
                        "id": job.session_id,
                        "version": None,
                        "session_code": None,
                    }
                    if job.session_id is not None
                    else None
                ),
                "scenario_version": (
                    {
                        "id": version.scenario_version_id,
                        "version": None,
                        "version_code": None,
                        "formula_version": None,
                        "input_schema_version": None,
                    }
                    if version.scenario_version_id is not None
                    else None
                ),
                "calculation_run": (
                    {
                        "id": version.calculation_run_id,
                        "calculation_id": None,
                        "attempt_number": None,
                        "run_mode": None,
                        "engine_version": None,
                        "formula_version": None,
                        "input_snapshot_hash": None,
                        "inventory_snapshot_at": (
                            version.inventory_snapshot_at
                        ),
                    }
                    if version.calculation_run_id is not None
                    else None
                ),
                "review_run": (
                    {
                        "id": version.review_run_id,
                        "version": None,
                        "rule_set_version": None,
                        "scenario_version_id": None,
                        "calculation_run_id": None,
                    }
                    if version.review_run_id is not None
                    else None
                ),
                "inventory": {
                    "snapshot_at": version.inventory_snapshot_at,
                },
            },
            "generation_seed": _generation_seed(
                version.metadata_json
            ),
        }
    )


def source_snapshot_digest(
    snapshot: dict[str, Any],
) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_source_versions(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    schema_version = snapshot.get("schema_version")
    if schema_version not in {
        _LEGACY_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        SOURCE_SNAPSHOT_SCHEMA_VERSION,
    }:
        return {}

    capture_mode = snapshot.get("capture_mode")
    if not _is_public_scalar(capture_mode):
        return {}

    result: dict[str, Any] = {"capture_mode": capture_mode}
    completeness = snapshot.get("provenance_completeness")
    if completeness is not None:
        if not _is_public_scalar(completeness):
            return {}
        result["provenance_completeness"] = completeness

    if schema_version == SOURCE_SNAPSHOT_SCHEMA_VERSION:
        sources = snapshot.get("sources")
        if not isinstance(sources, list):
            return {}
        projection: list[dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, dict):
                return {}
            if any(
                not _is_public_scalar(source.get(key))
                for key in _PUBLIC_SOURCE_FIELDS
            ):
                return {}
            projection.append(
                {
                    key: source.get(key)
                    for key in _PUBLIC_SOURCE_FIELDS
                }
            )
        result["sources"] = projection
    else:
        sources = snapshot.get("sources")
        if not isinstance(sources, dict):
            return {}
        projection = {}
        for source_name, fields in _LEGACY_PUBLIC_SOURCE_FIELDS.items():
            if source_name not in sources:
                continue
            source = sources.get(source_name)
            if source is None:
                projection[source_name] = None
                continue
            if not isinstance(source, dict):
                return {}
            projection[source_name] = {
                key: source.get(key)
                for key in fields
                if key in source
                and _is_public_scalar(source.get(key))
            }
        result["sources"] = projection
    return result


def _is_public_scalar(value: Any) -> bool:
    return value is None or isinstance(
        value,
        (str, int, float, bool),
    )
