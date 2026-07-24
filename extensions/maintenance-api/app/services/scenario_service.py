from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError, ConflictError, NotFoundError
from app.models import (
    ConfigurationVersion,
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandParameterOverride,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
)
from app.models.enums import ConfigurationStatus, ScenarioVersionStatus
from app.repositories.demand_scenario_repository import (
    DemandScenarioTemplateRepository,
    DemandScenarioVersionRepository,
)
from app.schemas.demand_scenario import (
    AgeGroupCreate,
    CommonShockCreate,
    FleetGroupCreate,
    FleetUsageCreate,
    ParameterOverrideCreate,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioTemplateRead,
    ScenarioTemplateUpdate,
    ScenarioValidationResult,
    ScenarioVersionCreate,
    ScenarioVersionUpdate,
)
from app.services.base import CrudService


class ScenarioService:
    def __init__(self) -> None:
        self.template_repository = DemandScenarioTemplateRepository()
        self.version_repository = DemandScenarioVersionRepository()
        self.template_crud = CrudService(
            self.template_repository,
            resource_name="demand_scenario",
            read_schema=ScenarioTemplateRead,
        )

    def create_template(self, session: Session, payload: ScenarioTemplateCreate):
        return self.template_crud.create(session, payload)

    def list_templates(self, session: Session, **kwargs):
        return self.template_crud.list(session, **kwargs)

    def get_template(self, session: Session, identifier: int):
        return self.template_crud.get(session, identifier)

    def update_template(self, session: Session, identifier: int, payload: ScenarioTemplateUpdate):
        return self.template_crud.update(session, identifier, payload)

    def delete_template(self, session: Session, identifier: int):
        return self.template_crud.delete(session, identifier)

    def create_version(self, session: Session, template_id: int, payload: ScenarioVersionCreate):
        if session.get(DemandScenarioTemplate, template_id) is None:
            raise NotFoundError("demand_scenario", template_id)
        exists = session.scalar(
            select(DemandScenarioVersion).where(
                DemandScenarioVersion.scenario_template_id == template_id,
                DemandScenarioVersion.version_code == payload.version_code,
            )
        )
        if exists:
            raise ConflictError("scenario version code already exists")
        data = payload.model_dump(mode="json")
        instance = DemandScenarioVersion(scenario_template_id=template_id, **data)
        session.add(instance)
        session.commit()
        session.refresh(instance)
        return instance

    def list_versions(self, session: Session, template_id: int):
        if session.get(DemandScenarioTemplate, template_id) is None:
            raise NotFoundError("demand_scenario", template_id)
        return list(
            session.scalars(
                select(DemandScenarioVersion)
                .where(DemandScenarioVersion.scenario_template_id == template_id)
                .order_by(DemandScenarioVersion.id)
            ).all()
        )

    def clone_version(
        self, session: Session, version_id: int, version_code: str, version_name: str
    ):
        source = self.get_version(session, version_id, full=True)
        if session.scalar(
            select(DemandScenarioVersion).where(
                DemandScenarioVersion.scenario_template_id == source.scenario_template_id,
                DemandScenarioVersion.version_code == version_code,
            )
        ):
            raise ConflictError("scenario version code already exists")
        clone = DemandScenarioVersion(
            scenario_template_id=source.scenario_template_id,
            version_code=version_code.strip().upper(),
            version_name=version_name,
            status=ScenarioVersionStatus.DRAFT,
            default_service_level=source.default_service_level,
            criticality_service_levels_json=source.criticality_service_levels_json,
            missing_parameter_policy=source.missing_parameter_policy,
            execution_mode=source.execution_mode,
            comparison_enabled=source.comparison_enabled,
            default_initial_age_hours=source.default_initial_age_hours,
            default_repair_parameters_json=source.default_repair_parameters_json,
            fallback_parameters_json=source.fallback_parameters_json,
            simulation_config_json=source.simulation_config_json,
            formula_version=source.formula_version,
            input_schema_version=source.input_schema_version,
            description=source.description,
        )
        session.add(clone)
        session.flush()
        stage_map = {}
        for stage in sorted(source.stages, key=lambda row: row.stage_order):
            copy = DemandScenarioStage(
                scenario_version_id=clone.id,
                stage_code=stage.stage_code,
                stage_name=stage.stage_name,
                stage_order=stage.stage_order,
                duration_hours=stage.duration_hours,
                utilization_rate=stage.utilization_rate,
                mission_intensity_factor=stage.mission_intensity_factor,
                environment_factor=stage.environment_factor,
                temperature_factor=stage.temperature_factor,
                dust_factor=stage.dust_factor,
                humidity_factor=stage.humidity_factor,
                vibration_factor=stage.vibration_factor,
                maintenance_level=stage.maintenance_level,
                description=stage.description,
            )
            session.add(copy)
            session.flush()
            stage_map[stage.id] = copy.id
        fleet_map = {}
        for fleet in source.fleet_groups:
            copy = DemandFleetGroup(
                scenario_version_id=clone.id,
                group_code=fleet.group_code,
                group_name=fleet.group_name,
                configuration_version_id=fleet.configuration_version_id,
                initial_quantity=fleet.initial_quantity,
                default_initial_age_hours=fleet.default_initial_age_hours,
                description=fleet.description,
            )
            session.add(copy)
            session.flush()
            fleet_map[fleet.id] = copy.id
            for group in fleet.age_groups:
                session.add(
                    DemandAgeGroup(
                        fleet_group_id=copy.id,
                        group_code=group.group_code,
                        group_name=group.group_name,
                        distribution_type=group.distribution_type,
                        proportion=group.proportion,
                        fixed_hours=group.fixed_hours,
                        minimum_hours=group.minimum_hours,
                        maximum_hours=group.maximum_hours,
                        mean_hours=group.mean_hours,
                        std_hours=group.std_hours,
                        mode_hours=group.mode_hours,
                        sort_order=group.sort_order,
                    )
                )
        session.flush()
        for stage in source.stages:
            for usage in stage.fleet_usages:
                session.add(
                    DemandStageFleetUsage(
                        stage_id=stage_map[stage.id],
                        fleet_group_id=fleet_map[usage.fleet_group_id],
                        active_quantity=usage.active_quantity,
                        utilization_override=usage.utilization_override,
                        equipment_intensity_factor=usage.equipment_intensity_factor,
                        environment_factor_override=usage.environment_factor_override,
                        is_active=usage.is_active,
                        notes=usage.notes,
                    )
                )
            for shock in stage.shocks:
                session.add(
                    DemandCommonShockRule(
                        stage_id=stage_map[stage.id],
                        shock_code=shock.shock_code,
                        shock_name=shock.shock_name,
                        probability=shock.probability,
                        multiplier=shock.multiplier,
                        application_mode=shock.application_mode,
                        fleet_group_id=fleet_map.get(shock.fleet_group_id),
                        affected_criticality_json=shock.affected_criticality_json,
                        affected_categories_json=shock.affected_categories_json,
                        affected_spare_parts_json=shock.affected_spare_parts_json,
                        maximum_occurrences=shock.maximum_occurrences,
                        notes=shock.notes,
                    )
                )
        for override in source.overrides:
            session.add(
                DemandParameterOverride(
                    scenario_version_id=clone.id,
                    stage_id=stage_map.get(override.stage_id),
                    fleet_group_id=fleet_map.get(override.fleet_group_id),
                    spare_part_id=override.spare_part_id,
                    reliability_profile_id=override.reliability_profile_id,
                    repair_profile_id=override.repair_profile_id,
                    model_type_override=override.model_type_override,
                    failure_process_mode=override.failure_process_mode,
                    service_level_override=override.service_level_override,
                    exclude_from_calculation=override.exclude_from_calculation,
                    reliability_parameters_json=override.reliability_parameters_json,
                    repair_parameters_json=override.repair_parameters_json,
                    adjustment_factors_json=override.adjustment_factors_json,
                    override_reason=override.override_reason,
                )
            )
        session.commit()
        session.refresh(clone)
        return clone

    def get_version(self, session: Session, version_id: int, *, full: bool = False):
        instance = (
            self.version_repository.get_full(session, version_id)
            if full
            else session.get(DemandScenarioVersion, version_id)
        )
        if instance is None:
            raise NotFoundError("demand_scenario_version", version_id)
        return instance

    def _require_draft(self, version: DemandScenarioVersion) -> None:
        if version.status is not ScenarioVersionStatus.DRAFT:
            raise ConflictError(
                "published or retired scenario version is read-only", code="SCENARIO_VERSION_LOCKED"
            )

    def update_version(self, session: Session, version_id: int, payload: ScenarioVersionUpdate):
        version = self.get_version(session, version_id)
        self._require_draft(version)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(version, key, value)
        session.commit()
        session.refresh(version)
        return version

    def add_stage(self, session: Session, version_id: int, payload: ScenarioStageCreate):
        version = self.get_version(session, version_id)
        self._require_draft(version)
        item = DemandScenarioStage(scenario_version_id=version_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def add_fleet_group(self, session: Session, version_id: int, payload: FleetGroupCreate):
        version = self.get_version(session, version_id)
        self._require_draft(version)
        configuration = session.get(ConfigurationVersion, payload.configuration_version_id)
        if configuration is None:
            raise NotFoundError("configuration_version", payload.configuration_version_id)
        item = DemandFleetGroup(scenario_version_id=version_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def add_age_group(self, session: Session, fleet_group_id: int, payload: AgeGroupCreate):
        fleet = session.get(DemandFleetGroup, fleet_group_id)
        if fleet is None:
            raise NotFoundError("demand_fleet_group", fleet_group_id)
        self._require_draft(fleet.version)
        item = DemandAgeGroup(fleet_group_id=fleet_group_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def add_fleet_usage(self, session: Session, stage_id: int, payload: FleetUsageCreate):
        stage = session.get(DemandScenarioStage, stage_id)
        if stage is None:
            raise NotFoundError("demand_stage", stage_id)
        self._require_draft(stage.version)
        fleet = session.get(DemandFleetGroup, payload.fleet_group_id)
        if fleet is None or fleet.scenario_version_id != stage.scenario_version_id:
            raise BusinessValidationError("fleet group must belong to the same scenario version")
        if payload.active_quantity > fleet.initial_quantity:
            raise BusinessValidationError("active_quantity exceeds fleet initial_quantity")
        item = DemandStageFleetUsage(stage_id=stage_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def add_override(self, session: Session, version_id: int, payload: ParameterOverrideCreate):
        version = self.get_version(session, version_id)
        self._require_draft(version)
        item = DemandParameterOverride(scenario_version_id=version_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def add_shock(self, session: Session, stage_id: int, payload: CommonShockCreate):
        stage = session.get(DemandScenarioStage, stage_id)
        if stage is None:
            raise NotFoundError("demand_stage", stage_id)
        self._require_draft(stage.version)
        item = DemandCommonShockRule(stage_id=stage_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def validate_version(self, session: Session, version_id: int) -> ScenarioValidationResult:
        version = self.get_version(session, version_id, full=True)
        issues: list[dict[str, object]] = []
        stages = sorted(version.stages, key=lambda row: row.stage_order)
        if not stages:
            issues.append({"code": "NO_STAGES", "message": "scenario requires at least one stage"})
        if [row.stage_order for row in stages] != list(range(1, len(stages) + 1)):
            issues.append(
                {"code": "NON_CONTIGUOUS_STAGE_ORDER", "message": "stage order must be contiguous"}
            )
        if not version.fleet_groups:
            issues.append(
                {"code": "NO_FLEET_GROUPS", "message": "scenario requires at least one fleet group"}
            )
        for stage in stages:
            if not [usage for usage in stage.fleet_usages if usage.is_active]:
                issues.append({"code": "STAGE_HAS_NO_FLEET_USAGE", "stage_id": stage.id})
        for fleet in version.fleet_groups:
            configuration = session.get(ConfigurationVersion, fleet.configuration_version_id)
            if (
                configuration is None
                or configuration.status is not ConfigurationStatus.PUBLISHED
                or not configuration.is_active
            ):
                issues.append({"code": "CONFIGURATION_NOT_PUBLISHED", "fleet_group_id": fleet.id})
            if fleet.age_groups:
                total = sum(Decimal(group.proportion) for group in fleet.age_groups)
                if abs(total - Decimal("1")) > Decimal("0.000001"):
                    issues.append(
                        {"code": "AGE_GROUP_PROPORTION_INVALID", "fleet_group_id": fleet.id}
                    )
        return ScenarioValidationResult(valid=not issues, issues=issues)

    def publish_version(self, session: Session, version_id: int):
        version = self.get_version(session, version_id)
        self._require_draft(version)
        result = self.validate_version(session, version_id)
        if not result.valid:
            raise BusinessValidationError(
                "scenario validation failed",
                details=result.issues,
                code="SCENARIO_VALIDATION_FAILED",
            )
        version.status = ScenarioVersionStatus.PUBLISHED
        version.published_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(version)
        return version

    def retire_version(self, session: Session, version_id: int):
        version = self.get_version(session, version_id)
        if version.status is not ScenarioVersionStatus.PUBLISHED:
            raise ConflictError("only published scenarios can be retired")
        version.status = ScenarioVersionStatus.RETIRED
        version.retired_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(version)
        return version


scenario_service = ScenarioService()
