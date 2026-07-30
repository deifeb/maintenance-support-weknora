from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportIssue(BaseModel):
    sheet: str | None = None
    row: int | None = None
    field: str | None = None
    code: str
    message: str


class ImportValidationResult(BaseModel):
    valid: bool
    sheet_counts: dict[str, int]
    errors: list[ImportIssue]
    warnings: list[ImportIssue] = Field(
        default_factory=list
    )
    preview: dict[
        str,
        list[dict[str, Any]],
    ] = Field(default_factory=dict)


class ImportExecutionResult(BaseModel):
    imported: bool
    created: dict[str, int]
    updated: dict[str, int]
    total_rows: int


class ImportSheetInspection(BaseModel):
    name: str
    source_headers: list[str]
    suggested_mapping: dict[str, str]
    required_fields: list[str]


class ImportTaskUploadResult(BaseModel):
    task_id: str
    status: str
    original_filename: str
    file_sha256: str
    template_version: str
    sheets: list[ImportSheetInspection]
    expires_at: datetime


class ImportPreviewRequest(BaseModel):
    mapping: dict[str, dict[str, str]]


class ImportSheetSummary(BaseModel):
    name: str
    total_rows: int
    valid_rows: int
    invalid_rows: int


class ImportTaskView(BaseModel):
    task_id: str
    status: str
    original_filename: str
    file_sha256: str
    template_version: str
    sheets: list[ImportSheetSummary]
    preview: dict[str, list[dict[str, Any]]]
    errors: list[ImportIssue]
    warnings: list[ImportIssue]
    can_execute: bool
    created_at: datetime
    expires_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: ImportExecutionResult | None = None
    error_code: str | None = None
    error_message: str | None = None
