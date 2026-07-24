from io import BytesIO
from typing import Any

from docx import Document


def _add_table(document: Document, columns: list[str], rows: list[list[Any]]) -> None:
    table = document.add_table(rows=1, cols=max(1, len(columns)))
    table.style = "Table Grid"
    for index, title in enumerate(columns or ["内容"]):
        table.rows[0].cells[index].text = str(title)
    for values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(values[: len(cells)]):
            cells[index].text = str(value)


def export_report_docx(report: dict[str, Any]) -> bytes:
    document = Document()
    document.add_heading(str(report["title"]), level=0)

    metadata = report.get("metadata", {})
    _add_table(
        document,
        ["字段", "内容"],
        [[key, value] for key, value in metadata.items()]
        or [["状态", report.get("status", "DRAFT")]],
    )

    for section in report.get("sections", []):
        document.add_heading(str(section["title"]), level=1)
        document.add_paragraph(str(section.get("content", "")))
        for table_definition in section.get("tables", []):
            title = table_definition.get("title")
            if title:
                document.add_paragraph(str(title))
            _add_table(
                document,
                [str(value) for value in table_definition.get("columns", [])],
                [list(row) for row in table_definition.get("rows", [])],
            )
        citations = section.get("citations", [])
        if citations:
            document.add_paragraph("引用：" + "、".join(str(value) for value in citations))

    document.add_heading("证据与引用", level=1)
    citation_rows = []
    for citation in report.get("citations", []):
        page = "" if citation.get("page_number") is None else citation["page_number"]
        citation_rows.append(
            [citation.get("citation_id", ""), citation.get("source_name", ""), page]
        )
    _add_table(document, ["引用编号", "来源", "页码"], citation_rows or [["无", "", ""]])

    output = BytesIO()
    document.save(output)
    return output.getvalue()
