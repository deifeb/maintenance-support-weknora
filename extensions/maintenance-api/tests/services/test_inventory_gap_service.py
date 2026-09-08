from app.services.inventory_gap_service import InventoryGapService


def test_inventory_gap_uses_available_in_transit_and_safety_stock():
    result = InventoryGapService().calculate(
        recommended_spare_quantity=10,
        available_quantity=7,
        in_transit_quantity=2,
        safety_stock_reserved=3,
    )
    assert result.usable_inventory == 6
    assert result.net_demand_gap == 4
    assert result.inventory_coverage_rate == 0.6
