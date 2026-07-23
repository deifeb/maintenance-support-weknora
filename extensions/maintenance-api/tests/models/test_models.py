from decimal import Decimal

import pytest
from app.db.base import Base
from app.db.session import engine
from app.models import WarehouseInventory
from sqlalchemy import inspect

EXPECTED_TABLES = {
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_inventories",
    "suppliers",
    "supplier_offers",
}


def test_all_ten_tables_are_registered() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


@pytest.mark.parametrize("table_name", sorted(EXPECTED_TABLES))
def test_each_table_has_primary_key(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    assert list(table.primary_key.columns)


def test_inventory_available_quantity_is_derived() -> None:
    inventory = WarehouseInventory(
        warehouse_id=1,
        spare_part_id=1,
        on_hand_quantity=Decimal("100"),
        reserved_quantity=Decimal("10"),
        damaged_quantity=Decimal("5"),
        quarantined_quantity=Decimal("3"),
        in_transit_quantity=Decimal("0"),
        safety_stock=Decimal("10"),
        reorder_point=Decimal("20"),
    )
    assert inventory.available_quantity == Decimal("82")
