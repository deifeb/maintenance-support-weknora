from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    AIReportJobStatus,
    AIReportType,
    AIReportVersionStatus,
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


# Compatibility aliases keep the public schema vocabulary unsurprising
# without widening the serialized list payload.
ReportCenterListItem = ReportCenterItemRead
ReportCenterLatestVersion = ReportCenterLatestVersionRead
