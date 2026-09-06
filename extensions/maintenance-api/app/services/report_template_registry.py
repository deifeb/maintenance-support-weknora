from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import BusinessValidationError
from app.models.enums import AIReportType


@dataclass(frozen=True)
class ReportTemplateSection:
    code: str
    title: str


@dataclass(frozen=True)
class ReportTemplateDefinition:
    report_type: AIReportType
    version: str
    title: str
    sections: tuple[ReportTemplateSection, ...]


def _invalid(message: str) -> BusinessValidationError:
    return BusinessValidationError(message, code="REPORT_TEMPLATE_INVALID")


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(f"report template {field} must be a non-empty string")
    return value


def _load_templates() -> tuple[
    dict[tuple[AIReportType, str], ReportTemplateDefinition], dict[AIReportType, str]
]:
    path = Path(__file__).resolve().parents[2] / "config" / "report-templates.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise _invalid("report template configuration could not be loaded") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("templates"), list):
        raise _invalid("report templates must be a list")

    templates: dict[tuple[AIReportType, str], ReportTemplateDefinition] = {}
    latest_versions: dict[AIReportType, str] = {}
    for raw_template in raw["templates"]:
        if not isinstance(raw_template, dict):
            raise _invalid("each report template must be a mapping")
        try:
            report_type = AIReportType(raw_template.get("report_type"))
        except (TypeError, ValueError) as error:
            raise _invalid("report template has an unknown report type") from error
        version = _required_string(raw_template.get("version"), "version")
        title = _required_string(raw_template.get("title"), "title")
        raw_sections = raw_template.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise _invalid("report template sections must be a non-empty list")

        sections: list[ReportTemplateSection] = []
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                raise _invalid("report template section must be a mapping")
            sections.append(
                ReportTemplateSection(
                    code=_required_string(raw_section.get("code"), "section code"),
                    title=_required_string(raw_section.get("title"), "section title"),
                )
            )
        if len({section.code for section in sections}) != len(sections):
            raise _invalid("report template has duplicate section codes")
        key = (report_type, version)
        if key in templates:
            raise _invalid("report template has duplicate report type and version")
        templates[key] = ReportTemplateDefinition(report_type, version, title, tuple(sections))
        latest_versions[report_type] = max(latest_versions.get(report_type, version), version)
    return templates, latest_versions


_templates, _latest_versions = _load_templates()


def get_template(report_type: AIReportType, version: str | None = None) -> ReportTemplateDefinition:
    try:
        resolved_version = version or _latest_versions[report_type]
        return _templates[(report_type, resolved_version)]
    except KeyError as error:
        raise BusinessValidationError(
            "report template was not found", code="REPORT_TEMPLATE_NOT_FOUND"
        ) from error


def list_templates() -> tuple[ReportTemplateDefinition, ...]:
    return tuple(
        sorted(_templates.values(), key=lambda item: (item.report_type.value, item.version))
    )
