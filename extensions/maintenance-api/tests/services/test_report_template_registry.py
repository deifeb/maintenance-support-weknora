import pytest
from app.core.exceptions import BusinessValidationError
from app.models.enums import AIReportType
from app.services.report_template_registry import get_template


@pytest.mark.parametrize("report_type", list(AIReportType))
def test_each_report_type_resolves_explicit_template(
    report_type: AIReportType,
) -> None:
    template = get_template(report_type)

    assert template.report_type is report_type
    assert template.version == "1.0"
    assert template.sections
    assert len({section.code for section in template.sections}) == len(template.sections)


def test_unknown_template_version_fails_closed() -> None:
    with pytest.raises(BusinessValidationError) as error:
        get_template(AIReportType.DEMAND_REVIEW, "99.0")
    assert error.value.code == "REPORT_TEMPLATE_NOT_FOUND"
