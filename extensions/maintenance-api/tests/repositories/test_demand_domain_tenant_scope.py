from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from inspect import signature

import app.repositories.demand_calculation_repository as calculation_repositories
import app.repositories.demand_scenario_repository as scenario_repositories
import pytest
from app.models import (
    ConfigurationVersion,
    DemandAgeGroup,
    DemandCalculation,
    DemandCalculationRun,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandParameterOverride,
    DemandRunContribution,
    DemandRunItemResult,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
    EquipmentModel,
    SparePart,
)
from app.models.enums import (
    AgeDistributionType,
    CalculationExecutionType,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    ShockApplicationMode,
    ShortageRiskLevel,
)
from sqlalchemy.orm import Session


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


def add_equipment_and_configuration(
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


def add_calculation(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    idempotency_key: str | None = None,
) -> DemandCalculation:
    now = datetime.now(timezone.utc)
    row = DemandCalculation(
        tenant_id=tenant_id,
        calculation_code=f"CALC-{suffix}",
        calculation_name=f"Calculation {suffix}",
        execution_type=CalculationExecutionType.SYNCHRONOUS,
        requested_mode=DemandExecutionMode.ANALYTICAL,
        idempotency_key=idempotency_key,
        input_snapshot_json={},
        input_snapshot_hash=(suffix * 64)[:64],
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(row)
    session.flush()
    return row


def add_run(
    session: Session,
    tenant_id: str,
    calculation_id: int,
    mode: DemandExecutionMode,
) -> DemandCalculationRun:
    row = DemandCalculationRun(
        tenant_id=tenant_id,
        calculation_id=calculation_id,
        run_mode=mode,
        engine_version="test",
        formula_version="test",
    )
    session.add(row)
    session.flush()
    return row


def add_result(
    session: Session,
    tenant_id: str,
    run_id: int,
    spare: SparePart,
) -> DemandRunItemResult:
    zero = Decimal("0")
    row = DemandRunItemResult(
        tenant_id=tenant_id,
        calculation_run_id=run_id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        calculation_status=ItemCalculationStatus.CALCULATED,
        failure_process_mode=FailureProcessMode.AUTO,
        target_service_level=Decimal("0.9"),
        expected_demand=zero,
        variance=zero,
        standard_deviation=zero,
        p50=zero,
        p80=zero,
        p90=zero,
        p95=zero,
        p99=zero,
        target_quantile_demand=zero,
        gross_replacement_demand=zero,
        repair_pipeline_demand=zero,
        repair_pipeline_peak=zero,
        net_consumption_demand=zero,
        recommended_spare_quantity=zero,
        shortage_risk_level=ShortageRiskLevel.NONE,
    )
    session.add(row)
    session.flush()
    return row


REPOSITORY_METHOD_MATRIX = [
    (
        scenario_repositories,
        "DemandScenarioTemplateRepository",
        ("count_references",),
    ),
    (
        scenario_repositories,
        "DemandScenarioVersionRepository",
        (
            "get_by_business_key",
            "list_for_template",
            "get_full",
        ),
    ),
    (
        calculation_repositories,
        "DemandCalculationRepository",
        (
            "get_by_idempotency_key",
            "get_full",
        ),
    ),
    (
        calculation_repositories,
        "DemandCalculationRunRepository",
        ("list_for_calculation",),
    ),
    (
        calculation_repositories,
        "DemandRunItemResultRepository",
        ("list_for_run",),
    ),
    (
        calculation_repositories,
        "DemandRunContributionRepository",
        ("list_for_run",),
    ),
]


@pytest.mark.parametrize(
    ("module", "class_name", "method_names"),
    REPOSITORY_METHOD_MATRIX,
)
def test_demand_repository_methods_require_tenant_id(
    module,
    class_name: str,
    method_names: tuple[str, ...],
) -> None:
    repository_type = getattr(module, class_name, None)
    assert repository_type is not None

    for method_name in method_names:
        assert "tenant_id" in signature(
            getattr(repository_type, method_name)
        ).parameters


def test_demand_child_repositories_are_available() -> None:
    class_names = (
        "DemandScenarioStageRepository",
        "DemandFleetGroupRepository",
        "DemandAgeGroupRepository",
        "DemandStageFleetUsageRepository",
        "DemandParameterOverrideRepository",
        "DemandCommonShockRepository",
    )

    for class_name in class_names:
        assert getattr(
            scenario_repositories,
            class_name,
            None,
        ) is not None


def test_scenario_template_references_are_tenant_scoped(
    session: Session,
) -> None:
    template = add_template(
        session,
        "tenant-a",
        "SCENARIO",
    )
    add_version(
        session,
        "tenant-a",
        template.id,
        "V-A",
    )
    add_version(
        session,
        "tenant-b",
        template.id,
        "V-B",
    )
    session.commit()

    repository = (
        scenario_repositories
        .DemandScenarioTemplateRepository()
    )

    assert repository.count_references(
        session,
        "tenant-a",
        template.id,
    ) == 1
    assert repository.count_references(
        session,
        "tenant-b",
        template.id,
    ) == 1


def test_scenario_version_business_queries_are_tenant_scoped(
    session: Session,
) -> None:
    template = add_template(
        session,
        "tenant-a",
        "SCENARIO",
    )
    version_a = add_version(
        session,
        "tenant-a",
        template.id,
        "V-A",
    )
    version_b = add_version(
        session,
        "tenant-b",
        template.id,
        "V-B",
    )
    session.commit()

    repository = (
        scenario_repositories
        .DemandScenarioVersionRepository()
    )

    assert repository.get_by_business_key(
        session,
        "tenant-a",
        template.id,
        "V-A",
    ).id == version_a.id
    assert repository.get_by_business_key(
        session,
        "tenant-a",
        template.id,
        "V-B",
    ) is None
    assert [
        row.id
        for row in repository.list_for_template(
            session,
            "tenant-a",
            template.id,
        )
    ] == [version_a.id]
    assert [
        row.id
        for row in repository.list_for_template(
            session,
            "tenant-b",
            template.id,
        )
    ] == [version_b.id]


def test_scenario_full_filters_nested_children(
    session: Session,
) -> None:
    template = add_template(
        session,
        "tenant-a",
        "SCENARIO",
    )
    version = add_version(
        session,
        "tenant-a",
        template.id,
        "V1",
    )
    configuration = add_equipment_and_configuration(
        session,
        "tenant-a",
        "A",
    )
    spare_a = add_spare(session, "tenant-a", "A")
    spare_b = add_spare(session, "tenant-b", "B")

    stage_a = DemandScenarioStage(
        tenant_id="tenant-a",
        scenario_version_id=version.id,
        stage_code="STAGE-A",
        stage_name="Stage A",
        stage_order=1,
        duration_hours=Decimal("1"),
    )
    stage_b = DemandScenarioStage(
        tenant_id="tenant-b",
        scenario_version_id=version.id,
        stage_code="STAGE-B",
        stage_name="Stage B",
        stage_order=2,
        duration_hours=Decimal("1"),
    )
    session.add_all([stage_a, stage_b])
    session.flush()

    fleet_a = DemandFleetGroup(
        tenant_id="tenant-a",
        scenario_version_id=version.id,
        group_code="FLEET-A",
        group_name="Fleet A",
        configuration_version_id=configuration.id,
        initial_quantity=1,
    )
    fleet_b = DemandFleetGroup(
        tenant_id="tenant-b",
        scenario_version_id=version.id,
        group_code="FLEET-B",
        group_name="Fleet B",
        configuration_version_id=configuration.id,
        initial_quantity=1,
    )
    session.add_all([fleet_a, fleet_b])
    session.flush()

    age_a = DemandAgeGroup(
        tenant_id="tenant-a",
        fleet_group_id=fleet_a.id,
        group_code="AGE-A",
        group_name="Age A",
        distribution_type=AgeDistributionType.FIXED,
        proportion=Decimal("1"),
        fixed_hours=Decimal("0"),
    )
    age_b = DemandAgeGroup(
        tenant_id="tenant-b",
        fleet_group_id=fleet_a.id,
        group_code="AGE-B",
        group_name="Age B",
        distribution_type=AgeDistributionType.FIXED,
        proportion=Decimal("1"),
        fixed_hours=Decimal("0"),
    )
    usage_a = DemandStageFleetUsage(
        tenant_id="tenant-a",
        stage_id=stage_a.id,
        fleet_group_id=fleet_a.id,
        active_quantity=1,
    )
    usage_b = DemandStageFleetUsage(
        tenant_id="tenant-b",
        stage_id=stage_a.id,
        fleet_group_id=fleet_b.id,
        active_quantity=1,
    )
    override_a = DemandParameterOverride(
        tenant_id="tenant-a",
        scenario_version_id=version.id,
        spare_part_id=spare_a.id,
    )
    override_b = DemandParameterOverride(
        tenant_id="tenant-b",
        scenario_version_id=version.id,
        spare_part_id=spare_b.id,
    )
    shock_a = DemandCommonShockRule(
        tenant_id="tenant-a",
        stage_id=stage_a.id,
        shock_code="SHOCK-A",
        shock_name="Shock A",
        probability=Decimal("0.1"),
        multiplier=Decimal("2"),
        application_mode=ShockApplicationMode.FAILURE_RATE,
    )
    shock_b = DemandCommonShockRule(
        tenant_id="tenant-b",
        stage_id=stage_a.id,
        shock_code="SHOCK-B",
        shock_name="Shock B",
        probability=Decimal("0.1"),
        multiplier=Decimal("2"),
        application_mode=ShockApplicationMode.FAILURE_RATE,
    )
    session.add_all(
        [
            age_a,
            age_b,
            usage_a,
            usage_b,
            override_a,
            override_b,
            shock_a,
            shock_b,
        ]
    )
    session.commit()

    version_id = version.id
    session.expunge_all()

    repository = (
        scenario_repositories
        .DemandScenarioVersionRepository()
    )
    loaded = repository.get_full(
        session,
        "tenant-a",
        version_id,
    )

    assert loaded is not None
    assert [row.tenant_id for row in loaded.stages] == [
        "tenant-a"
    ]
    assert [
        row.tenant_id
        for row in loaded.fleet_groups
    ] == ["tenant-a"]
    assert [
        row.tenant_id
        for row in loaded.overrides
    ] == ["tenant-a"]
    assert [
        row.tenant_id
        for row in loaded.stages[0].fleet_usages
    ] == ["tenant-a"]
    assert [
        row.tenant_id
        for row in loaded.stages[0].shocks
    ] == ["tenant-a"]
    assert [
        row.tenant_id
        for row in loaded.fleet_groups[0].age_groups
    ] == ["tenant-a"]
    assert [
        row.tenant_id
        for row in loaded.fleet_groups[0].stage_usages
    ] == ["tenant-a"]


def test_calculation_idempotency_is_tenant_scoped(
    session: Session,
) -> None:
    calculation_a = add_calculation(
        session,
        "tenant-a",
        "A",
        idempotency_key="shared-key",
    )
    calculation_b = add_calculation(
        session,
        "tenant-b",
        "B",
        idempotency_key="shared-key",
    )
    session.commit()

    repository = (
        calculation_repositories
        .DemandCalculationRepository()
    )

    assert repository.get_by_idempotency_key(
        session,
        "tenant-a",
        "shared-key",
    ).id == calculation_a.id
    assert repository.get_by_idempotency_key(
        session,
        "tenant-b",
        "shared-key",
    ).id == calculation_b.id


def test_calculation_full_filters_foreign_runs(
    session: Session,
) -> None:
    calculation = add_calculation(
        session,
        "tenant-a",
        "A",
    )
    visible = add_run(
        session,
        "tenant-a",
        calculation.id,
        DemandExecutionMode.ANALYTICAL,
    )
    add_run(
        session,
        "tenant-b",
        calculation.id,
        DemandExecutionMode.MONTE_CARLO,
    )
    session.commit()

    calculation_id = calculation.id
    visible_id = visible.id
    session.expunge_all()

    repository = (
        calculation_repositories
        .DemandCalculationRepository()
    )
    loaded = repository.get_full(
        session,
        "tenant-a",
        calculation_id,
    )

    assert loaded is not None
    assert [row.id for row in loaded.runs] == [visible_id]


def test_calculation_child_lists_are_tenant_scoped(
    session: Session,
) -> None:
    calculation = add_calculation(
        session,
        "tenant-a",
        "A",
    )
    run_a = add_run(
        session,
        "tenant-a",
        calculation.id,
        DemandExecutionMode.ANALYTICAL,
    )
    run_b = add_run(
        session,
        "tenant-b",
        calculation.id,
        DemandExecutionMode.MONTE_CARLO,
    )
    spare_a = add_spare(session, "tenant-a", "A")
    spare_b = add_spare(session, "tenant-b", "B")
    result_a = add_result(
        session,
        "tenant-a",
        run_a.id,
        spare_a,
    )
    add_result(
        session,
        "tenant-b",
        run_a.id,
        spare_b,
    )
    contribution_a = DemandRunContribution(
        tenant_id="tenant-a",
        calculation_run_id=run_a.id,
        spare_part_id=spare_a.id,
    )
    contribution_b = DemandRunContribution(
        tenant_id="tenant-b",
        calculation_run_id=run_a.id,
        spare_part_id=spare_b.id,
    )
    session.add_all([contribution_a, contribution_b])
    session.commit()

    run_repository = (
        calculation_repositories
        .DemandCalculationRunRepository()
    )
    result_repository = (
        calculation_repositories
        .DemandRunItemResultRepository()
    )
    contribution_repository = (
        calculation_repositories
        .DemandRunContributionRepository()
    )

    assert [
        row.id
        for row in run_repository.list_for_calculation(
            session,
            "tenant-a",
            calculation.id,
        )
    ] == [run_a.id]
    assert [
        row.id
        for row in run_repository.list_for_calculation(
            session,
            "tenant-b",
            calculation.id,
        )
    ] == [run_b.id]
    assert [
        row.id
        for row in result_repository.list_for_run(
            session,
            "tenant-a",
            run_a.id,
        )
    ] == [result_a.id]
    assert [
        row.id
        for row in contribution_repository.list_for_run(
            session,
            "tenant-a",
            run_a.id,
        )
    ] == [contribution_a.id]


def test_calculation_group_repository_never_returns_foreign_tenant(
    session: Session,
) -> None:
    try:
        from app.models.enums import CalculationGroupStatus
        from app.repositories.calculation_group_repository import (
            CalculationGroupRepository,
        )
    except (ImportError, ModuleNotFoundError) as error:
        pytest.fail(
            f"calculation group persistence is missing: {error}"
        )

    template_a = add_template(
        session,
        "tenant-a",
        "GROUP-A",
    )
    version_a = add_version(
        session,
        "tenant-a",
        template_a.id,
        "V-A",
    )
    template_b = add_template(
        session,
        "tenant-b",
        "GROUP-B",
    )
    version_b = add_version(
        session,
        "tenant-b",
        template_b.id,
        "V-B",
    )
    repository = CalculationGroupRepository()
    group_a = repository.create(
        session,
        "tenant-a",
        {
            "scenario_version_id": version_a.id,
            "status": CalculationGroupStatus.PENDING,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "recommendation_snapshot_json": {},
            "parameter_snapshot_json": {},
            "created_by_user_id": "user-a",
            "created_by_request_id": "request-a",
        },
    )
    group_b = repository.create(
        session,
        "tenant-b",
        {
            "scenario_version_id": version_b.id,
            "status": CalculationGroupStatus.PENDING,
            "primary_candidate_key": "EXPONENTIAL:ANALYTICAL",
            "recommendation_snapshot_json": {},
            "parameter_snapshot_json": {},
            "created_by_user_id": "user-b",
            "created_by_request_id": "request-b",
        },
    )

    assert repository.get(
        session,
        "tenant-a",
        group_a.id,
    ).id == group_a.id
    assert repository.get(
        session,
        "tenant-a",
        group_b.id,
    ) is None
    assert repository.get_for_update(
        session,
        "tenant-a",
        group_b.id,
    ) is None
    rows, total = repository.list_page(
        session,
        "tenant-a",
    )
    assert total == 1
    assert [row.id for row in rows] == [group_a.id]


def test_calculation_group_events_receive_monotonic_sequence(
    session: Session,
) -> None:
    try:
        from app.models.enums import CalculationGroupStatus
        from app.repositories.calculation_group_repository import (
            CalculationGroupRepository,
        )
    except (ImportError, ModuleNotFoundError) as error:
        pytest.fail(
            f"calculation group persistence is missing: {error}"
        )

    template = add_template(
        session,
        "tenant-a",
        "GROUP-EVENTS",
    )
    version = add_version(
        session,
        "tenant-a",
        template.id,
        "V1",
    )
    repository = CalculationGroupRepository()
    group = repository.create(
        session,
        "tenant-a",
        {
            "scenario_version_id": version.id,
            "status": CalculationGroupStatus.PENDING,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "recommendation_snapshot_json": {},
            "parameter_snapshot_json": {},
            "created_by_user_id": "user-a",
            "created_by_request_id": "request-a",
        },
    )

    first = repository.append_event(
        session,
        "tenant-a",
        group.id,
        event_type="group.created",
        payload={"status": "PENDING"},
    )
    second = repository.append_event(
        session,
        "tenant-a",
        group.id,
        event_type="child.queued",
        payload={"candidate_key": "WEIBULL:ANALYTICAL"},
    )

    assert [first.sequence, second.sequence] == [1, 2]
    assert group.last_event_sequence == 2


def test_calculation_group_child_attempts_replace_current_attempt(
    session: Session,
) -> None:
    from app.models.enums import (
        CalculationGroupStatus,
        DemandExecutionMode,
        ReliabilityModelType,
    )
    from app.repositories.calculation_group_repository import (
        CalculationGroupChildRepository,
        CalculationGroupRepository,
    )

    template = add_template(session, "tenant-a", "GROUP-ATTEMPTS")
    version = add_version(
        session,
        "tenant-a",
        template.id,
        "V1",
    )
    calculation = add_calculation(session, "tenant-a", "ATTEMPT")
    group = CalculationGroupRepository().create(
        session,
        "tenant-a",
        {
            "scenario_version_id": version.id,
            "status": CalculationGroupStatus.PENDING,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "recommendation_snapshot_json": {},
            "parameter_snapshot_json": {},
            "created_by_user_id": "user-a",
            "created_by_request_id": "request-a",
        },
    )
    repository = CalculationGroupChildRepository()
    attempt_data = {
        "candidate_key": "WEIBULL:ANALYTICAL",
        "reliability_model": ReliabilityModelType.WEIBULL,
        "execution_mode": DemandExecutionMode.ANALYTICAL,
        "calculation_id": calculation.id,
        "is_primary": True,
    }

    first = repository.create_attempt(
        session,
        "tenant-a",
        group.id,
        attempt_data,
    )
    second = repository.create_attempt(
        session,
        "tenant-a",
        group.id,
        attempt_data,
    )

    assert (first.attempt_number, first.is_current_attempt) == (
        1,
        False,
    )
    assert (second.attempt_number, second.is_current_attempt) == (
        2,
        True,
    )
    assert [
        row.id
        for row in repository.current_for_group(
            session,
            "tenant-a",
            group.id,
        )
    ] == [second.id]
    assert (
        repository.current_for_group(
            session,
            "tenant-b",
            group.id,
        )
        == []
    )


def test_calculation_item_decision_upsert_is_tenant_scoped_and_versioned(
    session: Session,
) -> None:
    from app.models.enums import (
        CalculationDecisionType,
        CalculationGroupStatus,
        DemandExecutionMode,
        ReliabilityModelType,
    )
    from app.repositories.calculation_group_repository import (
        CalculationGroupChildRepository,
        CalculationGroupRepository,
        CalculationItemDecisionRepository,
    )

    template = add_template(session, "tenant-a", "GROUP-DECISION")
    version = add_version(
        session,
        "tenant-a",
        template.id,
        "V1",
    )
    calculation = add_calculation(session, "tenant-a", "DECISION")
    spare = add_spare(session, "tenant-a", "DECISION")
    group = CalculationGroupRepository().create(
        session,
        "tenant-a",
        {
            "scenario_version_id": version.id,
            "status": CalculationGroupStatus.COMPLETED,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "recommendation_snapshot_json": {},
            "parameter_snapshot_json": {},
            "created_by_user_id": "user-a",
            "created_by_request_id": "request-a",
        },
    )
    child = CalculationGroupChildRepository().create_attempt(
        session,
        "tenant-a",
        group.id,
        {
            "candidate_key": "WEIBULL:ANALYTICAL",
            "reliability_model": ReliabilityModelType.WEIBULL,
            "execution_mode": DemandExecutionMode.ANALYTICAL,
            "calculation_id": calculation.id,
            "is_primary": True,
        },
    )
    repository = CalculationItemDecisionRepository()
    decision_data = {
        "source_child_id": child.id,
        "selected_child_id": child.id,
        "original_quantity": Decimal("4"),
        "final_quantity": Decimal("4"),
        "decision_type": CalculationDecisionType.SYSTEM_RECOMMENDATION,
        "risk": "LOW",
        "risk_rule_version": "v1",
        "decided_by_user_id": "user-a",
        "decided_by_request_id": "request-a",
    }

    created = repository.upsert(
        session,
        "tenant-a",
        group.id,
        spare.id,
        decision_data,
    )
    updated = repository.upsert(
        session,
        "tenant-a",
        group.id,
        spare.id,
        {
            **decision_data,
            "final_quantity": Decimal("5"),
            "decision_type": CalculationDecisionType.MANUAL_QUANTITY,
        },
    )

    assert updated.id == created.id
    assert updated.version == 2
    assert updated.final_quantity == Decimal("5")
    assert (
        repository.get_for_update(
            session,
            "tenant-b",
            group.id,
            spare.id,
        )
        is None
    )
