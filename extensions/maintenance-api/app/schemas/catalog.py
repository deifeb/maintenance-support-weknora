from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import CodeModel, TimestampRead


class PartBase(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    part_type: str | None = Field(default=None, max_length=100)
    specification: str | None = Field(default=None, max_length=500)
    manufacturer: str | None = Field(default=None, max_length=200)
    unit: str = Field(default="件", min_length=1, max_length=32)
    drawing_number: str | None = Field(default=None, max_length=100)
    maintenance_level: str | None = Field(default=None, max_length=64)
    description: str | None = None
    is_active: bool = True


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    part_type: str | None = Field(default=None, max_length=100)
    specification: str | None = Field(default=None, max_length=500)
    manufacturer: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    drawing_number: str | None = Field(default=None, max_length=100)
    maintenance_level: str | None = Field(default=None, max_length=64)
    description: str | None = None
    is_active: bool | None = None


class PartRead(PartBase, TimestampRead):
    id: int


class SparePartBase(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    specification: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="件", min_length=1, max_length=32)
    manufacturer: str | None = Field(default=None, max_length=200)
    material_code: str | None = Field(default=None, max_length=100)
    national_standard: str | None = Field(default=None, max_length=100)
    shelf_life_months: int | None = Field(default=None, ge=0)
    is_serialized: bool = False
    is_repairable: bool = False
    is_critical: bool = False
    default_service_level: Decimal | None = Field(default=None, gt=0, le=1)
    description: str | None = None
    is_active: bool = True


class SparePartCreate(SparePartBase):
    pass


class SparePartUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specification: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    manufacturer: str | None = Field(default=None, max_length=200)
    material_code: str | None = Field(default=None, max_length=100)
    national_standard: str | None = Field(default=None, max_length=100)
    shelf_life_months: int | None = Field(default=None, ge=0)
    is_serialized: bool | None = None
    is_repairable: bool | None = None
    is_critical: bool | None = None
    default_service_level: Decimal | None = Field(default=None, gt=0, le=1)
    description: str | None = None
    is_active: bool | None = None


class SparePartRead(SparePartBase, TimestampRead):
    id: int
