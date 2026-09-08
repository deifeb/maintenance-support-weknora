from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import CodeModel, TimestampRead


class SupplierBase(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    supplier_type: str | None = Field(default=None, max_length=100)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    credit_code: str | None = Field(default=None, max_length=100)
    rating: Decimal | None = Field(default=None, ge=0, le=100)
    qualification_status: str | None = Field(default=None, max_length=100)
    description: str | None = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    supplier_type: str | None = Field(default=None, max_length=100)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    credit_code: str | None = Field(default=None, max_length=100)
    rating: Decimal | None = Field(default=None, ge=0, le=100)
    qualification_status: str | None = Field(default=None, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class SupplierRead(SupplierBase, TimestampRead):
    id: int


class SupplierOfferBase(CodeModel):
    offer_code: str = Field(min_length=1, max_length=64)
    supplier_id: int
    spare_part_id: int
    unit_price: Decimal = Field(ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    price_includes_tax: bool = True
    lead_time_days: int = Field(ge=0)
    minimum_order_quantity: Decimal = Field(default=Decimal("1"), ge=0)
    order_multiple: Decimal = Field(default=Decimal("1"), gt=0)
    maximum_supply_quantity: Decimal | None = Field(default=None, ge=0)
    warranty_months: int | None = Field(default=None, ge=0)
    quality_level: str | None = Field(default=None, max_length=100)
    is_preferred: bool = False
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_offer(self):
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class SupplierOfferCreate(SupplierOfferBase):
    pass


class SupplierOfferUpdate(BaseModel):
    supplier_id: int | None = None
    spare_part_id: int | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    price_includes_tax: bool | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    minimum_order_quantity: Decimal | None = Field(default=None, ge=0)
    order_multiple: Decimal | None = Field(default=None, gt=0)
    maximum_supply_quantity: Decimal | None = Field(default=None, ge=0)
    warranty_months: int | None = Field(default=None, ge=0)
    quality_level: str | None = Field(default=None, max_length=100)
    is_preferred: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool | None = None


class SupplierOfferRead(SupplierOfferBase, TimestampRead):
    id: int
