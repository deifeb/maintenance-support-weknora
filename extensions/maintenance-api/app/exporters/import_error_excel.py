from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.schemas.import_data import ImportIssue

_ERROR_HEADERS = [
    "工作表",
    "行号",
    "字段",
    "错误代码",
    "错误信息",
]
_SUMMARY_HEADERS = [
    "工作表",
    "总行数",
    "有效行数",
    "无效行数",
]


def build_import_error_workbook(
    *,
    errors: list[ImportIssue],
    summaries: list[dict[str, Any]],
) -> bytes:
    workbook = Workbook()
    error_sheet = workbook.active
    error_sheet.title = "导入错误"
    summary_sheet = workbook.create_sheet("导入摘要")

    error_sheet.append(_ERROR_HEADERS)
    for issue in errors:
        error_sheet.append(
            [
                issue.sheet,
                issue.row,
                issue.field,
                issue.code,
                issue.message,
            ]
        )

    summary_sheet.append(_SUMMARY_HEADERS)
    for summary in summaries:
        summary_sheet.append(
            [
                summary["name"],
                summary["total_rows"],
                summary["valid_rows"],
                summary["invalid_rows"],
            ]
        )

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
