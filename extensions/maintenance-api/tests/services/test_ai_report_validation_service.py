from app.services.ai_report_validation_service import ai_report_validation_service


def test_report_validation_rejects_unsupported_numbers_and_citations() -> None:
    findings = ai_report_validation_service.validate_content(
        sections=[
            {
                "section_code": "management_summary",
                "content": "建议准备 9 件器材，并引用 [E-999]。",
            }
        ],
        allowed_numbers={"8"},
        valid_citation_ids={"E-001"},
    )

    assert {finding.code for finding in findings} == {
        "REPORT_UNSUPPORTED_NUMBER",
        "REPORT_CITATION_INVALID",
    }
    assert all(not finding.resolved for finding in findings)
