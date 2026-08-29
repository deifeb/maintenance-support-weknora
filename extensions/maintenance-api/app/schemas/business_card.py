from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from urllib.parse import parse_qs, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

CARD_SCHEMA_VERSION = "1.0"
MAX_CARD_TITLE_CHARS = 200
MAX_CARD_SUMMARY_CHARS = 1000
MAX_CARD_STATUS_CHARS = 64
MAX_CARDS_PER_MESSAGE = 3
MAX_CARD_PROJECTION_BYTES = 32 * 1024

CardType: TypeAlias = Literal[
    "SCENARIO_DRAFT",
    "CALCULATION",
    "MODEL_COMPARISON",
    "INVENTORY_GAP",
    "REVIEW_FINDING",
    "REPORT",
]

CardObjectType: TypeAlias = Literal[
    "AI_SESSION_SNAPSHOT",
    "CALCULATION_GROUP",
    "ALLOCATION_PLAN",
    "DEMAND_REVIEW_FINDING",
    "AI_REPORT_JOB",
]

ObjectIdentity: TypeAlias = StrictInt | StrictStr
ObservedVersion: TypeAlias = StrictInt | StrictStr | None

CARD_PRIORITY: dict[CardType, int] = {
    "REVIEW_FINDING": 0,
    "INVENTORY_GAP": 1,
    "SCENARIO_DRAFT": 2,
    "CALCULATION": 3,
    "MODEL_COMPARISON": 4,
    "REPORT": 5,
}

EXPECTED_OBJECT_TYPE: dict[CardType, CardObjectType] = {
    "SCENARIO_DRAFT": "AI_SESSION_SNAPSHOT",
    "CALCULATION": "CALCULATION_GROUP",
    "MODEL_COMPARISON": "CALCULATION_GROUP",
    "INVENTORY_GAP": "ALLOCATION_PLAN",
    "REVIEW_FINDING": "DEMAND_REVIEW_FINDING",
    "REPORT": "AI_REPORT_JOB",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaintenanceCardTarget(StrictModel):
    object_type: CardObjectType
    object_id: ObjectIdentity
    observed_version: ObservedVersion = None
    navigation_path: str = Field(min_length=1, max_length=500)

    @field_validator("object_id")
    @classmethod
    def validate_object_id(cls, value: ObjectIdentity) -> ObjectIdentity:
        if isinstance(value, bool):
            raise ValueError("object_id must be an integer or string identity")
        if isinstance(value, int) and value <= 0:
            raise ValueError("integer object_id must be positive")
        if isinstance(value, str) and not value.strip():
            raise ValueError("string object_id must be non-empty")
        return value

    @field_validator("observed_version")
    @classmethod
    def validate_observed_version(cls, value: ObservedVersion) -> ObservedVersion:
        if isinstance(value, bool):
            raise ValueError("observed_version must be an integer, string, or null")
        if isinstance(value, int) and value < 0:
            raise ValueError("integer observed_version must be non-negative")
        if isinstance(value, str) and not value.strip():
            raise ValueError("string observed_version must be non-empty")
        return value


class ScenarioDraftPayload(StrictModel):
    pass


class CalculationPayload(StrictModel):
    group_id: int = Field(gt=0)
    scenario_version_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=MAX_CARD_STATUS_CHARS)
    primary_candidate_key: str | None = Field(default=None, max_length=128)
    current_candidate_count: int = Field(ge=0)
    observed_version: ObservedVersion = None


class ModelComparisonPayload(StrictModel):
    group_id: int = Field(gt=0)
    scenario_version_id: int = Field(gt=0)
    comparable_candidate_count: int = Field(ge=2)
    primary_candidate_key: str | None = Field(default=None, max_length=128)
    observed_version: ObservedVersion = None


class InventoryGapPayload(StrictModel):
    gap_item_count: int = Field(ge=0)
    total_gap_quantity: Decimal = Field(ge=0)
    risk_item_count: int = Field(ge=0)
    source_demand_list_id: int = Field(gt=0)
    plan_status: str = Field(min_length=1, max_length=MAX_CARD_STATUS_CHARS)
    observed_version: ObservedVersion = None


class ReviewFindingPayload(StrictModel):
    finding_id: int = Field(gt=0)
    review_id: int = Field(gt=0)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    blocking: bool
    remaining_pending_count: int = Field(ge=0)
    observed_version: ObservedVersion = None


