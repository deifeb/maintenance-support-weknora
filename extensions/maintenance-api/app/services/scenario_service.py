from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    DemandFleetGroup,
    DemandScenarioStage,
    DemandScenarioVersion,
)
from app.models.enums import (
    ConfigurationStatus,
    ScenarioVersionStatus,
)
from app.repositories import (
    ConfigurationRepository,
    DemandAgeGroupRepository,
    DemandCommonShockRepository,
    DemandFleetGroupRepository,
    DemandParameterOverrideRepository,
    DemandScenarioStageRepository,
    DemandScenarioTemplateRepository,
    DemandScenarioVersionRepository,
    DemandStageFleetUsageRepository,
    ReliabilityRepository,
    RepairRepository,
    SparePartRepository,
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
from app.security.actor import ActorContext
from app.services.base import CrudService


class ScenarioService:
    def __init__(self) -> None:
        self.template_repository = (
            DemandScenarioTemplateRepository()
        )
        self.version_repository = (
            DemandScenarioVersionRepository()
        )
        self.stage_repository = (
            DemandScenarioStageRepository()
        )
        self.fleet_repository = (
            DemandFleetGroupRepository()
        )
        self.age_group_repository = (
            DemandAgeGroupRepository()
        )
        self.fleet_usage_repository = (
            DemandStageFleetUsageRepository()
        )
        self.override_repository = (
            DemandParameterOverrideRepository()
        )
        self.shock_repository = (
            DemandCommonShockRepository()
        )
        self.configuration_repository = (
            ConfigurationRepository()
        )
        self.spare_part_repository = (
            SparePartRepository()
        )
        self.reliability_repository = (
            ReliabilityRepository()
        )
        self.repair_repository = RepairRepository()
        self.template_crud = CrudService(
            self.template_repository,
            resource_name="demand_scenario",
            read_schema=ScenarioTemplateRead,
        )

    def create_template(
        self,
        session: Session,
        actor: ActorContext,
        payload: ScenarioTemplateCreate,
    ):
        return self.template_crud.create(
            session,
            actor,
            payload,
        )

    def list_templates(
        self,
        session: Session,
        actor: ActorContext,
        **kwargs: Any,
    ):
        return self.template_crud.list(
            session,
            actor,
            **kwargs,
        )

    def get_template(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        return self.template_crud.get(
            session,
            actor,
            identifier,
        )

    def update_template(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: ScenarioTemplateUpdate,
    ):
        return self.template_crud.update(
            session,
            actor,
            identifier,
            payload,
        )

    def delete_template(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> None:
        self.template_crud.delete(
            session,
            actor,
            identifier,
        )

    def create_version(
        self,
        session: Session,
        actor: ActorContext,
        template_id: int,
        payload: ScenarioVersionCreate,
    ):
        self.get_template(
            session,
            actor,
            template_id,
        )
        if self.version_repository.get_by_business_key(
            session,
            actor.tenant_id,
            template_id,
            payload.version_code,
        ):
            raise ConflictError(
                "scenario version code already exists"
            )
        instance = self.version_repository.create(
            session,
            actor.tenant_id,
            {
                "scenario_template_id": template_id,
                **payload.model_dump(mode="json"),
            },
        )
        self._commit_and_refresh(session, instance)
        return instance

    def list_versions(
        self,
        session: Session,
        actor: ActorContext,
        template_id: int,
    ):
        self.get_template(
            session,
            actor,
            template_id,
        )
        return self.version_repository.list_for_template(
            session,
            actor.tenant_id,
            template_id,
        )

    def clone_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        version_code: str,
        version_name: str,
    ):
        source = self.get_version(
            session,
            actor,
            version_id,
            full=True,
        )
        self.get_template(
            session,
            actor,
            source.scenario_template_id,
        )
        normalized_code = version_code.strip().upper()
        if self.version_repository.get_by_business_key(
            session,
            actor.tenant_id,
            source.scenario_template_id,
            normalized_code,
        ):
            raise ConflictError(
                "scenario version code already exists"
            )

        self._validate_clone_references(
            session,
            actor,
            source,
        )

        clone = self.version_repository.create(
            session,
            actor.tenant_id,
            {
                "scenario_template_id": (
                    source.scenario_template_id
                ),
                "version_code": normalized_code,
                "version_name": version_name,
                "status": ScenarioVersionStatus.DRAFT,
                "default_service_level": (
                    source.default_service_level
                ),
                "criticality_service_levels_json": deepcopy(
                    source.criticality_service_levels_json
                ),
                "missing_parameter_policy": (
                    source.missing_parameter_policy
                ),
                "execution_mode": source.execution_mode,
                "comparison_enabled": (
                    source.comparison_enabled
                ),
                "default_initial_age_hours": (
                    source.default_initial_age_hours
                ),
                "default_repair_parameters_json": deepcopy(
                    source.default_repair_parameters_json
                ),
                "fallback_parameters_json": deepcopy(
                    source.fallback_parameters_json
                ),
                "simulation_config_json": deepcopy(
                    source.simulation_config_json
                ),
                "formula_version": source.formula_version,
                "input_schema_version": (
                    source.input_schema_version
                ),
                "description": source.description,
            },
        )

        stage_map: dict[int, int] = {}
        for stage in sorted(
            source.stages,
            key=lambda row: row.stage_order,
        ):
            copied_stage = self.stage_repository.create(
                session,
                actor.tenant_id,
                {
                    "scenario_version_id": clone.id,
                    "stage_code": stage.stage_code,
                    "stage_name": stage.stage_name,
                    "stage_order": stage.stage_order,
                    "duration_hours": stage.duration_hours,
                    "utilization_rate": (
                        stage.utilization_rate
                    ),
                    "mission_intensity_factor": (
                        stage.mission_intensity_factor
                    ),
                    "environment_factor": (
                        stage.environment_factor
                    ),
                    "temperature_factor": (
                        stage.temperature_factor
                    ),
                    "dust_factor": stage.dust_factor,
                    "humidity_factor": (
                        stage.humidity_factor
                    ),
                    "vibration_factor": (
                        stage.vibration_factor
                    ),
                    "maintenance_level": (
                        stage.maintenance_level
                    ),
                    "description": stage.description,
                },
            )
            stage_map[stage.id] = copied_stage.id

        fleet_map: dict[int, int] = {}
        for fleet in source.fleet_groups:
            copied_fleet = self.fleet_repository.create(
                session,
                actor.tenant_id,
                {
                    "scenario_version_id": clone.id,
                    "group_code": fleet.group_code,
                    "group_name": fleet.group_name,
                    "configuration_version_id": (
                        fleet.configuration_version_id
                    ),
                    "initial_quantity": (
                        fleet.initial_quantity
                    ),
                    "default_initial_age_hours": (
                        fleet.default_initial_age_hours
                    ),
                    "description": fleet.description,
                },
            )
            fleet_map[fleet.id] = copied_fleet.id

            for age_group in fleet.age_groups:
                self.age_group_repository.create(
                    session,
                    actor.tenant_id,
                    {
                        "fleet_group_id": copied_fleet.id,
                        "group_code": age_group.group_code,
                        "group_name": age_group.group_name,
                        "distribution_type": (
                            age_group.distribution_type
                        ),
                        "proportion": age_group.proportion,
                        "fixed_hours": age_group.fixed_hours,
                        "minimum_hours": (
                            age_group.minimum_hours
                        ),
                        "maximum_hours": (
                            age_group.maximum_hours
                        ),
                        "mean_hours": age_group.mean_hours,
                        "std_hours": age_group.std_hours,
                        "mode_hours": age_group.mode_hours,
                        "sort_order": age_group.sort_order,
                    },
                )

        for stage in source.stages:
            for usage in stage.fleet_usages:
                self.fleet_usage_repository.create(
                    session,
                    actor.tenant_id,
                    {
                        "stage_id": stage_map[stage.id],
                        "fleet_group_id": (
                            fleet_map[
                                usage.fleet_group_id
                            ]
                        ),
                        "active_quantity": (
                            usage.active_quantity
                        ),
                        "utilization_override": (
                            usage.utilization_override
                        ),
                        "equipment_intensity_factor": (
                            usage.equipment_intensity_factor
                        ),
                        "environment_factor_override": (
                            usage.environment_factor_override
                        ),
                        "is_active": usage.is_active,
                        "notes": usage.notes,
                    },
                )

            for shock in stage.shocks:
                self.shock_repository.create(
                    session,
                    actor.tenant_id,
                    {
                        "stage_id": stage_map[stage.id],
                        "shock_code": shock.shock_code,
                        "shock_name": shock.shock_name,
                        "probability": shock.probability,
                        "multiplier": shock.multiplier,
                        "application_mode": (
                            shock.application_mode
                        ),
                        "fleet_group_id": (
                            None
                            if shock.fleet_group_id is None
                            else fleet_map[
                                shock.fleet_group_id
                            ]
                        ),
                        "affected_criticality_json": (
                            deepcopy(
                                shock
                                .affected_criticality_json
                            )
                        ),
                        "affected_categories_json": (
                            deepcopy(
                                shock
                                .affected_categories_json
                            )
                        ),
                        "affected_spare_parts_json": (
                            deepcopy(
                                shock
                                .affected_spare_parts_json
                            )
                        ),
                        "maximum_occurrences": (
                            shock.maximum_occurrences
                        ),
                        "notes": shock.notes,
                    },
                )

        for override in source.overrides:
            self.override_repository.create(
                session,
                actor.tenant_id,
                {
                    "scenario_version_id": clone.id,
                    "stage_id": (
                        None
                        if override.stage_id is None
                        else stage_map[override.stage_id]
                    ),
                    "fleet_group_id": (
                        None
                        if override.fleet_group_id is None
                        else fleet_map[
                            override.fleet_group_id
                        ]
                    ),
                    "spare_part_id": (
                        override.spare_part_id
                    ),
                    "reliability_profile_id": (
                        override.reliability_profile_id
                    ),
                    "repair_profile_id": (
                        override.repair_profile_id
                    ),
                    "model_type_override": (
                        override.model_type_override
                    ),
                    "failure_process_mode": (
                        override.failure_process_mode
                    ),
                    "service_level_override": (
                        override.service_level_override
                    ),
                    "exclude_from_calculation": (
                        override.exclude_from_calculation
                    ),
                    "reliability_parameters_json": (
                        deepcopy(
                            override
                            .reliability_parameters_json
                        )
                    ),
                    "repair_parameters_json": deepcopy(
                        override.repair_parameters_json
                    ),
                    "adjustment_factors_json": deepcopy(
                        override.adjustment_factors_json
                    ),
                    "override_reason": (
                        override.override_reason
                    ),
                },
            )

        self._commit_and_refresh(session, clone)
        return clone

    def get_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        *,
        full: bool = False,
    ):
        instance = (
            self.version_repository.get_full(
                session,
                actor.tenant_id,
                version_id,
            )
            if full
            else self.version_repository.get_by_id(
                session,
                actor.tenant_id,
                version_id,
            )
        )
        if instance is None:
            raise NotFoundError(
                "demand_scenario_version",
                version_id,
            )
        return instance

    def update_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        payload: ScenarioVersionUpdate,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        self._require_draft(version)
        self.version_repository.update(
            session,
            actor.tenant_id,
            version,
            payload.model_dump(
                exclude_unset=True,
                mode="json",
            ),
        )
        self._commit_and_refresh(session, version)
        return version

    def add_stage(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        payload: ScenarioStageCreate,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        self._require_draft(version)
        item = self.stage_repository.create(
            session,
            actor.tenant_id,
            {
                "scenario_version_id": version.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def add_fleet_group(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        payload: FleetGroupCreate,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        self._require_draft(version)
        self._configuration(
            session,
            actor,
            payload.configuration_version_id,
        )
        item = self.fleet_repository.create(
            session,
            actor.tenant_id,
            {
                "scenario_version_id": version.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def add_age_group(
        self,
        session: Session,
        actor: ActorContext,
        fleet_group_id: int,
        payload: AgeGroupCreate,
    ):
        fleet = self._fleet(
            session,
            actor,
            fleet_group_id,
        )
        version = self.get_version(
            session,
            actor,
            fleet.scenario_version_id,
        )
        self._require_draft(version)
        item = self.age_group_repository.create(
            session,
            actor.tenant_id,
            {
                "fleet_group_id": fleet.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def add_fleet_usage(
        self,
        session: Session,
        actor: ActorContext,
        stage_id: int,
        payload: FleetUsageCreate,
    ):
        stage = self._stage(
            session,
            actor,
            stage_id,
        )
        version = self.get_version(
            session,
            actor,
            stage.scenario_version_id,
        )
        self._require_draft(version)
        fleet = self._fleet(
            session,
            actor,
            payload.fleet_group_id,
        )
        if (
            fleet.scenario_version_id
            != stage.scenario_version_id
        ):
            raise BusinessValidationError(
                "fleet group must belong to "
                "the same scenario version"
            )
        if payload.active_quantity > fleet.initial_quantity:
            raise BusinessValidationError(
                "active_quantity exceeds "
                "fleet initial_quantity"
            )
        item = self.fleet_usage_repository.create(
            session,
            actor.tenant_id,
            {
                "stage_id": stage.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def add_override(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
        payload: ParameterOverrideCreate,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        self._require_draft(version)
        self._validate_override_references(
            session,
            actor,
            version,
            payload.stage_id,
            payload.fleet_group_id,
            payload.spare_part_id,
            payload.reliability_profile_id,
            payload.repair_profile_id,
        )
        item = self.override_repository.create(
            session,
            actor.tenant_id,
            {
                "scenario_version_id": version.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def add_shock(
        self,
        session: Session,
        actor: ActorContext,
        stage_id: int,
        payload: CommonShockCreate,
    ):
        stage = self._stage(
            session,
            actor,
            stage_id,
        )
        version = self.get_version(
            session,
            actor,
            stage.scenario_version_id,
        )
        self._require_draft(version)
        if payload.fleet_group_id is not None:
            fleet = self._fleet(
                session,
                actor,
                payload.fleet_group_id,
            )
            if (
                fleet.scenario_version_id
                != stage.scenario_version_id
            ):
                raise BusinessValidationError(
                    "fleet group must belong to "
                    "the same scenario version"
                )
        item = self.shock_repository.create(
            session,
            actor.tenant_id,
            {
                "stage_id": stage.id,
                **payload.model_dump(),
            },
        )
        self._commit_and_refresh(session, item)
        return item

    def validate_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
    ) -> ScenarioValidationResult:
        version = self.get_version(
            session,
            actor,
            version_id,
            full=True,
        )
        issues: list[dict[str, object]] = []
        stages = sorted(
            version.stages,
            key=lambda row: row.stage_order,
        )
        if not stages:
            issues.append(
                {
                    "code": "NO_STAGES",
                    "message": (
                        "scenario requires at least one stage"
                    ),
                }
            )
        if [row.stage_order for row in stages] != list(
            range(1, len(stages) + 1)
        ):
            issues.append(
                {
                    "code": "NON_CONTIGUOUS_STAGE_ORDER",
                    "message": (
                        "stage order must be contiguous"
                    ),
                }
            )
        if not version.fleet_groups:
            issues.append(
                {
                    "code": "NO_FLEET_GROUPS",
                    "message": (
                        "scenario requires at least "
                        "one fleet group"
                    ),
                }
            )
        for stage in stages:
            if not [
                usage
                for usage in stage.fleet_usages
                if usage.is_active
            ]:
                issues.append(
                    {
                        "code": "STAGE_HAS_NO_FLEET_USAGE",
                        "stage_id": stage.id,
                    }
                )
        for fleet in version.fleet_groups:
            configuration = (
                self.configuration_repository.get_by_id(
                    session,
                    actor.tenant_id,
                    fleet.configuration_version_id,
                )
            )
            if (
                configuration is None
                or configuration.status
                is not ConfigurationStatus.PUBLISHED
                or not configuration.is_active
            ):
                issues.append(
                    {
                        "code": "CONFIGURATION_NOT_PUBLISHED",
                        "fleet_group_id": fleet.id,
                    }
                )
            if fleet.age_groups:
                total = sum(
                    Decimal(group.proportion)
                    for group in fleet.age_groups
                )
                if (
                    abs(total - Decimal("1"))
                    > Decimal("0.000001")
                ):
                    issues.append(
                        {
                            "code": (
                                "AGE_GROUP_PROPORTION_INVALID"
                            ),
                            "fleet_group_id": fleet.id,
                        }
                    )
        for override in version.overrides:
            self._validate_override_references(
                session,
                actor,
                version,
                override.stage_id,
                override.fleet_group_id,
                override.spare_part_id,
                override.reliability_profile_id,
                override.repair_profile_id,
            )

        return ScenarioValidationResult(
            valid=not issues,
            issues=issues,
        )

    def publish_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        self._require_draft(version)
        result = self.validate_version(
            session,
            actor,
            version_id,
        )
        if not result.valid:
            raise BusinessValidationError(
                "scenario validation failed",
                details=result.issues,
                code="SCENARIO_VALIDATION_FAILED",
            )
        self.version_repository.update(
            session,
            actor.tenant_id,
            version,
            {
                "status": ScenarioVersionStatus.PUBLISHED,
                "published_at": datetime.now(timezone.utc),
            },
        )
        self._commit_and_refresh(session, version)
        return version

    def retire_version(
        self,
        session: Session,
        actor: ActorContext,
        version_id: int,
    ):
        version = self.get_version(
            session,
            actor,
            version_id,
        )
        if (
            version.status
            is not ScenarioVersionStatus.PUBLISHED
        ):
            raise ConflictError(
                "only published scenarios can be retired"
            )
        self.version_repository.update(
            session,
            actor.tenant_id,
            version,
            {
                "status": ScenarioVersionStatus.RETIRED,
                "retired_at": datetime.now(timezone.utc),
            },
        )
        self._commit_and_refresh(session, version)
        return version

    def _template(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        return self.get_template(
            session,
            actor,
            identifier,
        )

    def _stage(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> DemandScenarioStage:
        row = self.stage_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "demand_stage",
                identifier,
            )
        return row

    def _fleet(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> DemandFleetGroup:
        row = self.fleet_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "demand_fleet_group",
                identifier,
            )
        return row

    def _configuration(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        row = self.configuration_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "configuration_version",
                identifier,
            )
        return row

    def _spare_part(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        row = self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "spare_part",
                identifier,
            )
        return row

    def _reliability_profile(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        row = self.reliability_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "reliability_profile",
                identifier,
            )
        return row

    def _repair_profile(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ):
        row = self.repair_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if row is None:
            raise NotFoundError(
                "repair_profile",
                identifier,
            )
        return row

    def _validate_override_references(
        self,
        session: Session,
        actor: ActorContext,
        version: DemandScenarioVersion,
        stage_id: int | None,
        fleet_group_id: int | None,
        spare_part_id: int,
        reliability_profile_id: int | None,
        repair_profile_id: int | None,
    ) -> None:
        if stage_id is not None:
            stage = self._stage(
                session,
                actor,
                stage_id,
            )
            if (
                stage.scenario_version_id
                != version.id
            ):
                raise BusinessValidationError(
                    "stage must belong to "
                    "the same scenario version"
                )
        if fleet_group_id is not None:
            fleet = self._fleet(
                session,
                actor,
                fleet_group_id,
            )
            if (
                fleet.scenario_version_id
                != version.id
            ):
                raise BusinessValidationError(
                    "fleet group must belong to "
                    "the same scenario version"
                )
        spare_part = self._spare_part(
            session,
            actor,
            spare_part_id,
        )
        if reliability_profile_id is not None:
            reliability_profile = (
                self._reliability_profile(
                    session,
                    actor,
                    reliability_profile_id,
                )
            )
            if (
                reliability_profile.spare_part_id
                != spare_part.id
            ):
                raise BusinessValidationError(
                    "reliability profile must belong "
                    "to the selected spare part"
                )
        if repair_profile_id is not None:
            repair_profile = self._repair_profile(
                session,
                actor,
                repair_profile_id,
            )
            if repair_profile.spare_part_id != spare_part.id:
                raise BusinessValidationError(
                    "repair profile must belong "
                    "to the selected spare part"
                )

    def _validate_clone_references(
        self,
        session: Session,
        actor: ActorContext,
        source: DemandScenarioVersion,
    ) -> None:
        stage_ids = {
            stage.id
            for stage in source.stages
        }
        fleet_ids = {
            fleet.id
            for fleet in source.fleet_groups
        }

        for fleet in source.fleet_groups:
            self._configuration(
                session,
                actor,
                fleet.configuration_version_id,
            )

        for stage in source.stages:
            for usage in stage.fleet_usages:
                if usage.fleet_group_id not in fleet_ids:
                    raise BusinessValidationError(
                        "fleet usage points outside "
                        "the scenario version"
                    )
            for shock in stage.shocks:
                if (
                    shock.fleet_group_id is not None
                    and shock.fleet_group_id
                    not in fleet_ids
                ):
                    raise BusinessValidationError(
                        "shock points outside "
                        "the scenario version"
                    )

        for override in source.overrides:
            if (
                override.stage_id is not None
                and override.stage_id not in stage_ids
            ):
                raise BusinessValidationError(
                    "override stage points outside "
                    "the scenario version"
                )
            if (
                override.fleet_group_id is not None
                and override.fleet_group_id
                not in fleet_ids
            ):
                raise BusinessValidationError(
                    "override fleet group points outside "
                    "the scenario version"
                )
            self._validate_override_references(
                session,
                actor,
                source,
                override.stage_id,
                override.fleet_group_id,
                override.spare_part_id,
                override.reliability_profile_id,
                override.repair_profile_id,
            )

    @staticmethod
    def _require_draft(
        version: DemandScenarioVersion,
    ) -> None:
        if (
            version.status
            is not ScenarioVersionStatus.DRAFT
        ):
            raise ConflictError(
                "published or retired scenario "
                "version is read-only",
                code="SCENARIO_VERSION_LOCKED",
            )

    @staticmethod
    def _commit_and_refresh(
        session: Session,
        instance: Any,
    ) -> None:
        session.commit()
        session.refresh(instance)


scenario_service = ScenarioService()
