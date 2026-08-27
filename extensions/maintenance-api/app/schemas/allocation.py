from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.snapshot_service import snapshot_service

_WEIGHT_QUANTUM = Decimal("0.000001")


def _decimal_value(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("decimal values must not use binary floating point")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("value must be an exact decimal") from exc
    if not decimal_value.is_finite():
        raise ValueError("value must be finite")
    return decimal_value


def _weights(value: Any) -> dict[str, Decimal]:
    if not isinstance(value, dict) or not value:
        raise ValueError("weights cannot be empty")
    normalized: dict[str, Decimal] = {}
    for key, item in value.items():
        name = str(key).strip()
        if not name:
            raise ValueError("weight name cannot be blank")
        weight = _decimal_value(item)
        if weight < 0:
            raise ValueError("weights must be non-negative")
        if weight != weight.quantize(_WEIGHT_QUANTUM):
            raise ValueError("weights must have at most six decimal places")
        normalized[name] = weight
    return normalized


def _normalization(value: Any) -> dict[str, dict[str, Decimal]]:
    if not isinstance(value, dict):
        raise ValueError("normalization must be an object")
    normalized: dict[str, dict[str, Decimal]] = {}
    for key, bounds in value.items():
        if not isinstance(bounds, dict) or "min" not in bounds or "max" not in bounds:
            raise ValueError("normalization requires min and max")
        minimum = _decimal_value(bounds["min"])
        maximum = _decimal_value(bounds["max"])
        if maximum <= minimum:
            raise ValueError("normalization max must be greater than min")
        normalized[str(key)] = {"min": minimum, "max": maximum}
    return normalized


class RuleSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: dict[str, Any]
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    hard_rules: dict[str, Any]
    weights: dict[str, Decimal]
    normalization: dict[str, dict[str, Decimal]]

    _validate_weights = field_validator("weights", mode="before")(_weights)
    _validate_normalization = field_validator(
        "normalization", mode="before"
    )(_normalization)

    @model_validator(mode="after")
    def validate_effective_range(self) -> RuleSnapshot:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("effective_to must be later than effective_from")
        return self

    @property
    def canonical_hash(self) -> str:
        return snapshot_service.canonical_hash(self.model_dump(mode="json"))


class AllocationRuleDraftCommand(RuleSnapshot):
    lineage_id: str = Field(min_length=1, max_length=36)
    change_reason: str = Field(min_length=1, max_length=4000)

    @field_validator("lineage_id", "change_reason")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class AllocationRulePublishCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)


class AllocationRuleRetireCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)

class AllocationPlanLineEditCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_plan_version: int = Field(gt=0)
    expected_line_version: int = Field(gt=0)
    allocated_quantity: Decimal
    reason: str = Field(min_length=1, max_length=4000)

    _validate_allocated_quantity = field_validator(
        "allocated_quantity",
        mode="before",
    )(_decimal_value)

    @field_validator("allocated_quantity")
    @classmethod
    def validate_allocated_quantity(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("allocated_quantity must be non-negative")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason cannot be blank")
        return normalized


class AllocationPlanPreviewCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)


class AllocationPlanConfirmCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)


class AllocationPlanExecuteCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_version: int = Field(gt=0)


AllocationExecutionOutcome = Literal[
    "RESERVED",
    "GAP_RETAINED",
    "CONFLICT",
]


class AllocationPlanActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: int
    event_id: int
    status: str
    version: int


class AllocationPlanExecutionLineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_id: int
    outcome: AllocationExecutionOutcome
    reservation_id: int | None = None
    error_code: str | None = None
    cause_code: str | None = None
    retryable: bool = False
    suggested_action: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AllocationPlanExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: int
    execution_id: int
    execution_as_of: date
    status: str
    version: int
    line_results: tuple[AllocationPlanExecutionLineResult, ...]
