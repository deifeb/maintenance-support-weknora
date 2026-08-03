from __future__ import annotations

from decimal import Decimal
from inspect import signature
from typing import Callable

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.models import (
    ConfigurationVersion,
    DemandFleetGroup,
    DemandParameterOverride,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    EquipmentModel,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
)
from app.models.enums import (
    ConfigurationStatus,
    DataSourceType,
    ReliabilityModelType,
)
from app.schemas.demand_scenario import (
    AgeGroupCreate,
    CommonShockCreate,
    FleetGroupCreate,
    FleetUsageCreate,
    ParameterOverrideCreate,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioTemplateUpdate,
    ScenarioVersionCreate,
    ScenarioVersionUpdate,
)
from app.security.actor import ActorContext
from app.services.scenario_service import (
    ScenarioService,
    scenario_service,
)
from sqlalchemy.orm import Session

PUBLIC_METHODS = (
    "create_template",
    "list_templates",
    "get_template",
    "update_template",
    "delete_template",
    "create_version",
    "list_versions",
    "clone_version",
    "get_version",
    "update_version",
    "add_stage",
    "add_fleet_group",
    "add_age_group",
    "add_fleet_usage",
    "add_override",
    "add_shock",
    "validate_version",
    "publish_version",
    "retire_version",
)


def add_template(
    session: Session,
    tenant_id: str,
    code: str,
) -> DemandScenarioTemplate:
    row = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=code,
        name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_version(
    session: Session,
    tenant_id: str,
    template_id: int,
    code: str,
) -> DemandScenarioVersion:
    row = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template_id,
        version_code=code,
        version_name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_stage(
    session: Session,
    tenant_id: str,
    version_id: int,
    code: str,
) -> DemandScenarioStage:
    row = DemandScenarioStage(
        tenant_id=tenant_id,
        scenario_version_id=version_id,
        stage_code=code,
        stage_name=code,
        stage_order=1,
        duration_hours=Decimal("1"),
    )
    session.add(row)
    session.flush()
    return row


