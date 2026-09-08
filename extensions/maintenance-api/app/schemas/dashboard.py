from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardMetric(BaseModel):
    key: str
    value: int | Decimal
    trend: Decimal | None = None


class RecentTask(BaseModel):
    task_type: str
    task_id: int
    title: str
    status: str
    updated_at: datetime
    progress: int | Decimal | None = None
    route: str


class RiskItem(BaseModel):
    key: str
    risk_type: str
    entity_type: str
    entity_id: int
    title: str
    severity: str
    value: int | Decimal | None = None
    detail: str | None = None
    updated_at: datetime
    route: str


class DashboardSummary(BaseModel):
    metrics: list[DashboardMetric]
    recent_tasks: list[RecentTask]
    risk_items: list[RiskItem]
    risk_distribution: dict[str, int]
    generated_at: datetime

    def metric_value(self, key: str) -> int | Decimal:
        for metric in self.metrics:
            if metric.key == key:
                return metric.value
        return 0

    @property
    def active_equipment_count(self) -> int:
        return int(self.metric_value("active_equipment_count"))

    @property
    def active_spare_part_count(self) -> int:
        return int(self.metric_value("active_spare_part_count"))

    @property
    def running_calculation_count(self) -> int:
        return int(self.metric_value("running_calculation_count"))
