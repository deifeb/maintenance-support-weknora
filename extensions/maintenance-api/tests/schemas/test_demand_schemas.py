from decimal import Decimal

import pytest
from app.models.enums import AgeDistributionType
from app.schemas.demand_scenario import AgeGroupCreate, ScenarioStageCreate
from app.schemas.repair import RepairProfileCreate
from pydantic import ValidationError


def test_repair_profile_rejects_probability_sum_above_one():
    with pytest.raises(ValidationError):
        RepairProfileCreate(
            profile_code="RP-1",
            profile_name="修理",
            spare_part_id=1,
            repair_success_rate=Decimal("0.8"),
            condemnation_rate=Decimal("0.3"),
            repair_turnaround_hours=Decimal("24"),
        )


def test_age_group_requires_distribution_parameters():
    with pytest.raises(ValidationError):
        AgeGroupCreate(
            group_code="OLD",
            group_name="老旧",
            distribution_type=AgeDistributionType.UNIFORM,
            proportion=Decimal("1"),
        )


def test_stage_rejects_zero_duration():
    with pytest.raises(ValidationError):
        ScenarioStageCreate(stage_code="S1", stage_name="阶段", stage_order=1, duration_hours=0)
