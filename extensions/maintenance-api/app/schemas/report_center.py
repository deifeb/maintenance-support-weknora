from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
)
from app.schemas.ai_report import (
    AIReportCitationInput,
    AIReportSectionInput,
)

ReportCenterSortBy = Literal[
    "created_at",
    "report_code",
    "title",
    "report_type",
    "job_status",
]
ReportCenterSortOrder = Literal["asc", "desc"]


class ReportCenterQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    keyword: str | None = Field(default=None, max_length=255)
    report_type: AIReportType | None = None
    job_status: AIReportJobStatus | None = None
    version_status: AIReportVersionStatus | None = None
    session_id: int | None = Field(default=None, gt=0)
    scenario_version_id: int | None = Field(default=None, gt=0)
    calculation_run_id: int | None = Field(default=None, gt=0)
    review_run_id: int | None = Field(default=None, gt=0)
    sort_by: ReportCenterSortBy = "created_at"
    sort_order: ReportCenterSortOrder = "desc"


# Frozen 05-5C1 service-test/public query contract.
ReportListQuery = ReportCenterQuery


class ReportCenterLatestVersionRead(BaseModel):
    id: int
    version_number: int
    status: AIReportVersionStatus
    created_at: datetime


class ReportCenterItemRead(BaseModel):
    report_id: int
    report_code: str
    session_id: int | None
    report_type: AIReportType
    job_status: AIReportJobStatus
    title: str
    progress_percent: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: ReportCenterLatestVersionRead | None


class ReportJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    report_type: AIReportType = (
        AIReportType.MANAGEMENT_DECISION
    )
    session_id: int | None = None
    scenario_version_id: int | None = None
    calculation_run_id: int | None = None
    review_run_id: int | None = None
    sections: list[AIReportSectionInput] = Field(
        default_factory=list
    )
    citations: list[AIReportCitationInput] = Field(
        default_factory=list
    )
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class ReportVersionSummaryRead(BaseModel):
    id: int
    version_number: int
    status: AIReportVersionStatus
    template_version: str
    content_digest: str


class ReportJobStatusRead(BaseModel):
    report_id: int
    report_code: str
    report_type: AIReportType
    job_status: AIReportJobStatus
    title: str
    progress_percent: int
    error_code: str | None
    latest_version: ReportVersionSummaryRead


# Compatibility aliases keep the public schema vocabulary unsurprising
# without widening the serialized list payload.
ReportCenterListItem = ReportCenterItemRead
ReportCenterLatestVersion = ReportCenterLatestVersionRead
