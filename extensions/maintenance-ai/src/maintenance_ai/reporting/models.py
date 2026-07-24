from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportSectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    section_code: str
    title: str
    facts: dict[str, Any]
    allowed_numbers: tuple[str, ...] = ()
    allowed_citation_ids: tuple[str, ...] = ()
    target_reader: str = "MANAGER"


class ReportSectionPayload(BaseModel):
    title: str
    content: str
    citation_ids: list[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    section_code: str
    title: str
    content: str
    citation_ids: tuple[str, ...]
