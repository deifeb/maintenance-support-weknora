from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

_CITATION_PATTERN = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])[-+]?\d+(?:\.\d+)?%?")


@dataclass(frozen=True, slots=True)
class ReportValidationFindingDraft:
    code: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


def _normalize_number(value: str) -> str:
    raw = value.strip()
    suffix = "%" if raw.endswith("%") else ""
    raw = raw.removesuffix("%")
    try:
        normalized = format(Decimal(raw).normalize(), "f")
    except InvalidOperation:
        return value
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"-0", "+0", ""}:
        normalized = "0"
    return normalized + suffix


class AIReportValidationService:
    def validate_content(
        self,
        *,
        sections: Iterable[dict[str, Any]],
        allowed_numbers: set[str],
        valid_citation_ids: set[str],
    ) -> list[ReportValidationFindingDraft]:
        normalized_allowed = {_normalize_number(str(value)) for value in allowed_numbers}
        findings: list[ReportValidationFindingDraft] = []
        seen: set[tuple[str, str, str]] = set()

        for section in sections:
            code = str(section.get("section_code", "unknown"))
            content = str(section.get("content", ""))
            citations = set(_CITATION_PATTERN.findall(content))
            citations.update(str(value) for value in section.get("citations", []))
            for citation_id in sorted(citations - valid_citation_ids):
                key = ("REPORT_CITATION_INVALID", code, citation_id)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    ReportValidationFindingDraft(
                        code="REPORT_CITATION_INVALID",
                        severity="ERROR",
                        message=f"章节 {code} 引用了不存在或无权访问的证据 {citation_id}",
                        details={"section_code": code, "citation_id": citation_id},
                    )
                )

            content_without_citations = _CITATION_PATTERN.sub("", content)
            table_values: list[str] = []
            for table in section.get("tables", []):
                table_values.extend(str(value) for value in table.get("columns", []))
                for row in table.get("rows", []):
                    table_values.extend(str(value) for value in row)
            number_source = "\n".join([content_without_citations, *table_values])
            for raw_number in _NUMBER_PATTERN.findall(number_source):
                normalized = _normalize_number(raw_number)
                if normalized in normalized_allowed:
                    continue
                key = ("REPORT_UNSUPPORTED_NUMBER", code, normalized)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    ReportValidationFindingDraft(
                        code="REPORT_UNSUPPORTED_NUMBER",
                        severity="ERROR",
                        message=f"章节 {code} 包含未由固定快照支持的数字 {raw_number}",
                        details={"section_code": code, "number": raw_number},
                    )
                )
        return findings


ai_report_validation_service = AIReportValidationService()
