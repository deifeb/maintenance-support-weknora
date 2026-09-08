import time

import pytest
from app.exporters.ai_report_docx import export_report_docx
from app.exporters.ai_report_json import export_report_json
from app.exporters.ai_report_markdown import export_report_markdown


def _report() -> dict:
    sections = [
        {
            "section_code": f"section-{index}",
            "title": f"章节{index}",
            "content": "确定性报告内容。" * 100,
            "citations": [],
            "tables": [
                {
                    "title": "明细",
                    "columns": ["器材", "数量"],
                    "rows": [[f"SP-{row:04d}", str(row)] for row in range(50)],
                }
            ],
        }
        for index in range(17)
    ]
    return {
        "title": "性能测试报告",
        "metadata": {"version": "1.0"},
        "sections": sections,
        "citations": [],
    }


@pytest.mark.performance
def test_report_exports_complete_within_engineering_targets() -> None:
    report = _report()
    started = time.perf_counter()
    export_report_markdown(report)
    export_report_json(report)
    text_duration = time.perf_counter() - started

    started = time.perf_counter()
    content = export_report_docx(report)
    docx_duration = time.perf_counter() - started

    assert text_duration < 3.0
    assert docx_duration < 10.0
    assert content[:2] == b"PK"
