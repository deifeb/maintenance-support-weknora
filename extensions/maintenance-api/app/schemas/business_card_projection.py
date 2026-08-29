from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.business_card import (
    CARD_SCHEMA_VERSION,
    CardType,
    MaintenanceBusinessCard,
    ObjectIdentity,
    ObservedVersion,
    canonicalize_cards,
)


class StrictProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaintenanceCardReference(StrictProjectionModel):
    type: CardType
    object_id: ObjectIdentity
    observed_version: ObservedVersion = None


class MaintenanceProjectionSource(StrictProjectionModel):
    kind: Literal["AI_MESSAGE_TRIGGER"] = "AI_MESSAGE_TRIGGER"
    session_id: int = Field(gt=0)
    message_id: int = Field(gt=0)


class MaintenanceProjection(StrictProjectionModel):
    schema_version: Literal["1.0"] = CARD_SCHEMA_VERSION
    source: MaintenanceProjectionSource
    cards: list[MaintenanceBusinessCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def canonicalize_projection(self):
        self.cards = canonicalize_cards(self.cards)
        return self
