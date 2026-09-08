from typing import Any

from pydantic import BaseModel, Field


class AIDemandReviewRequest(BaseModel):
    items: list[dict[str, Any]] = Field(min_length=1)
    session_id: int | None = None
    calculation_run_id: int | None = None
    scenario_snapshot: dict[str, Any] = Field(
        default_factory=lambda: {
            "scenario_version_id": None,
            "stages": [{"code": "S1"}],
        }
    )
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)


class AIReviewFindingRead(BaseModel):
    id: int | None = None
    rule_code: str
    category: str
    title: str
    message: str
    severity: str
    blocking_level: str
    status: str = "OPEN"
    spare_part_id: int | None = None
    suggested_actions: list[str] = Field(default_factory=list)


class AIReviewFindingActionRequest(BaseModel):
    comment: str | None = None
