from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DataSourceType
from app.schemas.base import CodeModel, TimestampRead


class RepairProfileBase(CodeModel):
    profile_code: str = Field(min_length=1, max_length=64)
    profile_name: str = Field(min_length=1, max_length=200)
    spare_part_id: int = Field(gt=0)
    configuration_version_id: int | None = Field(default=None, gt=0)
    maintenance_level: str | None = Field(default=None, max_length=64)
    repair_success_rate: Decimal = Field(ge=0, le=1)
    condemnation_rate: Decimal = Field(ge=0, le=1)
    repair_turnaround_hours: Decimal = Field(gt=0)
    turnaround_std_hours: Decimal = Field(default=Decimal("0"), ge=0)
    initial_repair_pipeline_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    data_source_type: DataSourceType = DataSourceType.MANUAL_ESTIMATE
    data_source_reference: str | None = Field(default=None, max_length=500)
    sample_size: int | None = Field(default=None, ge=0)
    confidence_level: Decimal | None = Field(default=None, gt=0, le=1)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_probabilities_and_dates(self):
        if self.repair_success_rate + self.condemnation_rate > 1:
            raise ValueError("repair_success_rate + condemnation_rate must not exceed 1")
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class RepairProfileCreate(RepairProfileBase):
    pass


class RepairProfileUpdate(BaseModel):
    profile_name: str | None = Field(default=None, min_length=1, max_length=200)
    configuration_version_id: int | None = Field(default=None, gt=0)
    maintenance_level: str | None = Field(default=None, max_length=64)
    repair_success_rate: Decimal | None = Field(default=None, ge=0, le=1)
    condemnation_rate: Decimal | None = Field(default=None, ge=0, le=1)
    repair_turnaround_hours: Decimal | None = Field(default=None, gt=0)
    turnaround_std_hours: Decimal | None = Field(default=None, ge=0)
    initial_repair_pipeline_quantity: Decimal | None = Field(default=None, ge=0)
    data_source_type: DataSourceType | None = None
    data_source_reference: str | None = Field(default=None, max_length=500)
    sample_size: int | None = Field(default=None, ge=0)
    confidence_level: Decimal | None = Field(default=None, gt=0, le=1)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool | None = None


class RepairProfileRead(RepairProfileBase, TimestampRead):
    id: int
