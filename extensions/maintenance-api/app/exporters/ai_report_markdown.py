from typing import Any


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def export_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report['title']}", ""]
    metadata = report.get("metadata", {})
    for key, value in metadata.items():
        lines.append(f"- **{key}**: {value}")
    if metadata:
        lines.append("")

    for section in report.get("sections", []):
        lines.extend([f"## {section['title']}", "", str(section.get("content", "")), ""])
        for table in section.get("tables", []):
            if table.get("title"):
                lines.extend([f"**{table['title']}**", ""])
            columns = [str(value) for value in table.get("columns", [])]
            if columns:
                lines.append("| " + " | ".join(_escape(value) for value in columns) + " |")
                lines.append("| " + " | ".join("---" for _ in columns) + " |")
                for row in table.get("rows", []):
                    lines.append("| " + " | ".join(_escape(value) for value in row) + " |")
                lines.append("")
        citations = section.get("citations", [])
        if citations:
            lines.extend(["引用：" + "、".join(str(value) for value in citations), ""])

    if report.get("citations"):
        lines.extend(["## 证据与引用", ""])
        for citation in report["citations"]:
            page = f"，第 {citation['page_number']} 页" if citation.get("page_number") else ""
            lines.append(f"- [{citation['citation_id']}] {citation.get('source_name', '')}{page}")
    return "\n".join(lines).rstrip() + "\n"
