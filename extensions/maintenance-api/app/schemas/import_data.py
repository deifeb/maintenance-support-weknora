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
    warnings: list[ImportIssue] = Field(default_factory=list)
    preview: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class ImportExecutionResult(BaseModel):
    imported: bool
    created: dict[str, int]
    updated: dict[str, int]
    total_rows: int
