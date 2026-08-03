from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class InventoryTargetReceiptResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created_identity: StrictBool
    operation_type: Literal["OPENING", "ADJUST"] | None
    transaction_id: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode="after")
    def validate_transaction_result(self):
        if (self.operation_type is None) != (self.transaction_id is None):
            raise ValueError(
                "operation_type and transaction_id must both be present or absent"
            )
        return self
