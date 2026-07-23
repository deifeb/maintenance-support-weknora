from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ConfigurationStatus, CriticalityLevel
from app.schemas.base import CodeModel, ORMModel, TimestampRead


class EquipmentModelBase(CodeModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=200)
    model_series: str | None = Field(default=None, max_length=100)
    service_life_years: Decimal | None = Field(default=None, ge=0)
    description: str | None = None
    is_active: bool = True


class EquipmentModelCreate(EquipmentModelBase):
    pass


class EquipmentModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=200)
    model_series: str | None = Field(default=None, max_length=100)
    service_life_years: Decimal | None = Field(default=None, ge=0)
    description: str | None = None
    is_active: bool | None = None


class EquipmentModelRead(EquipmentModelBase, TimestampRead):
    id: int


class ConfigurationVersionBase(CodeModel):
    equipment_model_id: int
    version_code: str = Field(min_length=1, max_length=64)
    version_name: str = Field(min_length=1, max_length=200)
    status: ConfigurationStatus = ConfigurationStatus.DRAFT
    effective_date: date | None = None
    expiry_date: date | None = None
    is_default: bool = False
    is_active: bool = True
    source_reference: str | None = Field(default=None, max_length=500)
    description: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_date and self.expiry_date and self.expiry_date <= self.effective_date:
            raise ValueError("expiry_date must be later than effective_date")
        return self


class ConfigurationVersionCreate(ConfigurationVersionBase):
    status: ConfigurationStatus = ConfigurationStatus.DRAFT


class ConfigurationVersionUpdate(BaseModel):
    version_name: str | None = Field(default=None, min_length=1, max_length=200)
    effective_date: date | None = None
    expiry_date: date | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    source_reference: str | None = Field(default=None, max_length=500)
    description: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_date and self.expiry_date and self.expiry_date <= self.effective_date:
            raise ValueError("expiry_date must be later than effective_date")
        return self


class ConfigurationVersionRead(ConfigurationVersionBase, TimestampRead):
    id: int


class ConfigurationItemBase(CodeModel):
    configuration_version_id: int
    item_code: str = Field(min_length=1, max_length=64)
    parent_item_id: int | None = None
    part_id: int
    spare_part_id: int | None = None
    install_quantity: Decimal = Field(gt=0)
    position_code: str | None = Field(default=None, max_length=100)
    position_name: str | None = Field(default=None, max_length=200)
    criticality_level: CriticalityLevel = CriticalityLevel.MEDIUM
    replacement_ratio: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    maintenance_level: str | None = Field(default=None, max_length=64)
    is_mandatory: bool = True
    sort_order: int = Field(default=0, ge=0)
    notes: str | None = None


class ConfigurationItemCreate(ConfigurationItemBase):
    pass


class ConfigurationItemUpdate(BaseModel):
    parent_item_id: int | None = None
    part_id: int | None = None
    spare_part_id: int | None = None
    install_quantity: Decimal | None = Field(default=None, gt=0)
    position_code: str | None = Field(default=None, max_length=100)
    position_name: str | None = Field(default=None, max_length=200)
    criticality_level: CriticalityLevel | None = None
    replacement_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    maintenance_level: str | None = Field(default=None, max_length=64)
    is_mandatory: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    notes: str | None = None


class ConfigurationItemRead(ConfigurationItemBase, TimestampRead):
    id: int


class ConfigurationCloneRequest(CodeModel):
    version_code: str = Field(min_length=1, max_length=64)
    version_name: str = Field(min_length=1, max_length=200)
    effective_date: date | None = None
    is_default: bool = False


class ConfigurationTreeNode(ORMModel):
    id: int
    item_code: str
    parent_item_id: int | None
    part_id: int
    spare_part_id: int | None
    install_quantity: Decimal
    position_code: str | None
    position_name: str | None
    criticality_level: CriticalityLevel
    replacement_ratio: Decimal
    maintenance_level: str | None
    is_mandatory: bool
    sort_order: int
    notes: str | None
    children: list["ConfigurationTreeNode"] = Field(default_factory=list)


class ConfigurationTree(BaseModel):
    version: ConfigurationVersionRead
    items: list[ConfigurationTreeNode]
