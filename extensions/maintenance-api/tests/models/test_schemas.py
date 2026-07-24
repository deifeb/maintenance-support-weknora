from decimal import Decimal

import pytest
from app.models.enums import DataSourceType, ReliabilityModelType
from app.schemas.inventory import InventoryQuantities
from app.schemas.reliability import ReliabilityProfileCreate
from app.schemas.supplier import SupplierOfferCreate
from pydantic import ValidationError


@pytest.mark.parametrize(
    "model_type,extra",
    [
        (ReliabilityModelType.EXPONENTIAL, {"failure_rate": "0.001"}),
        (ReliabilityModelType.WEIBULL, {"weibull_shape": "1.5", "weibull_scale": "1000"}),
        (ReliabilityModelType.BINOMIAL, {"binomial_trials": 10, "binomial_probability": "0.2"}),
        (
            ReliabilityModelType.NEGATIVE_BINOMIAL,
            {"negative_binomial_r": "3", "negative_binomial_p": "0.4"},
        ),
        (ReliabilityModelType.EMPIRICAL, {"empirical_mean": "2", "empirical_variance": "1"}),
    ],
)
def test_valid_reliability_models(model_type, extra) -> None:
    payload = ReliabilityProfileCreate(
        profile_code=f"RP-{model_type}",
        spare_part_id=1,
        model_type=model_type,
        data_source_type=DataSourceType.DESIGN_PARAMETER,
        **extra,
    )
    assert payload.model_type == model_type


@pytest.mark.parametrize("model_type", list(ReliabilityModelType))
def test_missing_model_parameters_are_rejected(model_type) -> None:
    with pytest.raises(ValidationError):
        ReliabilityProfileCreate(
            profile_code="RP-X",
            spare_part_id=1,
            model_type=model_type,
            data_source_type=DataSourceType.DESIGN_PARAMETER,
        )


@pytest.mark.parametrize(
    "values",
    [
        {"on_hand_quantity": 10, "reserved_quantity": 11, "safety_stock": 0, "reorder_point": 0},
        {"on_hand_quantity": 10, "safety_stock": 5, "reorder_point": 4},
        {"on_hand_quantity": 10, "safety_stock": 2, "reorder_point": 5, "maximum_stock": 4},
    ],
)
def test_invalid_inventory_relations_are_rejected(values) -> None:
    with pytest.raises(ValidationError):
        InventoryQuantities(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit_price", -1),
        ("lead_time_days", -1),
        ("order_multiple", 0),
        ("tax_rate", Decimal("1.1")),
    ],
)
def test_invalid_supplier_offer_values_are_rejected(field, value) -> None:
    data = {
        "offer_code": "OF-1",
        "supplier_id": 1,
        "spare_part_id": 1,
        "unit_price": 10,
        "lead_time_days": 5,
        field: value,
    }
    with pytest.raises(ValidationError):
        SupplierOfferCreate(**data)
