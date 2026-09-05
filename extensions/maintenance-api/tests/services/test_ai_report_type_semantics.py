import pytest
from app.models.enums import AIReportSourceType, AIReportType
from app.schemas.report_center import (
    ReportCenterQuery,
    ReportJobCreateRequest,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    "value",
    [
        "DEMAND_CALCULATION",
        "MODEL_COMPARISON",
        "DEMAND_REVIEW",
        "INVENTORY_GAP",
        "ALLOCATION_PLAN",
        "STOCKTAKE",
        "SPARE_PART_RISK",
        "MANAGEMENT_DECISION",
    ],
)
def test_all_report_types_are_accepted(value: str) -> None:
    assert AIReportType(value).value == value


def test_report_source_ref_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReportJobCreateRequest(
            title="risk",
            report_type="SPARE_PART_RISK",
            source_refs=[{"type": "DEMAND_LIST", "id": 1, "extra": True}],
        )


def test_report_center_query_accepts_source_filters() -> None:
    query = ReportCenterQuery(source_type="DEMAND_LIST", source_id=7, source_version="3")

    assert query.source_type is AIReportSourceType.DEMAND_LIST
    assert query.source_id == 7
    assert query.source_version == "3"
