import argparse
from decimal import Decimal

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    ConfigurationVersion,
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
    RepairProfile,
    SparePart,
)
from app.models.enums import (
    AgeDistributionType,
    DataSourceType,
    DemandExecutionMode,
    MissingParameterPolicy,
    ScenarioVersionStatus,
    ShockApplicationMode,
)
from app.scripts.seed_master_data import seed as seed_master_data


def _normalize_tenant_id(tenant_id: str) -> str:
    normalized = tenant_id.strip()
    if not normalized:
        raise ValueError("tenant_id must not be blank")
    return normalized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Tenant that owns all seeded demand scenarios",
    )
    return parser.parse_args()


def get_or_create(
    session,
    model,
    *,
    tenant_id: str,
    lookup: dict,
    defaults: dict,
):
    scoped_lookup = {
        "tenant_id": tenant_id,
        **lookup,
    }
    instance = session.scalar(
        select(model).filter_by(**scoped_lookup)
    )
    if instance is None:
        instance = model(
            **scoped_lookup,
            **defaults,
        )
        session.add(instance)
        session.flush()
    return instance


def seed(*, tenant_id: str) -> dict[str, int]:
    tenant_id = _normalize_tenant_id(tenant_id)
    seed_master_data(tenant_id=tenant_id)
    session = SessionLocal()
    try:
        published_config = session.scalar(
            select(ConfigurationVersion)
            .where(
                ConfigurationVersion.tenant_id == tenant_id,
                ConfigurationVersion.version_code == "V1",
                ConfigurationVersion.is_active.is_(True),
            )
            .order_by(ConfigurationVersion.id)
        )
        if published_config is None:
            raise RuntimeError(
                "Run seed_master_data first to create "
                "a published configuration"
            )

        repairable_spares = list(
            session.scalars(
                select(SparePart)
                .where(
                    SparePart.tenant_id == tenant_id,
                    SparePart.is_repairable.is_(True),
                )
                .order_by(SparePart.id)
                .limit(5)
            ).all()
        )
        for spare in repairable_spares:
            get_or_create(
                session,
                RepairProfile,
                tenant_id=tenant_id,
                lookup={
                    "profile_code": f"DRP-{spare.code}",
                },
                defaults={
                    "profile_name": (
                        f"{spare.name}示例修理参数"
                    ),
                    "spare_part_id": spare.id,
                    "configuration_version_id": (
                        published_config.id
                    ),
                    "maintenance_level": "基地级",
                    "repair_success_rate": Decimal("0.85"),
                    "condemnation_rate": Decimal("0.10"),
                    "repair_turnaround_hours": Decimal("72"),
                    "turnaround_std_hours": Decimal("12"),
                    "initial_repair_pipeline_quantity": (
                        Decimal("0")
                    ),
                    "data_source_type": (
                        DataSourceType.MANUAL_ESTIMATE
                    ),
                    "is_active": True,
                },
            )

        definitions = [
            (
                "SC-TRAINING",
                "年度训练保障",
                3,
                False,
            ),
            (
                "SC-HIGH-INTENSITY",
                "高强度多阶段保障",
                4,
                False,
            ),
            (
                "SC-COMMON-SHOCK",
                "共同冲击保障",
                3,
                True,
            ),
        ]
        for code, name, stage_count, with_shock in definitions:
            template = get_or_create(
                session,
                DemandScenarioTemplate,
                tenant_id=tenant_id,
                lookup={"code": code},
                defaults={
                    "name": name,
                    "category": "示例场景",
                    "is_active": True,
                },
            )
            version = get_or_create(
                session,
                DemandScenarioVersion,
                tenant_id=tenant_id,
                lookup={
                    "scenario_template_id": template.id,
                    "version_code": "V1",
                },
                defaults={
                    "version_name": "示例版本1",
                    "status": ScenarioVersionStatus.PUBLISHED,
                    "default_service_level": Decimal("0.90"),
                    "criticality_service_levels_json": {
                        "CRITICAL": "0.99",
                        "HIGH": "0.95",
                        "MEDIUM": "0.90",
                        "LOW": "0.80",
                    },
                    "missing_parameter_policy": (
                        MissingParameterPolicy.WARN_AND_SKIP
                    ),
                    "execution_mode": DemandExecutionMode.AUTO,
                    "comparison_enabled": False,
                    "default_initial_age_hours": Decimal("500"),
                    "simulation_config_json": {
                        "min_runs": 1000,
                        "max_runs": 10000,
                        "batch_size": 1000,
                        "mean_relative_tolerance": "0.01",
                        "quantile_absolute_tolerance": "1",
                        "required_stable_batches": 3,
                        "quantiles": [
                            "0.50",
                            "0.80",
                            "0.90",
                            "0.95",
                            "0.99",
                        ],
                    },
                    "formula_version": "DEMAND-FORMULA-1",
                    "input_schema_version": "1.0",
                },
            )
            fleet = get_or_create(
                session,
                DemandFleetGroup,
                tenant_id=tenant_id,
                lookup={
                    "scenario_version_id": version.id,
                    "group_code": "FLEET-A",
                },
                defaults={
                    "group_name": "示例装备群",
                    "configuration_version_id": (
                        published_config.id
                    ),
                    "initial_quantity": 10,
                    "default_initial_age_hours": Decimal("500"),
                },
            )
            get_or_create(
                session,
                DemandAgeGroup,
                tenant_id=tenant_id,
                lookup={
                    "fleet_group_id": fleet.id,
                    "group_code": "NEW",
                },
                defaults={
                    "group_name": "较新装备",
                    "distribution_type": (
                        AgeDistributionType.UNIFORM
                    ),
                    "proportion": Decimal("0.4"),
                    "minimum_hours": Decimal("0"),
                    "maximum_hours": Decimal("500"),
                    "sort_order": 1,
                },
            )
            get_or_create(
                session,
                DemandAgeGroup,
                tenant_id=tenant_id,
                lookup={
                    "fleet_group_id": fleet.id,
                    "group_code": "MATURE",
                },
                defaults={
                    "group_name": "中期装备",
                    "distribution_type": (
                        AgeDistributionType.TRIANGULAR
                    ),
                    "proportion": Decimal("0.6"),
                    "minimum_hours": Decimal("500"),
                    "maximum_hours": Decimal("2500"),
                    "mode_hours": Decimal("1200"),
                    "sort_order": 2,
                },
            )
            for order in range(1, stage_count + 1):
                stage = get_or_create(
                    session,
                    DemandScenarioStage,
                    tenant_id=tenant_id,
                    lookup={
                        "scenario_version_id": version.id,
                        "stage_code": f"S{order}",
                    },
                    defaults={
                        "stage_name": f"任务阶段{order}",
                        "stage_order": order,
                        "duration_hours": Decimal(
                            str(100 + order * 20)
                        ),
                        "utilization_rate": Decimal("0.8"),
                        "mission_intensity_factor": Decimal(
                            (
                                "1.2"
                                if code != "SC-TRAINING"
                                else "1.0"
                            )
                        ),
                        "environment_factor": Decimal("1.1"),
                        "temperature_factor": Decimal("1"),
                        "dust_factor": Decimal("1"),
                        "humidity_factor": Decimal("1"),
                        "vibration_factor": Decimal("1"),
                    },
                )
                get_or_create(
                    session,
                    DemandStageFleetUsage,
                    tenant_id=tenant_id,
                    lookup={
                        "stage_id": stage.id,
                        "fleet_group_id": fleet.id,
                    },
                    defaults={
                        "active_quantity": max(
                            6,
                            11 - order,
                        ),
                        "equipment_intensity_factor": Decimal(
                            "1"
                        ),
                        "is_active": True,
                    },
                )
                if with_shock and order == 2:
                    get_or_create(
                        session,
                        DemandCommonShockRule,
                        tenant_id=tenant_id,
                        lookup={
                            "stage_id": stage.id,
                            "shock_code": "HIGH-TEMP",
                        },
                        defaults={
                            "shock_name": "高温共同冲击",
                            "probability": Decimal("0.05"),
                            "multiplier": Decimal("1.8"),
                            "application_mode": (
                                ShockApplicationMode.FAILURE_RATE
                            ),
                            "maximum_occurrences": 1,
                        },
                    )

        session.commit()

        def tenant_count(model) -> int:
            return int(
                session.scalar(
                    select(func.count(model.id)).where(
                        model.tenant_id == tenant_id,
                    )
                )
                or 0
            )

        return {
            "repair_profiles": tenant_count(
                RepairProfile
            ),
            "scenario_templates": tenant_count(
                DemandScenarioTemplate
            ),
            "scenario_versions": tenant_count(
                DemandScenarioVersion
            ),
            "scenario_stages": tenant_count(
                DemandScenarioStage
            ),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    args = _parse_args()
    print(seed(tenant_id=args.tenant_id))


if __name__ == "__main__":
    main()
