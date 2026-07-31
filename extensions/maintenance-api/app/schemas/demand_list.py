from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

DecimalString = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: format(value, "f"),
        return_type=str,
        when_used="json",
    ),
]


class DemandListItemQuantitySnapshot(BaseModel):
    original_quantity: DecimalString
    final_quantity: DecimalString