class ReportPayload(StrictModel):
    report_id: int = Field(gt=0)
    report_code: str = Field(min_length=1, max_length=64)
    report_type: Literal[
        "DEMAND_CALCULATION",
        "INVENTORY_GAP",
        "MANAGEMENT_DECISION",
    ]
    job_status: str = Field(min_length=1, max_length=MAX_CARD_STATUS_CHARS)
    version_id: int = Field(gt=0)
    version_number: int = Field(ge=1)
    version_status: str = Field(min_length=1, max_length=MAX_CARD_STATUS_CHARS)


class BusinessCardBase(StrictModel):
    schema_version: Literal["1.0"] = CARD_SCHEMA_VERSION
    type: CardType
    title: str = Field(min_length=1, max_length=MAX_CARD_TITLE_CHARS)
    summary: str = Field(min_length=1, max_length=MAX_CARD_SUMMARY_CHARS)
    status: str = Field(min_length=1, max_length=MAX_CARD_STATUS_CHARS)
    target: MaintenanceCardTarget
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include an RFC3339 timezone")
        return value

    @model_validator(mode="after")
    def validate_target_contract(self):
        expected = EXPECTED_OBJECT_TYPE[self.type]
        if self.target.object_type != expected:
            raise ValueError(
                f"{self.type} target.object_type must be {expected}"
            )
        return self


class ScenarioDraftCard(BusinessCardBase):
    type: Literal["SCENARIO_DRAFT"] = "SCENARIO_DRAFT"
    payload: ScenarioDraftPayload = Field(default_factory=ScenarioDraftPayload)

    @model_validator(mode="after")
    def validate_navigation(self):
        _require_query_navigation(
            self.target.navigation_path,
            "/platform/maintenance/scenarios/new",
            "session_id",
            self.target.object_id,
        )
        return self


class CalculationCard(BusinessCardBase):
    type: Literal["CALCULATION"] = "CALCULATION"
    payload: CalculationPayload

    @model_validator(mode="after")
    def validate_card_consistency(self):
        _require_path_navigation(
            self.target.navigation_path,
            f"/platform/maintenance/calculations/{self.target.object_id}/progress",
        )
        if str(self.payload.group_id) != str(self.target.object_id):
            raise ValueError("CALCULATION payload.group_id must match target.object_id")
        _require_version_match(self.target.observed_version, self.payload.observed_version)
        return self


class ModelComparisonCard(BusinessCardBase):
    type: Literal["MODEL_COMPARISON"] = "MODEL_COMPARISON"
    payload: ModelComparisonPayload

    @model_validator(mode="after")
    def validate_card_consistency(self):
        _require_path_navigation(
            self.target.navigation_path,
            f"/platform/maintenance/calculations/{self.target.object_id}/comparison",
        )
        if str(self.payload.group_id) != str(self.target.object_id):
            raise ValueError("MODEL_COMPARISON payload.group_id must match target.object_id")
        _require_version_match(self.target.observed_version, self.payload.observed_version)
        return self


class InventoryGapCard(BusinessCardBase):
    type: Literal["INVENTORY_GAP"] = "INVENTORY_GAP"
    payload: InventoryGapPayload

    @model_validator(mode="after")
    def validate_card_consistency(self):
        _require_path_navigation(
            self.target.navigation_path,
            f"/platform/maintenance/inventory-gap/allocations/{self.target.object_id}",
        )
        _require_version_match(self.target.observed_version, self.payload.observed_version)
        if self.payload.gap_item_count == 0 and self.payload.risk_item_count == 0:
            raise ValueError("INVENTORY_GAP requires a gap or meaningful risk")
        return self


class ReviewFindingCard(BusinessCardBase):
    type: Literal["REVIEW_FINDING"] = "REVIEW_FINDING"
    payload: ReviewFindingPayload

    @model_validator(mode="after")
    def validate_card_consistency(self):
        if str(self.payload.finding_id) != str(self.target.object_id):
            raise ValueError("REVIEW_FINDING payload.finding_id must match target.object_id")
        _require_path_navigation(
            self.target.navigation_path,
            f"/platform/maintenance/reviews/{self.payload.review_id}",
        )
        _require_version_match(self.target.observed_version, self.payload.observed_version)
        return self


