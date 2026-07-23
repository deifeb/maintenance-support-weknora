from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class CodeModel(BaseModel):
    @field_validator("code", "version_code", "item_code", "profile_code", "offer_code", check_fields=False)
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("code cannot be blank")
        return normalized


class ActivePatch(BaseModel):
    is_active: bool


class TimestampRead(ORMModel):
    created_at: datetime
    updated_at: datetime


class DeleteResult(BaseModel):
    deleted: bool
    resource: str
    identifier: Any
