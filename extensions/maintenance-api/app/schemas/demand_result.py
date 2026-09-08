from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class InventoryGapRead(BaseModel):
    usable_inventory: Decimal
    net_demand_gap: Decimal
    inventory_coverage_rate: Decimal
    shortage_risk_level: str


class CalculationItemResultRead(BaseModel):
    spare_part_id: int
    spare_part_code: str
    spare_part_name: str
    expected_demand: Decimal
    p50: Decimal
    p80: Decimal
    p90: Decimal
    p95: Decimal
    p99: Decimal
    recommended_spare_quantity: Decimal
    usable_inventory: Decimal
    net_demand_gap: Decimal
    inventory_coverage_rate: Decimal
    shortage_risk_level: str
    warnings: list[str] = []


class CalculationRead(BaseModel):
    id: int
    calculation_code: str
    calculation_name: str
    status: str
    requested_mode: str
    execution_type: str
    progress_percent: Decimal
    input_snapshot_hash: str
    result_summary_json: dict[str, Any] | None