class ReportCard(BusinessCardBase):
    type: Literal["REPORT"] = "REPORT"
    payload: ReportPayload

    @model_validator(mode="after")
    def validate_card_consistency(self):
        _require_query_navigation(
            self.target.navigation_path,
            "/platform/maintenance/reports",
            "report_id",
            self.target.object_id,
        )
        if str(self.payload.report_id) != str(self.target.object_id):
            raise ValueError("REPORT payload.report_id must match target.object_id")
        if (
            self.target.observed_version is not None
            and str(self.target.observed_version) != str(self.payload.version_number)
        ):
            raise ValueError("REPORT observed_version must match payload.version_number")
        return self


MaintenanceBusinessCard: TypeAlias = Annotated[
    ScenarioDraftCard
    | CalculationCard
    | ModelComparisonCard
    | InventoryGapCard
    | ReviewFindingCard
    | ReportCard,
    Field(discriminator="type"),
]

_CARD_ADAPTER = TypeAdapter(MaintenanceBusinessCard)


def parse_business_card(value: object) -> MaintenanceBusinessCard:
    return _CARD_ADAPTER.validate_python(value)


def canonicalize_cards(
    cards: list[MaintenanceBusinessCard],
) -> list[MaintenanceBusinessCard]:
    by_identity: dict[
        tuple[str, str, str, str],
        MaintenanceBusinessCard,
    ] = {}
    for card in cards:
        identity = (
            card.type,
            card.target.object_type,
            str(card.target.object_id),
            "" if card.target.observed_version is None else str(card.target.observed_version),
        )
        by_identity.setdefault(identity, card)

    deduped = list(by_identity.values())
    seen_types: set[str] = set()
    for card in deduped:
        if card.type in seen_types:
            raise ValueError(f"only one {card.type} card is allowed per message")
        seen_types.add(card.type)

    if len(deduped) > MAX_CARDS_PER_MESSAGE:
        raise ValueError(
            f"at most {MAX_CARDS_PER_MESSAGE} maintenance cards are allowed per message"
        )

    ordered = sorted(
        deduped,
        key=lambda card: (
            CARD_PRIORITY[card.type],
            card.target.object_type,
            str(card.target.object_id),
            "" if card.target.observed_version is None else str(card.target.observed_version),
        ),
    )
    require_projection_size(ordered)
    return ordered


class BusinessCardBatch(StrictModel):
    cards: list[MaintenanceBusinessCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def canonicalize(self):
        try:
            self.cards = canonicalize_cards(self.cards)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


def canonical_card_json(cards: list[MaintenanceBusinessCard]) -> bytes:
    ordered = canonicalize_cards(cards)
    return _canonical_bytes(ordered)


def _canonical_bytes(cards: list[MaintenanceBusinessCard]) -> bytes:
    payload = [card.model_dump(mode="json", exclude_none=True) for card in cards]
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def projection_size_bytes(cards: list[MaintenanceBusinessCard]) -> int:
    return len(_canonical_bytes(cards))


def require_projection_size(
    cards: list[MaintenanceBusinessCard],
    *,
    max_bytes: int = MAX_CARD_PROJECTION_BYTES,
) -> None:
    size = projection_size_bytes(cards)
    if size > max_bytes:
        raise ValueError(
            f"maintenance card projection exceeds {max_bytes} bytes"
        )


def _require_path_navigation(actual: str, expected: str) -> None:
    parsed = urlsplit(actual)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("navigation_path must be a fixed same-origin maintenance path")
    if parsed.path != expected:
        raise ValueError("navigation_path does not match the card route template")


def _require_query_navigation(
    actual: str,
    expected_path: str,
    query_key: str,
    object_id: ObjectIdentity,
) -> None:
    parsed = urlsplit(actual)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path != expected_path:
        raise ValueError("navigation_path must be a fixed same-origin maintenance path")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) != {query_key} or query[query_key] != [str(object_id)]:
        raise ValueError("navigation_path does not match the card route template")


def _require_version_match(
    target_version: ObservedVersion,
    payload_version: ObservedVersion,
) -> None:
    if target_version is None or payload_version is None:
        return
    if str(target_version) != str(payload_version):
        raise ValueError("payload observed_version must match target.observed_version")
