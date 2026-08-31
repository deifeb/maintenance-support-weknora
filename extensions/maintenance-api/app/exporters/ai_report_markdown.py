from typing import Any


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _format_source_entry(
    label: str,
    value: Any,
    fields: tuple[str, ...],
) -> str | None:
    if not isinstance(value, dict):
        return None
    details = [
        f"{field}={value[field]}"
        for field in fields
        if value.get(field) not in (None, "")
    ]
    if not details:
        return None
    return f"{label}({', '.join(details)})"


def _format_source_versions(report: dict[str, Any]) -> str:
    source_versions = report.get("source_versions")
    if not isinstance(source_versions, dict):
        return "Unavailable"

    parts: list[str] = []
    capture_mode = source_versions.get("capture_mode")
    if capture_mode not in (None, ""):
        parts.append(f"capture_mode={capture_mode}")

    definitions = (
        ("session", ("id", "version")),
        ("scenario_version", ("id", "version", "version_code")),
        (
            "calculation_run",
            (
                "id",
                "attempt_number",
                "engine_version",
                "formula_version",
                "input_snapshot_hash",
            ),
        ),
        ("review_run", ("id", "version", "rule_set_version")),
        ("inventory", ("snapshot_at",)),
    )
    for label, fields in definitions:
        entry = _format_source_entry(
            label,
            source_versions.get(label),
            fields,
        )
        if entry:
            parts.append(entry)

    return "; ".join(parts) or "Unavailable"


def _format_tenant_safe_citations(report: dict[str, Any]) -> str:
    parts: list[str] = []
    for citation in report.get("citations", []):
        if not isinstance(citation, dict):
            continue
        citation_id = citation.get("citation_id")
        if citation_id in (None, ""):
            continue

        text = f"[{citation_id}]"
        source_name = citation.get("source_name")
        if source_name not in (None, ""):
            text += f" {source_name}"
        page_number = citation.get("page_number")
        if page_number not in (None, ""):
            text += f" (page {page_number})"
        parts.append(text)

    return "; ".join(parts) or "None"


def _provenance_rows(report: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        ("Report version", report.get("version_number", "Unavailable")),
        ("Generated at", report.get("generated_at", "Unavailable")),
        ("Generation mode", report.get("generation_mode", "Unavailable")),
        ("Input digest", report.get("input_digest", "Unavailable")),
        ("Source versions / hashes", _format_source_versions(report)),
        (
            "Tenant-safe citations",
            _format_tenant_safe_citations(report),
        ),
    ]


def export_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report['title']}", "", "## Version provenance", ""]
    for label, value in _provenance_rows(report):
        lines.append(f"- **{label}**: {_escape(value)}")
    lines.append("")

    metadata = report.get("metadata", {})
    for key, value in metadata.items():
        lines.append(f"- **{key}**: {value}")
    if metadata:
        lines.append("")

    for section in report.get("sections", []):
        lines.extend(
            [
                f"## {section['title']}",
                "",
                str(section.get("content", "")),
                "",
            ]
        )
        for table in section.get("tables", []):
            if table.get("title"):
                lines.extend([f"**{table['title']}**", ""])
            columns = [
                str(value)
                for value in table.get("columns", [])
            ]
            if columns:
                lines.append(
                    "| "
                    + " | ".join(_escape(value) for value in columns)
                    + " |"
                )
                lines.append(
                    "| "
                    + " | ".join("---" for _ in columns)
                    + " |"
                )
                for row in table.get("rows", []):
                    lines.append(
                        "| "
                        + " | ".join(_escape(value) for value in row)
                        + " |"
                    )
                lines.append("")
        citations = section.get("citations", [])
        if citations:
            lines.extend(
                [
                    "引用："
                    + "、".join(str(value) for value in citations),
                    "",
                ]
            )

    if report.get("citations"):
        lines.extend(["## 证据与引用", ""])
        for citation in report["citations"]:
            page = (
                f"，第 {citation['page_number']} 页"
                if citation.get("page_number")
                else ""
            )
            lines.append(
                f"- [{citation['citation_id']}] "
                f"{citation.get('source_name', '')}{page}"
            )
    return "\n".join(lines).rstrip() + "\n"
