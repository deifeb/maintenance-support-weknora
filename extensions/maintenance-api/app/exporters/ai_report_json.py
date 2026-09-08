import json
from typing import Any

_REPORT_FIELDS = (
    "report_id",
    "report_code",
    "report_type",
    "title",
    "status",
    "version_id",
    "version_number",
    "parent_version_id",
    "template_version",
    "input_digest",
    "generation_mode",
    "generated_at",
    "source_versions",
    "metadata",
    "sections",
    "citations",
)
_PROVENANCE_FIELDS = (
    "report_code",
    "report_type",
    "version_number",
    "template_version",
    "generated_at",
    "generation_mode",
    "input_digest",
    "source_versions",
    "citations",
)


def export_report_json(report: dict[str, Any]) -> str:
    exported = {
        field: report[field]
        for field in _REPORT_FIELDS
        if field in report
    }
    exported["provenance"] = {
        field: report.get(field)
        for field in _PROVENANCE_FIELDS
    }
    return json.dumps(
        exported,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )
