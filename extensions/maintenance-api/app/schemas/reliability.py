from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DataSourceType, ReliabilityModelType
from app.schemas.base import CodeModel, TimestampRead


class ReliabilityProfileBase(CodeModel):
    profile_code: str = Field(min_length=1, max_length=64)
    spare_part_id: int
    configuration_version_id: int | None = None
    model_type: ReliabilityModelType
    failure_rate: Decimal | None = Field(default=None, gt=0)
    mtbf_hours: Decimal | None = Field(default=None, gt=0)
    weibull_shape: Decimal | None = Field(default=None, gt=0)
    weibull_scale: Decimal | None = Field(default=None, gt=0)
    binomial_trials: int | None = Field(default=None, gt=0)
    binomial_probability: Decimal | None = Field(default=None, ge=0, le=1)
    negative_binomial_r: Decimal | None = Field(default=None, gt=0)
    negative_binomial_p: Decimal | None = Field(default=None, gt=0, le=1)
    empirical_mean: Decimal | None = Field(default=None, ge=0)
    empirical_variance: Decimal | None = Field(default=None, ge=0)
    extension_parameters_json: dict[str, Any] | None = None
    operating_condition_json: dict[str, Any] | None = None
    data_source_type: DataSourceType
    data_source_reference: str | None = Field(default=None, max_length=500)
    sample_size: int | None = Field(default=None, ge=0)
    confidence_level: Decimal | None = Field(default=None, gt=0, le=1)
    estimated_at: datetime | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_profile(self):
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        match self.model_type:
            case ReliabilityModelType.EXPONENTIAL:
                if self.failure_rate is None and self.mtbf_hours is None:
                    raise ValueError("EXPONENTIAL requires failure_rate or mtbf_hours")
            case ReliabilityModelType.WEIBULL:
                if self.weibull_shape is None or self.weibull_scale is None:
                    raise ValueError("WEIBULL requires weibull_shape and weibull_scale")
            case ReliabilityModelType.BINOMIAL:
                if self.binomial_trials is None or self.binomial_probability is None:
                    raise ValueError("BINOMIAL requires binomial_trials and binomial_probability")
            case ReliabilityModelType.NEGATIVE_BINOMIAL:
                if self.negative_binomial_r is None or self.negative_binomial_p is None:
                    raise ValueError(
                        "NEGATIVE_BINOMIAL requires negative_binomial_r and negative_binomial_p"
                    )
            case ReliabilityModelType.EMPIRICAL:
                if self.empirical_mean is None or self.empirical_variance is None:
                    raise ValueError("EMPIRICAL requires empirical_mean and empirical_variance")
        return self


class ReliabilityProfileCreate(ReliabilityProfileBase):
    pass


class ReliabilityProfileUpdate(BaseModel):
    configuration_version_id: int | None = None
    model_type: ReliabilityModelType | None = None
    failure_rate: Decimal | None = Field(default=None, gt=0)
    mtbf_hours: Decimal | None = Field(default=None, gt=0)
    weibull_shape: Decimal | None = Field(default=None, gt=0)
    weibull_scale: Decimal | None = Field(default=None, gt=0)
    binomial_trials: int | None = Field(default=None, gt=0)
    binomial_probability: Decimal | None = Field(default=None, ge=0, le=1)
    negative_binomial_r: Decimal | None = Field(default=None, gt=0)
    negative_binomial_p: Decimal | None = Field(default=None, gt=0, le=1)
    empirical_mean: Decimal | None = Field(default=None, ge=0)
    empirical_variance: Decimal | None = Field(default=None, ge=0)
    extension_parameters_json: dict[str, Any] | None = None
    operating_condition_json: dict[str, Any] | None = None
    data_source_type: DataSourceType | None = None
    data_source_reference: str | None = Field(default=None, max_length=500)
    sample_size: int | None = Field(default=None, ge=0)
    confidence_level: Decimal | None = Field(default=None, gt=0, le=1)
    estimated_at: datetime | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    is_active: bool | None = None


class ReliabilityProfileRead(ReliabilityProfileBase, TimestampRead):
    id: int
