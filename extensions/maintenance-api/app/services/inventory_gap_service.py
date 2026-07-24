from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InventoryGap:
    usable_inventory: Decimal
    net_demand_gap: Decimal
    inventory_coverage_rate: float
    shortage_risk_level: str


class InventoryGapService:
    def calculate(
        self,
        *,
        recommended_spare_quantity,
        available_quantity,
        in_transit_quantity,
        safety_stock_reserved,
    ) -> InventoryGap:
        recommended = Decimal(str(recommended_spare_quantity))
        usable = max(
            Decimal("0"),
            Decimal(str(available_quantity))
            + Decimal(str(in_transit_quantity))
            - Decimal(str(safety_stock_reserved)),
        )
        gap = max(Decimal("0"), recommended - usable)
        coverage_decimal = usable / recommended if recommended > 0 else Decimal("1")
        coverage = float(coverage_decimal)
        if gap == 0:
            risk = "NONE"
        elif coverage_decimal >= Decimal("0.8"):
            risk = "LOW"
        elif coverage_decimal >= Decimal("0.5"):
            risk = "MEDIUM"
        elif coverage_decimal >= Decimal("0.2"):
            risk = "HIGH"
        else:
            risk = "CRITICAL"
        return InventoryGap(usable, gap, coverage, risk)


inventory_gap_service = InventoryGapService()