def add_equipment_configuration(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> ConfigurationVersion:
    equipment = EquipmentModel(
        tenant_id=tenant_id,
        code=f"EQ-{suffix}",
        name=f"Equipment {suffix}",
    )
    session.add(equipment)
    session.flush()
    configuration = ConfigurationVersion(
        tenant_id=tenant_id,
        equipment_model_id=equipment.id,
        version_code=f"CFG-{suffix}",
        version_name=f"Configuration {suffix}",
    )
    session.add(configuration)
    session.flush()
    return configuration


def add_spare(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> SparePart:
    row = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
        unit="piece",
    )
    session.add(row)
    session.flush()
    return row


def add_reliability(
    session: Session,
    tenant_id: str,
    spare_id: int,
    suffix: str,
) -> ReliabilityProfile:
    row = ReliabilityProfile(
        tenant_id=tenant_id,
        profile_code=f"REL-{suffix}",
        spare_part_id=spare_id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.01"),
        data_source_type=DataSourceType.MANUAL_ESTIMATE,
    )
    session.add(row)
    session.flush()
    return row


def add_repair(
    session: Session,
    tenant_id: str,
    spare_id: int,
    suffix: str,
) -> RepairProfile:
    row = RepairProfile(
        tenant_id=tenant_id,
        profile_code=f"REP-{suffix}",
        profile_name=f"Repair {suffix}",
        spare_part_id=spare_id,
        repair_success_rate=Decimal("0.8"),
        condemnation_rate=Decimal("0.1"),
        repair_turnaround_hours=Decimal("24"),
    )
    session.add(row)
    session.flush()
    return row


def test_scenario_service_public_methods_require_actor() -> None:
    for method_name in PUBLIC_METHODS:
        assert "actor" in signature(
            getattr(ScenarioService, method_name)
        ).parameters


def test_template_and_version_operations_are_tenant_scoped(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    foreign_template = add_template(
        session,
        "tenant-b",
        "FOREIGN",
    )
    foreign_version = add_version(
        session,
        "tenant-b",
        foreign_template.id,
        "V1",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        scenario_service.get_template(
            session,
            actor,
            foreign_template.id,
        )
    with pytest.raises(NotFoundError):
        scenario_service.update_template(
            session,
            actor,
            foreign_template.id,
            ScenarioTemplateUpdate(name="foreign"),
        )
    with pytest.raises(NotFoundError):
        scenario_service.delete_template(
            session,
            actor,
            foreign_template.id,
        )
    with pytest.raises(NotFoundError):
        scenario_service.create_version(
            session,
            actor,
            foreign_template.id,
            ScenarioVersionCreate(
                version_code="V2",
                version_name="Version 2",
            ),
        )
    with pytest.raises(NotFoundError):
        scenario_service.list_versions(
            session,
            actor,
            foreign_template.id,
        )
    with pytest.raises(NotFoundError):
        scenario_service.get_version(
            session,
            actor,
            foreign_version.id,
        )
    with pytest.raises(NotFoundError):
        scenario_service.update_version(
            session,
            actor,
            foreign_version.id,
            ScenarioVersionUpdate(
                version_name="foreign"
            ),
        )


def test_created_scenario_entities_use_actor_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    configuration = add_equipment_configuration(
        session,
        actor.tenant_id,
        "A",
    )
    spare = add_spare(
        session,
        actor.tenant_id,
        "A",
    )
    reliability = add_reliability(
        session,
        actor.tenant_id,
        spare.id,
        "A",
    )
    repair = add_repair(
        session,
        actor.tenant_id,
        spare.id,
        "A",
    )
    template = scenario_service.create_template(
        session,
        actor,
        ScenarioTemplateCreate(
            code="SC-A",
            name="Scenario A",
        ),
    )
    version = scenario_service.create_version(
        session,
        actor,
        template.id,
        ScenarioVersionCreate(
            version_code="V1",
            version_name="Version 1",
        ),
    )
    stage = scenario_service.add_stage(
        session,
        actor,
        version.id,
        ScenarioStageCreate(
            stage_code="S1",
            stage_name="Stage 1",
            stage_order=1,
            duration_hours=Decimal("1"),
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        actor,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="Fleet 1",
            configuration_version_id=configuration.id,
            initial_quantity=1,
        ),
    )
    age = scenario_service.add_age_group(
        session,
        actor,
        fleet.id,
        AgeGroupCreate(
            group_code="A1",
            group_name="Age 1",
            distribution_type="FIXED",
            proportion=Decimal("1"),
            fixed_hours=Decimal("0"),
        ),
    )
    usage = scenario_service.add_fleet_usage(
        session,
        actor,
        stage.id,
        FleetUsageCreate(
            fleet_group_id=fleet.id,
            active_quantity=1,
        ),
    )
    override = scenario_service.add_override(
        session,
        actor,
        version.id,
        ParameterOverrideCreate(
            stage_id=stage.id,
            fleet_group_id=fleet.id,
            spare_part_id=spare.id,
            reliability_profile_id=reliability.id,
            repair_profile_id=repair.id,
        ),
    )
    shock = scenario_service.add_shock(
        session,
        actor,
        stage.id,
        CommonShockCreate(
            shock_code="SH1",
            shock_name="Shock 1",
            probability=Decimal("0.1"),
            multiplier=Decimal("2"),
            application_mode="FAILURE_RATE",
            fleet_group_id=fleet.id,
        ),
    )

    assert {
        template.tenant_id,
        version.tenant_id,
        stage.tenant_id,
        fleet.tenant_id,
        age.tenant_id,
        usage.tenant_id,
        override.tenant_id,
        shock.tenant_id,
    } == {actor.tenant_id}


def test_foreign_scenario_targets_are_rejected(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    foreign_template = add_template(
        session,
        "tenant-b",
        "FOREIGN",
    )
    foreign_version = add_version(
        session,
        "tenant-b",
        foreign_template.id,
        "V1",
    )
    foreign_stage = add_stage(
        session,
        "tenant-b",
        foreign_version.id,
        "S1",
    )
    foreign_configuration = add_equipment_configuration(
        session,
        "tenant-b",
        "B",
    )
    foreign_fleet = DemandFleetGroup(
        tenant_id="tenant-b",
        scenario_version_id=foreign_version.id,
        group_code="F1",
        group_name="Fleet 1",
        configuration_version_id=foreign_configuration.id,
        initial_quantity=1,
    )
    session.add(foreign_fleet)
    session.commit()

    with pytest.raises(NotFoundError):
        scenario_service.add_stage(
            session,
            actor,
            foreign_version.id,
            ScenarioStageCreate(
                stage_code="S2",
                stage_name="Stage 2",
                stage_order=2,
                duration_hours=Decimal("1"),
            ),
        )
    with pytest.raises(NotFoundError):
        scenario_service.add_age_group(
            session,
            actor,
            foreign_fleet.id,
            AgeGroupCreate(
                group_code="A1",
                group_name="Age 1",
                distribution_type="FIXED",
                proportion=Decimal("1"),
                fixed_hours=Decimal("0"),
            ),
        )
    with pytest.raises(NotFoundError):
        scenario_service.add_fleet_usage(
            session,
            actor,
            foreign_stage.id,
            FleetUsageCreate(
                fleet_group_id=foreign_fleet.id,
                active_quantity=1,
            ),
        )
    with pytest.raises(NotFoundError):
        scenario_service.add_shock(
            session,
            actor,
            foreign_stage.id,
            CommonShockCreate(
                shock_code="SH1",
                shock_name="Shock 1",
                probability=Decimal("0.1"),
                multiplier=Decimal("2"),
                application_mode="FAILURE_RATE",
            ),
        )


def test_foreign_reference_ids_are_rejected(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    template = add_template(
        session,
        actor.tenant_id,
        "LOCAL",
    )
    version = add_version(
        session,
        actor.tenant_id,
        template.id,
        "V1",
    )
    stage = add_stage(
        session,
        actor.tenant_id,
        version.id,
        "S1",
    )
    foreign_configuration = add_equipment_configuration(
        session,
        "tenant-b",
        "B",
    )
    foreign_spare = add_spare(
        session,
        "tenant-b",
        "B",
    )
    foreign_reliability = add_reliability(
        session,
        "tenant-b",
        foreign_spare.id,
        "B",
    )
    foreign_repair = add_repair(
        session,
        "tenant-b",
        foreign_spare.id,
        "B",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        scenario_service.add_fleet_group(
            session,
            actor,
            version.id,
            FleetGroupCreate(
                group_code="F1",
                group_name="Fleet 1",
                configuration_version_id=(
                    foreign_configuration.id
                ),
                initial_quantity=1,
            ),
        )
    with pytest.raises(NotFoundError):
        scenario_service.add_override(
            session,
            actor,
            version.id,
            ParameterOverrideCreate(
                stage_id=stage.id,
                spare_part_id=foreign_spare.id,
                reliability_profile_id=(
                    foreign_reliability.id
                ),
                repair_profile_id=foreign_repair.id,
            ),
        )


def test_cross_version_child_references_are_rejected(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    template = add_template(
        session,
        actor.tenant_id,
        "LOCAL",
    )
    version_a = add_version(
        session,
        actor.tenant_id,
        template.id,
        "V1",
    )
    version_b = add_version(
        session,
        actor.tenant_id,
        template.id,
        "V2",
    )
    stage_a = add_stage(
        session,
        actor.tenant_id,
        version_a.id,
        "S1",
    )
    configuration = add_equipment_configuration(
        session,
        actor.tenant_id,
        "A",
    )
    fleet_b = DemandFleetGroup(
        tenant_id=actor.tenant_id,
        scenario_version_id=version_b.id,
        group_code="F2",
        group_name="Fleet 2",
        configuration_version_id=configuration.id,
        initial_quantity=1,
    )
    spare = add_spare(
        session,
        actor.tenant_id,
        "A",
    )
    session.add(fleet_b)
    session.commit()

    with pytest.raises(BusinessValidationError):
        scenario_service.add_fleet_usage(
            session,
            actor,
            stage_a.id,
            FleetUsageCreate(
                fleet_group_id=fleet_b.id,
                active_quantity=1,
            ),
        )
    with pytest.raises(BusinessValidationError):
        scenario_service.add_override(
            session,
            actor,
            version_a.id,
            ParameterOverrideCreate(
                stage_id=stage_a.id,
                fleet_group_id=fleet_b.id,
                spare_part_id=spare.id,
            ),
        )
    with pytest.raises(BusinessValidationError):
        scenario_service.add_shock(
            session,
            actor,
            stage_a.id,
            CommonShockCreate(
                shock_code="SH1",
                shock_name="Shock 1",
                probability=Decimal("0.1"),
                multiplier=Decimal("2"),
                application_mode="FAILURE_RATE",
                fleet_group_id=fleet_b.id,
            ),
        )


def test_clone_rejects_foreign_configuration_reference(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    template = add_template(
        session,
        actor.tenant_id,
        "LOCAL",
    )
    version = add_version(
        session,
        actor.tenant_id,
        template.id,
        "V1",
    )
    foreign_configuration = add_equipment_configuration(
        session,
        "tenant-b",
        "B",
    )
    session.add(
        DemandFleetGroup(
            tenant_id=actor.tenant_id,
            scenario_version_id=version.id,
            group_code="F1",
            group_name="Fleet 1",
            configuration_version_id=(
                foreign_configuration.id
            ),
            initial_quantity=1,
        )
    )
    session.commit()

    with pytest.raises(NotFoundError):
        scenario_service.clone_version(
            session,
            actor,
            version.id,
            "V2",
            "Version 2",
        )

    assert (
        scenario_service.version_repository
        .get_by_business_key(
            session,
            actor.tenant_id,
            template.id,
            "V2",
        )
        is None
    )

# TASK_73B_REVIEW_FINDINGS


def test_override_profiles_must_match_selected_spare(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    template = add_template(
        session,
        actor.tenant_id,
        "PROFILE-MATCH",
    )
    version = add_version(
        session,
        actor.tenant_id,
        template.id,
        "V1",
    )
    selected_spare = add_spare(
        session,
        actor.tenant_id,
        "SELECTED",
    )
    other_spare = add_spare(
        session,
        actor.tenant_id,
        "OTHER",
    )
    mismatched_reliability = add_reliability(
        session,
        actor.tenant_id,
        other_spare.id,
        "OTHER",
    )
    mismatched_repair = add_repair(
        session,
        actor.tenant_id,
        other_spare.id,
        "OTHER",
    )
    session.commit()

    with pytest.raises(
        BusinessValidationError,
        match="reliability profile",
    ):
        scenario_service.add_override(
            session,
            actor,
            version.id,
            ParameterOverrideCreate(
                spare_part_id=selected_spare.id,
                reliability_profile_id=(
                    mismatched_reliability.id
                ),
            ),
        )

    with pytest.raises(
        BusinessValidationError,
        match="repair profile",
    ):
        scenario_service.add_override(
            session,
            actor,
            version.id,
            ParameterOverrideCreate(
                spare_part_id=selected_spare.id,
                repair_profile_id=mismatched_repair.id,
            ),
        )


def test_publish_rejects_foreign_override_reference(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    configuration = add_equipment_configuration(
        session,
        actor.tenant_id,
        "PUBLISH",
    )
    configuration.status = ConfigurationStatus.PUBLISHED
    configuration.is_active = True

    template = scenario_service.create_template(
        session,
        actor,
        ScenarioTemplateCreate(
            code="SC-PUBLISH-DIRTY",
            name="Dirty publish scenario",
        ),
    )
    version = scenario_service.create_version(
        session,
        actor,
        template.id,
        ScenarioVersionCreate(
            version_code="V1",
            version_name="Version 1",
        ),
    )
    stage = scenario_service.add_stage(
        session,
        actor,
        version.id,
        ScenarioStageCreate(
            stage_code="S1",
            stage_name="Stage 1",
            stage_order=1,
            duration_hours=Decimal("1"),
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        actor,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="Fleet 1",
            configuration_version_id=configuration.id,
            initial_quantity=1,
        ),
    )
    scenario_service.add_fleet_usage(
        session,
        actor,
        stage.id,
        FleetUsageCreate(
            fleet_group_id=fleet.id,
            active_quantity=1,
        ),
    )

    foreign_spare = add_spare(
        session,
        "tenant-b",
        "FOREIGN-PUBLISH",
    )
    session.add(
        DemandParameterOverride(
            tenant_id=actor.tenant_id,
            scenario_version_id=version.id,
            spare_part_id=foreign_spare.id,
        )
    )
    session.commit()

    with pytest.raises(NotFoundError):
        scenario_service.publish_version(
            session,
            actor,
            version.id,
        )

    session.refresh(version)
    assert version.status.value == "DRAFT"
