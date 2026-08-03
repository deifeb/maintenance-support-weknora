from typing import Any

from pydantic import BaseModel, Field


class AIReportSectionInput(BaseModel):
    section_code: str
    title: str
    content: str = ""
    source_type: str = "DETERMINISTIC"
    citations: list[str] = Field(
        default_factory=list
    )
    tables: list[dict[str, Any]] = Field(
        default_factory=list
    )


class AIReportCitationInput(BaseModel):
    citation_id: str
    source_type: str = "WEKNORA_DOCUMENT"
    source_name: str
    document_version: str | None = None
    page_number: int | None = None
    chunk_reference: str | None = None
    knowledge_node: str | None = None
    database_record_json: (
        dict[str, Any] | None
    ) = None


class AIReportCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    report_type: str = (
        "MANAGEMENT_DECISION"
    )
    session_id: int | None = None
    scenario_version_id: int | None = None
    calculation_run_id: int | None = None
    review_run_id: int | None = None
    sections: list[
        AIReportSectionInput
    ] = Field(default_factory=list)
    citations: list[
        AIReportCitationInput
    ] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )
