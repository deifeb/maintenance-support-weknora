from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module

import pytest
from app.models.enums import (
    CalculationDecisionType,
    DemandExecutionMode,
    ReliabilityModelType,
)
from pydantic import ValidationError


def _schema(name: str):
    module = import_module("app.schemas.demand_list")
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(
            f"demand list schema contract is missing: {name}",
            pytrace=False,
        )
    return value


def test_schema_contract_exports_required_models() -> None:
    required = {
        "DemandListCreateRequest",
        "DemandListItemUpdateRequest",
        "DemandListItemRead",
        "DemandListEventRead",
        "DemandListSummaryRead",
        "DemandListRead",
    }
    module = import_module("app.schemas.demand_list")

    missing = sorted(
        name
        for name in required
        if getattr(module, name, None) is None
    )

    assert not missing, (
        "demand list schema contract is missing: "
        + ", ".join(missing)
    )


def test_create_schema_strips_text_fields() -> None:
    schema = _schema("DemandListCreateRequest")

    request = schema(
        calculation_group_id=7,
        name="  Readiness demand  ",
        description="  Generated draft  ",
    )

    assert request.name == "Readiness demand"
    assert request.description == "Generated draft"


def test_create_schema_rejects_blank_name() -> None:
    schema = _schema("DemandListCreateRequest")

    with pytest.raises(ValidationError):
        schema(
            calculation_group_id=7,
            name="   ",
        )


def test_create_schema_rejects_overlong_name() -> None:
    schema = _schema("DemandListCreateRequest")

    with pytest.raises(ValidationError):
        schema(
            calculation_group_id=7,
            name="x" * 201,
        )


def test_update_schema_rejects_negative_quantity() -> None:
    schema = _schema("DemandListItemUpdateRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            final_quantity=Decimal("-0.000001"),
            adjustment_reason="Operational adjustment",
        )


def test_update_schema_rejects_blank_reason() -> None:
    schema = _schema("DemandListItemUpdateRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            final_quantity=Decimal("1.000000"),
            adjustment_reason="   ",
        )


def test_item_read_schema_has_complete_snapshot_fields() -> None:
    schema = _schema("DemandListItemRead")
    required = {
        "id",
        "demand_list_id",
        "spare_part_id",
        "spare_part_code_snapshot",
        "spare_part_name_snapshot",
        "spare_part_unit_snapshot",
        "criticality_level_snapshot",
        "source_calculation_group_id",
        "source_group_child_id",
        "source_calculation_id",
        "source_calculation_run_id",
        "source_result_id",
        "reliability_model",
        "execution_mode",
        "original_quantity",
        "final_quantity",
        "decision_type",
        "decision_reason",
        "decision_risk",
        "requires_admin_confirmation",
        "confirmed_by_admin",
        "risk_rule_version",
        "source_snapshot_json",
        "decision_snapshot_json",
        "interval_snapshot_json",
        "parameter_snapshot_json",
        "warning_snapshot_json",
        "inventory_snapshot_json",
        "version",
        "created_at",
        "updated_at",
    }

    assert required <= set(schema.model_fields)


def test_item_read_serializes_decimal_strings() -> None:
    schema = _schema("DemandListItemRead")
    timestamp = datetime(2026, 7, 31, 10, 0, tzinfo=UTC)

    item = schema(
        id=11,
        demand_list_id=5,
        spare_part_id=19,
        spare_part_code_snapshot="SP-019",
        spare_part_name_snapshot="Hydraulic pump",
        spare_part_unit_snapshot="piece",
        criticality_level_snapshot="HIGH",
        source_calculation_group_id=3,
        source_group_child_id=4,
        source_calculation_id=8,
        source_calculation_run_id=9,
        source_result_id=10,
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        original_quantity=Decimal("100.000000"),
        final_quantity=Decimal("95.125000"),
        decision_type=CalculationDecisionType.MANUAL_QUANTITY,
        decision_reason="Operational adjustment",
        decision_risk="HIGH",
        requires_admin_confirmation=True,
        confirmed_by_admin=False,
        risk_rule_version="DEMAND-DECISION-RISK-1",
        source_snapshot_json={
            "expected_demand": "88.500000",
        },
        decision_snapshot_json={
            "original_quantity": "100.000000",
            "final_quantity": "95.125000",
        },
        interval_snapshot_json={
            "p50": "80.000000",
            "p99": "120.000000",
        },
        parameter_snapshot_json={
            "shape": "1.800000",
        },
        warning_snapshot_json=["HIGH_VARIANCE"],
        inventory_snapshot_json={
            "usable_inventory": "10.000000",
        },
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
    )

    dumped = item.model_dump(mode="json")

    assert dumped["original_quantity"] == "100.000000"
    assert dumped["final_quantity"] == "95.125000"
    assert (
        dumped["source_snapshot_json"]["expected_demand"]
        == "88.500000"
    )
    assert (
        dumped["decision_snapshot_json"]["final_quantity"]
        == "95.125000"
    )



def _demand_list_service():
    try:
        module = import_module(
            "app.services.demand_list_service"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "demand list service module is missing",
            pytrace=False,
        )
    service_class = getattr(
        module,
        "DemandListService",
        None,
    )
    if service_class is None:
        pytest.fail(
            "demand list service contract is missing: "
            "DemandListService",
            pytrace=False,
        )
    return service_class()


def _completed_group_with_decisions(
    session,
    actor,
    *,
    include_all_decisions: bool = True,
):
    from app.models import (
        CalculationGroup,
        CalculationGroupChild,
        CalculationItemDecision,
        DemandCalculation,
        DemandCalculationRun,
        DemandRunItemResult,
        DemandScenarioTemplate,
        DemandScenarioVersion,
        SparePart,
    )
    from app.models.enums import (
        CalculationDecisionType,
        CalculationExecutionType,
        CalculationGroupStatus,
        CalculationStatus,
        FailureProcessMode,
        ItemCalculationStatus,
        RerunMode,
        ScenarioVersionStatus,
        ShortageRiskLevel,
    )

    now = datetime.now(UTC)
    template = DemandScenarioTemplate(
        tenant_id=actor.tenant_id,
        code=f"DL-{actor.tenant_id}",
        name="Demand list source scenario",
    )
    session.add(template)
    session.flush()

    version = DemandScenarioVersion(
        tenant_id=actor.tenant_id,
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=ScenarioVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.flush()

    calculation = DemandCalculation(
        tenant_id=actor.tenant_id,
        calculation_code=(
            f"DL-CALC-{actor.tenant_id}"
        ),
        calculation_name="Demand list source",
        scenario_version_id=version.id,
        rerun_mode=RerunMode.NEW,
        execution_type=(
            CalculationExecutionType.SYNCHRONOUS
        ),
        requested_mode=DemandExecutionMode.ANALYTICAL,
        status=CalculationStatus.SUCCEEDED,
        progress_percent=Decimal("100"),
        input_snapshot_json={
            "scenario_version_id": version.id,
        },
        input_snapshot_hash="a" * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
        result_schema_version="1.0",
    )
    session.add(calculation)
    session.flush()

    group = CalculationGroup(
        tenant_id=actor.tenant_id,
        scenario_version_id=version.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={
            "primary_candidate_key": (
                "WEIBULL:ANALYTICAL"
            ),
        },
        parameter_snapshot_json={
            "random_seed": 20260723,
        },
        created_by_user_id=actor.user_id,
        created_by_request_id=actor.request_id,
    )
    session.add(group)
    session.flush()

    child = CalculationGroupChild(
        tenant_id=actor.tenant_id,
        group_id=group.id,
        candidate_key="WEIBULL:ANALYTICAL",
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        calculation_id=calculation.id,
        attempt_number=1,
        is_current_attempt=True,
        is_primary=True,
        selection_reason="Primary recommendation",
    )
    session.add(child)
    session.flush()

    run = DemandCalculationRun(
        tenant_id=actor.tenant_id,
        calculation_id=calculation.id,
        run_mode=DemandExecutionMode.ANALYTICAL,
        status=CalculationStatus.SUCCEEDED,
        attempt_number=1,
        is_current_attempt=True,
        progress_percent=Decimal("100"),
        engine_version="task2-red",
        formula_version="task2-red",
        converged=True,
    )
    session.add(run)
    session.flush()

    specifications = (
        (
            "SP-DL-A",
            "Hydraulic pump",
            "HIGH",
            "100.000000",
            ["HIGH_VARIANCE"],
            {"shape": "1.800000"},
        ),
        (
            "SP-DL-B",
            "Seal kit",
            "MEDIUM",
            "55.000000",
            [],
            {"failure_rate": "0.001000"},
        ),
    )
    created = []
    for index, (
        code,
        name,
        criticality,
        quantity,
        warnings,
        parameters,
    ) in enumerate(specifications, start=1):
        spare = SparePart(
            tenant_id=actor.tenant_id,
            code=code,
            name=name,
            unit="piece",
        )
        session.add(spare)
        session.flush()

        recommended = Decimal(quantity)
        result = DemandRunItemResult(
            tenant_id=actor.tenant_id,
            calculation_run_id=run.id,
            spare_part_id=spare.id,
            spare_part_code_snapshot=spare.code,
            spare_part_name_snapshot=spare.name,
            criticality_level=criticality,
            calculation_status=(
                ItemCalculationStatus.CALCULATED
            ),
            selected_model_type=(
                ReliabilityModelType.WEIBULL
            ),
            failure_process_mode=(
                FailureProcessMode.AUTO
            ),
            parameter_snapshot_json=parameters,
            target_service_level=Decimal("0.95"),
            expected_demand=(
                recommended - Decimal("2")
            ),
            variance=Decimal("4"),
            standard_deviation=Decimal("2"),
            p50=recommended - Decimal("10"),
            p80=recommended - Decimal("5"),
            p90=recommended,
            p95=recommended + Decimal("5"),
            p99=recommended + Decimal("10"),
            target_quantile_demand=recommended,
            gross_replacement_demand=recommended,
            repair_pipeline_demand=Decimal("0"),
            repair_pipeline_peak=Decimal("0"),
            net_consumption_demand=recommended,
            recommended_spare_quantity=recommended,
            on_hand_quantity=Decimal("10"),
            available_quantity=Decimal("9"),
            in_transit_quantity=Decimal("3"),
            safety_stock_reserved=Decimal("1"),
            usable_inventory=Decimal("8"),
            net_demand_gap=(
                recommended - Decimal("8")
            ),
            inventory_coverage_rate=Decimal("0.08"),
            shortage_risk_level=ShortageRiskLevel.HIGH,
            minimum_inventory_point=Decimal("5"),
            maximum_simultaneous_gap=Decimal("12"),
            common_shock_demand=Decimal("0"),
            warning_codes_json=warnings,
        )
        session.add(result)
        session.flush()

        if include_all_decisions or index == 1:
            decision = CalculationItemDecision(
                tenant_id=actor.tenant_id,
                group_id=group.id,
                spare_part_id=spare.id,
                source_child_id=child.id,
                selected_child_id=child.id,
                original_quantity=recommended,
                final_quantity=recommended,
                decision_type=(
                    CalculationDecisionType
                    .SYSTEM_RECOMMENDATION
                ),
                reason=None,
                risk="LOW",
                requires_admin_confirmation=False,
                confirmed_by_admin=False,
                risk_rule_version=(
                    "DEMAND-DECISION-RISK-1"
                ),
                decided_by_user_id=actor.user_id,
                decided_by_request_id=actor.request_id,
            )
            session.add(decision)
            session.flush()
        created.append((spare, result))

    session.commit()
    return group, child, run, created


def test_create_from_group_persists_complete_draft_snapshots(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    service = _demand_list_service()
    group, child, run, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )

    original_commit = session.commit
    commit_calls = 0

    def counted_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Readiness demand",
        description="Generated from comparison",
        idempotency_key="demand-list-create-1",
    )

    assert commit_calls == 1
    assert created.status.value == "DRAFT"
    assert created.calculation_group_id == group.id
    assert created.scenario_version_id == (
        group.scenario_version_id
    )
    assert created.version_number == 1
    assert created.is_current is False
    assert len(created.items) == 2
    assert len(created.events) == 1

    first = sorted(
        created.items,
        key=lambda item: item.spare_part_code_snapshot,
    )[0]
    source_spare, source_result = source_rows[0]

    assert first.spare_part_id == source_spare.id
    assert first.source_group_child_id == child.id
    assert first.source_calculation_id == (
        child.calculation_id
    )
    assert first.source_calculation_run_id == run.id
    assert first.source_result_id == source_result.id
    assert first.original_quantity == Decimal(
        "100.000000"
    )
    assert first.final_quantity == Decimal(
        "100.000000"
    )
    assert first.source_snapshot_json[
        "recommended_spare_quantity"
    ] == "100.000000"
    assert first.source_snapshot_json[
        "expected_demand"
    ] == "98.000000"
    assert first.interval_snapshot_json[
        "selected_child_id"
    ] == child.id
    assert first.interval_snapshot_json[
        "candidates"
    ][0]["p50"] == "90.000000"
    assert first.interval_snapshot_json[
        "candidates"
    ][0]["p99"] == "110.000000"
    assert first.parameter_snapshot_json == {
        "shape": "1.800000",
    }
    assert first.warning_snapshot_json == [
        "HIGH_VARIANCE"
    ]
    assert first.inventory_snapshot_json[
        "usable_inventory"
    ] == "8.000000"
    assert first.decision_snapshot_json[
        "risk_rule_version"
    ] == "DEMAND-DECISION-RISK-1"

    event = created.events[0]
    assert event.event_type.value == "CREATED"
    assert event.idempotency_key == (
        "demand-list-create-1"
    )
    assert event.request_hash
    assert event.response_snapshot_json[
        "id"
    ] == created.id

    source_result.recommended_spare_quantity = Decimal(
        "999.000000"
    )
    source_result.parameter_snapshot_json = {
        "shape": "9.900000",
    }
    session.flush()

    assert first.source_snapshot_json[
        "recommended_spare_quantity"
    ] == "100.000000"
    assert first.parameter_snapshot_json == {
        "shape": "1.800000",
    }


def test_create_from_group_rejects_incomplete_decisions(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )
    from app.models import DemandList

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
        include_all_decisions=False,
    )

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Incomplete decisions",
            description=None,
            idempotency_key="demand-list-incomplete",
        )

    assert captured.value.code == (
        "DEMAND_LIST_DECISIONS_INCOMPLETE"
    )
    assert (
        session.query(DemandList).count()
        == 0
    )


def test_create_from_group_replays_same_idempotency_key(
    session,
    actor_contributor,
) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
        DemandListItem,
    )

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Replayable demand",
        "description": "Stable response",
        "idempotency_key": "demand-list-replay",
    }

    first = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    second = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )

    assert second.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )
    assert session.query(DemandList).count() == 1
    assert session.query(DemandListItem).count() == 2
    assert session.query(DemandListEvent).count() == 1


def test_create_from_group_requires_contributor_role(
    session,
    actor_viewer,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service = _demand_list_service()

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.create_from_group(
            session,
            actor_viewer,
            calculation_group_id=1,
            name="Forbidden demand",
            description=None,
            idempotency_key="demand-list-viewer",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )
# Task 2D RED: preconditions, source validation, tenant safety,
# and aggregate atomicity.


def _task2d_add_successful_child_without_results(
    session,
    actor,
    group,
):
    from app.models import (
        CalculationGroupChild,
        DemandCalculation,
    )
    from app.models.enums import (
        CalculationExecutionType,
        CalculationStatus,
        RerunMode,
    )

    now = datetime.now(UTC)
    calculation = DemandCalculation(
        tenant_id=actor.tenant_id,
        calculation_code=(
            f"DL-CALC-EMPTY-{group.id}"
        ),
        calculation_name="Successful child without items",
        scenario_version_id=group.scenario_version_id,
        rerun_mode=RerunMode.NEW,
        execution_type=(
            CalculationExecutionType.SYNCHRONOUS
        ),
        requested_mode=DemandExecutionMode.ANALYTICAL,
        status=CalculationStatus.SUCCEEDED,
        progress_percent=Decimal("100"),
        input_snapshot_json={
            "scenario_version_id": (
                group.scenario_version_id
            ),
        },
        input_snapshot_hash="b" * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
        result_schema_version="1.0",
    )
    session.add(calculation)
    session.flush()

    child = CalculationGroupChild(
        tenant_id=actor.tenant_id,
        group_id=group.id,
        candidate_key="WEIBULL:ANALYTICAL:EMPTY",
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        calculation_id=calculation.id,
        attempt_number=1,
        is_current_attempt=True,
        is_primary=False,
        selection_reason="Task 2D empty-result candidate",
    )
    session.add(child)
    session.flush()
    return child


def _task2d_assert_no_demand_aggregate(session) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
        DemandListItem,
    )

    assert session.query(DemandList).count() == 0
    assert session.query(DemandListItem).count() == 0
    assert session.query(DemandListEvent).count() == 0


def test_task2d_rejects_nonterminal_group(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import CalculationGroupStatus

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    group.status = CalculationGroupStatus.RUNNING
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Nonterminal source",
            description=None,
            idempotency_key="task2d-nonterminal",
        )

    assert captured.value.code == (
        "CALCULATION_GROUP_NOT_TERMINAL"
    )
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_group_without_successful_current_child(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import (
        CalculationGroupStatus,
        CalculationStatus,
    )

    service = _demand_list_service()
    group, child, _, _ = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    group.status = CalculationGroupStatus.FAILED
    child.calculation.status = CalculationStatus.FAILED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="No successful results",
            description=None,
            idempotency_key="task2d-no-results",
        )

    assert captured.value.code == (
        "CALCULATION_GROUP_HAS_NO_RESULTS"
    )
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_missing_decisions_with_sorted_ids(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )
    from app.models import CalculationItemDecision

    service = _demand_list_service()
    group, _, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    first_spare, first_result = source_rows[0]
    second_spare, second_result = source_rows[1]

    first_result.spare_part_code_snapshot = "ZZZ-MISSING"
    second_result.spare_part_code_snapshot = "AAA-MISSING"
    session.query(CalculationItemDecision).filter(
        CalculationItemDecision.group_id == group.id,
    ).delete(synchronize_session=False)
    session.commit()

    expected_ids = sorted(
        [first_spare.id, second_spare.id]
    )

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Missing decisions",
            description=None,
            idempotency_key="task2d-missing-decisions",
        )

    assert captured.value.code == (
        "DEMAND_LIST_DECISIONS_INCOMPLETE"
    )
    assert captured.value.details == {
        "spare_part_ids": expected_ids,
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_selected_child_without_item_result(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )
    from app.models import CalculationItemDecision

    service = _demand_list_service()
    group, _, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    spare, _ = source_rows[0]
    empty_child = (
        _task2d_add_successful_child_without_results(
            session,
            actor_contributor,
            group,
        )
    )
    decision = session.query(
        CalculationItemDecision
    ).filter(
        CalculationItemDecision.tenant_id
        == actor_contributor.tenant_id,
        CalculationItemDecision.group_id == group.id,
        CalculationItemDecision.spare_part_id
        == spare.id,
    ).one()
    decision.selected_child_id = empty_child.id
    session.commit()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Missing selected result",
            description=None,
            idempotency_key="task2d-selected-no-result",
        )

    assert captured.value.code == (
        "DEMAND_LIST_DECISION_SOURCE_INVALID"
    )
    assert captured.value.details == {
        "spare_part_id": spare.id,
        "selected_child_id": empty_child.id,
        "reason": "selected_child_has_no_result",
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_stale_selected_child(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )
    from app.models import CalculationGroupChild

    service = _demand_list_service()
    group, stale_child, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    spare, _ = source_rows[0]
    stale_child.is_current_attempt = False
    replacement = CalculationGroupChild(
        tenant_id=actor_contributor.tenant_id,
        group_id=group.id,
        candidate_key=stale_child.candidate_key,
        reliability_model=(
            stale_child.reliability_model
        ),
        execution_mode=stale_child.execution_mode,
        calculation_id=stale_child.calculation_id,
        attempt_number=2,
        is_current_attempt=True,
        is_primary=True,
        selection_reason="Task 2D current replacement",
    )
    session.add(replacement)
    session.commit()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Stale selected child",
            description=None,
            idempotency_key="task2d-stale-child",
        )

    assert captured.value.code == (
        "DEMAND_LIST_DECISION_SOURCE_INVALID"
    )
    assert captured.value.details == {
        "spare_part_id": spare.id,
        "selected_child_id": stale_child.id,
        "reason": "selected_child_not_current",
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_cross_tenant_group_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.create_from_group(
            session,
            tenant_b,
            calculation_group_id=group.id,
            name="Cross-tenant source",
            description=None,
            idempotency_key="task2d-cross-tenant-group",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "calculation_group",
        "identifier": group.id,
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_cross_tenant_spare_part_source(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()
    group, _, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    spare, _ = source_rows[0]
    spare.tenant_id = "tenant-b"
    session.commit()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Invalid spare source",
            description=None,
            idempotency_key="task2d-invalid-spare",
        )

    assert captured.value.code == (
        "DEMAND_LIST_SOURCE_INVALID"
    )
    assert captured.value.details == {
        "spare_part_id": spare.id,
        "reason": "spare_part_not_found",
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rejects_blank_spare_part_unit(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()
    group, _, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    spare, _ = source_rows[0]
    spare.unit = "   "
    session.commit()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Missing spare unit",
            description=None,
            idempotency_key="task2d-missing-unit",
        )

    assert captured.value.code == (
        "DEMAND_LIST_SOURCE_INVALID"
    )
    assert captured.value.details == {
        "spare_part_id": spare.id,
        "reason": "spare_part_unit_missing",
    }
    _task2d_assert_no_demand_aggregate(session)


def test_task2d_rolls_back_partial_aggregate_write(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )

    original_add_item = service.repository.add_item
    item_calls = 0

    def fail_after_first_item(*args, **kwargs):
        nonlocal item_calls
        item_calls += 1
        if item_calls == 2:
            raise RuntimeError(
                "task2d forced item-write failure"
            )
        return original_add_item(*args, **kwargs)

    monkeypatch.setattr(
        service.repository,
        "add_item",
        fail_after_first_item,
    )

    with pytest.raises(
        RuntimeError,
        match="task2d forced item-write failure",
    ):
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Rollback aggregate",
            description=None,
            idempotency_key="task2d-rollback",
        )

    assert item_calls == 2
    _task2d_assert_no_demand_aggregate(session)
# Task 2E RED: complete idempotent creation contract.


def test_task2e_normalized_equivalent_request_replays(
    session,
    actor_contributor,
) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
    )

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )

    first = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="  Normalized replay  ",
        description="  Stable description  ",
        idempotency_key="task2e-normalized",
    )
    replay = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Normalized replay",
        description="Stable description",
        idempotency_key="task2e-normalized",
    )

    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )
    assert session.query(DemandList).count() == 1
    assert session.query(DemandListEvent).count() == 1


def test_task2e_replay_precedes_source_state_validation(
    session,
    actor_contributor,
) -> None:
    from app.models import CalculationItemDecision
    from app.models.enums import CalculationGroupStatus

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Source-independent replay",
        "description": None,
        "idempotency_key": "task2e-source-replay",
    }

    first = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )

    group.status = CalculationGroupStatus.RUNNING
    session.query(CalculationItemDecision).filter(
        CalculationItemDecision.tenant_id
        == actor_contributor.tenant_id,
        CalculationItemDecision.group_id == group.id,
    ).delete(synchronize_session=False)
    session.commit()

    replay = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )

    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )


def test_task2e_different_tenants_may_reuse_key(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
    )

    service = _demand_list_service()
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )
    group_a, _, _, _ = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    group_b, _, _, _ = (
        _completed_group_with_decisions(
            session,
            tenant_b,
        )
    )

    created_a = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group_a.id,
        name="Tenant A demand",
        description=None,
        idempotency_key="task2e-shared-key",
    )
    created_b = service.create_from_group(
        session,
        tenant_b,
        calculation_group_id=group_b.id,
        name="Tenant B demand",
        description=None,
        idempotency_key="task2e-shared-key",
    )

    persisted_by_id = {
        row.id: row
        for row in session.query(DemandList).all()
    }

    assert persisted_by_id[created_a.id].tenant_id == (
        "tenant-a"
    )
    assert persisted_by_id[created_b.id].tenant_id == (
        "tenant-b"
    )
    assert created_a.id != created_b.id
    assert session.query(DemandList).count() == 2
    assert session.query(DemandListEvent).count() == 2


def test_task2e_same_key_different_request_has_conflict_details(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import (
        DemandList,
        DemandListEvent,
    )

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )

    service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Original request",
        description=None,
        idempotency_key="task2e-conflict",
    )

    with pytest.raises(ConflictError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Changed request",
            description=None,
            idempotency_key="task2e-conflict",
        )

    assert captured.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }
    assert session.query(DemandList).count() == 1
    assert session.query(DemandListEvent).count() == 1


def test_task2e_blank_key_is_required(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=1,
            name="Missing key",
            description=None,
            idempotency_key="   ",
        )

    assert captured.value.code == (
        "IDEMPOTENCY_KEY_REQUIRED"
    )
    _task2d_assert_no_demand_aggregate(session)


def test_task2e_non_created_receipt_is_rejected(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import (
        DemandList,
        DemandListEvent,
    )
    from app.models.enums import DemandListEventType

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Receipt event type",
        "description": None,
        "idempotency_key": "task2e-event-type",
    }

    service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    receipt = session.query(DemandListEvent).one()
    receipt.event_type = DemandListEventType.ITEM_UPDATED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            **arguments,
        )

    assert captured.value.code == (
        "IDEMPOTENT_RESPONSE_UNAVAILABLE"
    )
    assert session.query(DemandList).count() == 1
    assert session.query(DemandListEvent).count() == 1


def test_task2e_malformed_response_snapshot_is_rejected(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import (
        DemandList,
        DemandListEvent,
    )

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Malformed receipt",
        "description": None,
        "idempotency_key": "task2e-malformed",
    }

    created = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    receipt = session.query(DemandListEvent).one()
    receipt.response_snapshot_json = {
        "id": created.id,
    }
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            **arguments,
        )

    assert captured.value.code == (
        "IDEMPOTENT_RESPONSE_UNAVAILABLE"
    )
    assert session.query(DemandList).count() == 1
    assert session.query(DemandListEvent).count() == 1


def test_task2e_valid_receipt_returns_exact_stored_snapshot(
    session,
    actor_contributor,
) -> None:
    from app.models import DemandListEvent

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Stored snapshot",
        "description": "Exact replay",
        "idempotency_key": "task2e-exact-snapshot",
    }

    created = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    receipt = session.query(DemandListEvent).one()
    expected = receipt.response_snapshot_json

    replay = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )

    assert expected is not None
    assert replay.model_dump(mode="json") == expected
    assert replay.model_dump(mode="json") == (
        created.model_dump(mode="json")
    )
# Task 2F RED: tenant-safe get/list, deterministic reads,
# filters, and exact pagination.


def _task2f_add_summary_row(
    session,
    actor,
    source,
    *,
    name: str,
    lineage_id: str,
    status,
    created_at,
    version_number: int = 1,
):
    from app.models import DemandList

    row = DemandList(
        tenant_id=actor.tenant_id,
        name=name,
        description=f"{name} description",
        lineage_id=lineage_id,
        version_number=version_number,
        scenario_version_id=source.scenario_version_id,
        calculation_group_id=(
            source.calculation_group_id
        ),
        status=status,
        is_current=(
            status.value == "PUBLISHED"
        ),
        created_by_user_id=actor.user_id,
        created_by_request_id=actor.request_id,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(row)
    session.flush()
    return row


def test_task2f_viewer_contributor_admin_can_get(
    session,
    actor_contributor,
    actor_viewer,
    actor_admin,
) -> None:
    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Readable demand list",
        description=None,
        idempotency_key="task2f-readable",
    )

    for actor in (
        actor_viewer,
        actor_contributor,
        actor_admin,
    ):
        loaded = service.get(
            session,
            actor,
            created.id,
        )
        assert loaded.id == created.id
        assert loaded.name == "Readable demand list"


def test_task2f_foreign_tenant_get_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Tenant A list",
        description=None,
        idempotency_key="task2f-foreign-get",
    )
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.get(
            session,
            tenant_b,
            created.id,
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": created.id,
    }


def test_task2f_list_excludes_other_tenants(
    session,
    actor_contributor,
    actor_context,
) -> None:
    service = _demand_list_service()
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )
    group_a, _, _, _ = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    group_b, _, _, _ = (
        _completed_group_with_decisions(
            session,
            tenant_b,
        )
    )

    created_a = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group_a.id,
        name="Tenant A only",
        description=None,
        idempotency_key="task2f-tenant-a",
    )
    created_b = service.create_from_group(
        session,
        tenant_b,
        calculation_group_id=group_b.id,
        name="Tenant B only",
        description=None,
        idempotency_key="task2f-tenant-b",
    )

    page = service.list(
        session,
        tenant_b,
        page=1,
        page_size=20,
    )

    assert page.total == 1
    assert [item.id for item in page.items] == [
        created_b.id
    ]
    assert created_a.id not in {
        item.id for item in page.items
    }


def test_task2f_status_and_lineage_filters_work(
    session,
    actor_contributor,
) -> None:
    from datetime import timedelta

    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Filter base",
        description=None,
        idempotency_key="task2f-filter-base",
    )
    source = session.get(DemandList, created.id)
    assert source is not None

    target_lineage = "task2f-target-lineage"
    _task2f_add_summary_row(
        session,
        actor_contributor,
        source,
        name="Published target",
        lineage_id=target_lineage,
        status=DemandListStatus.PUBLISHED,
        created_at=source.created_at
        + timedelta(seconds=1),
    )
    _task2f_add_summary_row(
        session,
        actor_contributor,
        source,
        name="Draft target",
        lineage_id=target_lineage,
        status=DemandListStatus.DRAFT,
        created_at=source.created_at
        + timedelta(seconds=2),
        version_number=2,
    )
    _task2f_add_summary_row(
        session,
        actor_contributor,
        source,
        name="Published other",
        lineage_id="task2f-other-lineage",
        status=DemandListStatus.PUBLISHED,
        created_at=source.created_at
        + timedelta(seconds=3),
    )
    session.commit()

    filtered = service.list(
        session,
        actor_contributor,
        page=1,
        page_size=20,
        status=DemandListStatus.PUBLISHED,
        lineage_id=target_lineage,
    )

    assert filtered.total == 1
    assert [item.name for item in filtered.items] == [
        "Published target"
    ]


def test_task2f_get_sorts_and_copies_nested_json(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from datetime import timedelta

    from app.models import (
        DemandListEvent,
    )
    from app.models.enums import DemandListEventType

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Deterministic read",
        description=None,
        idempotency_key="task2f-sort-copy",
    )
    row = service.repository.get(
        session,
        actor_contributor.tenant_id,
        created.id,
    )
    assert row is not None
    base_time = row.events[0].occurred_at

    event_later_id_earlier_time = DemandListEvent(
        tenant_id=actor_contributor.tenant_id,
        demand_list_id=row.id,
        event_type=DemandListEventType.ITEM_UPDATED,
        actor_user_id=actor_contributor.user_id,
        actor_roles_json=["contributor"],
        request_id="task2f-event-early",
        before_summary_json={"quantity": "1.000000"},
        after_summary_json={"quantity": "2.000000"},
        occurred_at=base_time - timedelta(seconds=2),
    )
    event_latest_time = DemandListEvent(
        tenant_id=actor_contributor.tenant_id,
        demand_list_id=row.id,
        event_type=DemandListEventType.ITEM_UPDATED,
        actor_user_id=actor_contributor.user_id,
        actor_roles_json=["contributor"],
        request_id="task2f-event-late",
        before_summary_json={"quantity": "2.000000"},
        after_summary_json={"quantity": "3.000000"},
        occurred_at=base_time + timedelta(seconds=2),
    )
    session.add_all(
        [
            event_later_id_earlier_time,
            event_latest_time,
        ]
    )
    session.commit()

    row = service.repository.get(
        session,
        actor_contributor.tenant_id,
        created.id,
    )
    assert row is not None
    row.items[:] = list(reversed(row.items))
    row.events[:] = list(reversed(row.events))

    expected_item_ids = sorted(
        item.id for item in row.items
    )
    expected_event_ids = [
        event.id
        for event in sorted(
            row.events,
            key=lambda event: (
                event.occurred_at,
                event.id,
            ),
        )
    ]
    persisted_source = dict(
        row.items[0].source_snapshot_json
    )
    persisted_roles = list(
        row.events[0].actor_roles_json
    )

    monkeypatch.setattr(
        service.repository,
        "get",
        lambda *_args, **_kwargs: row,
    )

    loaded = service.get(
        session,
        actor_contributor,
        created.id,
    )

    assert [item.id for item in loaded.items] == (
        expected_item_ids
    )
    assert [event.id for event in loaded.events] == (
        expected_event_ids
    )

    loaded.items[0].source_snapshot_json[
        "task2f_mutation"
    ] = True
    loaded.events[0].actor_roles_json.append(
        "task2f_mutation"
    )

    assert (
        row.items[0].source_snapshot_json
        == persisted_source
    )
    assert row.events[0].actor_roles_json == (
        persisted_roles
    )


def test_task2f_page_metadata_is_exact(
    session,
    actor_contributor,
) -> None:
    from datetime import timedelta

    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Page row 0",
        description=None,
        idempotency_key="task2f-page-base",
    )
    source = session.get(DemandList, created.id)
    assert source is not None

    for index in range(1, 5):
        _task2f_add_summary_row(
            session,
            actor_contributor,
            source,
            name=f"Page row {index}",
            lineage_id=f"task2f-page-{index}",
            status=DemandListStatus.DRAFT,
            created_at=source.created_at
            + timedelta(seconds=index),
        )
    session.commit()

    page = service.list(
        session,
        actor_contributor,
        page=2,
        page_size=2,
    )

    assert page.page == 2
    assert page.page_size == 2
    assert page.total == 5
    assert page.pages == 3
    assert len(page.items) == 2
# Task 2G RED: optimistic DRAFT item updates.


def _task2g_create_draft(
    session,
    actor,
    *,
    key: str,
    name: str = "Task 2G draft",
):
    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor,
    )
    created = service.create_from_group(
        session,
        actor,
        calculation_group_id=group.id,
        name=name,
        description=None,
        idempotency_key=key,
    )
    return service, created


def test_task2g_update_changes_quantity_versions_and_commits_once(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.models import DemandListItem

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-success",
    )
    target = created.items[0]
    persisted = session.get(DemandListItem, target.id)
    assert persisted is not None
    persisted.confirmed_by_admin = True
    session.commit()

    original_commit = session.commit
    commit_calls = 0

    def counted_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="  Approved adjustment  ",
    )

    updated_item = next(
        item
        for item in updated.items
        if item.id == target.id
    )
    assert commit_calls == 1
    assert updated.version == created.version + 1
    assert updated_item.version == target.version + 1
    assert updated_item.final_quantity == Decimal(
        "90.000000"
    )
    assert updated_item.decision_reason == (
        "Approved adjustment"
    )
    assert updated_item.confirmed_by_admin is False
    assert updated.events[-1].event_type.value == (
        "ITEM_UPDATED"
    )


def test_task2g_update_matches_shared_risk_policy(
    session,
    actor_contributor,
) -> None:
    from app.services.demand_decision_policy import (
        DecisionCandidateEvidence,
        evaluate_decision_risk,
    )

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-risk-parity",
    )
    target = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )
    interval = target.interval_snapshot_json
    assert interval is not None

    candidates = tuple(
        DecisionCandidateEvidence(
            child_id=int(candidate["child_id"]),
            recommended_quantity=Decimal(
                candidate["recommended_quantity"]
            ),
            p50=(
                Decimal(candidate["p50"])
                if candidate.get("p50") is not None
                else None
            ),
            p99=(
                Decimal(candidate["p99"])
                if candidate.get("p99") is not None
                else None
            ),
            warnings=tuple(
                candidate.get("warnings") or ()
            ),
        )
        for candidate in interval["candidates"]
    )
    final_quantity = Decimal("90.000000")
    expected = evaluate_decision_risk(
        source_child_id=int(
            target.source_group_child_id
        ),
        selected_child_id=int(
            interval["selected_child_id"]
        ),
        source_quantity=target.original_quantity,
        selected_quantity=Decimal(
            target.source_snapshot_json[
                "recommended_spare_quantity"
            ]
        ),
        final_quantity=final_quantity,
        criticality_level=(
            target.criticality_level_snapshot
        ),
        successful_candidates=candidates,
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=final_quantity,
        adjustment_reason="Risk parity check",
    )
    updated_item = next(
        item
        for item in updated.items
        if item.id == target.id
    )

    assert updated_item.decision_type == (
        expected.decision_type
    )
    assert updated_item.decision_risk == expected.risk
    assert (
        updated_item.requires_admin_confirmation
        is expected.requires_admin_confirmation
    )
    assert updated_item.risk_rule_version == (
        expected.rule_version
    )


def test_task2g_event_uses_decimal_strings_and_preserves_origin(
    session,
    actor_contributor,
) -> None:
    from copy import deepcopy

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-event",
    )
    target = created.items[0]
    original_decision_snapshot = deepcopy(
        target.decision_snapshot_json
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("91.250000"),
        adjustment_reason="Event evidence",
    )

    updated_item = next(
        item
        for item in updated.items
        if item.id == target.id
    )
    event = updated.events[-1]

    assert event.event_type.value == "ITEM_UPDATED"
    assert event.actor_user_id == actor_contributor.user_id
    assert event.request_id == actor_contributor.request_id
    assert event.before_summary_json == {
        "item_id": target.id,
        "final_quantity": format(
            target.final_quantity,
            "f",
        ),
        "version": target.version,
    }
    assert event.after_summary_json == {
        "item_id": target.id,
        "final_quantity": "91.250000",
        "version": target.version + 1,
    }
    assert updated_item.decision_snapshot_json == (
        original_decision_snapshot
    )


def test_task2g_stale_list_version_has_contract_details(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-stale",
    )
    target = created.items[0]
    stale_version = created.version + 1

    with pytest.raises(ConflictError) as captured:
        service.update_item(
            session,
            actor_contributor,
            created.id,
            target.id,
            expected_version=stale_version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Stale write",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale_version,
        "actual_version": created.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task2g_non_draft_list_is_not_editable(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-not-editable",
    )
    target = created.items[0]
    persisted = session.get(DemandList, created.id)
    assert persisted is not None
    persisted.status = (
        DemandListStatus.PENDING_CONFIRMATION
    )
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.update_item(
            session,
            actor_contributor,
            created.id,
            target.id,
            expected_version=created.version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Forbidden state",
        )

    assert captured.value.code == (
        "DEMAND_LIST_NOT_EDITABLE"
    )


def test_task2g_foreign_list_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-foreign-list",
    )
    target = created.items[0]
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.update_item(
            session,
            tenant_b,
            created.id,
            target.id,
            expected_version=created.version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Cross tenant",
        )

    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": created.id,
    }


def test_task2g_foreign_item_is_not_found(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import NotFoundError
    from app.models import DemandListItem

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-foreign-item",
    )
    target = created.items[0]
    persisted = session.get(DemandListItem, target.id)
    assert persisted is not None
    persisted.tenant_id = "tenant-b"
    session.commit()

    with pytest.raises(NotFoundError) as captured:
        service.update_item(
            session,
            actor_contributor,
            created.id,
            target.id,
            expected_version=created.version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Foreign item",
        )

    assert captured.value.details == {
        "resource": "demand_list_item",
        "identifier": target.id,
    }


def test_task2g_item_from_another_list_is_not_found(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import NotFoundError

    service, first = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-list-one",
        name="Task 2G list one",
    )
    group_id = first.calculation_group_id
    second = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group_id,
        name="Task 2G list two",
        description=None,
        idempotency_key="task2g-list-two",
    )
    foreign_item = second.items[0]

    with pytest.raises(NotFoundError) as captured:
        service.update_item(
            session,
            actor_contributor,
            first.id,
            foreign_item.id,
            expected_version=first.version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Wrong aggregate",
        )

    assert captured.value.details == {
        "resource": "demand_list_item",
        "identifier": foreign_item.id,
    }


def test_task2g_viewer_cannot_update(
    session,
    actor_contributor,
    actor_viewer,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2g-viewer",
    )
    target = created.items[0]

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.update_item(
            session,
            actor_viewer,
            created.id,
            target.id,
            expected_version=created.version,
            final_quantity=Decimal("95.000000"),
            adjustment_reason="Viewer write",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task2g_negative_direct_quantity_is_rejected(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.update_item(
            session,
            actor_contributor,
            999,
            999,
            expected_version=1,
            final_quantity=Decimal("-0.000001"),
            adjustment_reason="Invalid quantity",
        )

    assert captured.value.code == (
        "DEMAND_LIST_QUANTITY_INVALID"
    )


def test_task2g_blank_direct_reason_is_rejected(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.update_item(
            session,
            actor_contributor,
            999,
            999,
            expected_version=1,
            final_quantity=Decimal("1.000000"),
            adjustment_reason="   ",
        )

    assert captured.value.code == (
        "DEMAND_LIST_ADJUSTMENT_REASON_REQUIRED"
    )
# Task 2H review remediation RED:
# close the final-review Critical and Important findings.


def _task2h_add_alternative_selected_decision(
    session,
    actor,
    group,
    primary_child,
    source_rows,
):
    from app.models import (
        CalculationGroupChild,
        CalculationItemDecision,
        DemandCalculation,
        DemandCalculationRun,
        DemandRunItemResult,
    )
    from app.models.enums import (
        CalculationDecisionType,
        CalculationExecutionType,
        CalculationStatus,
        FailureProcessMode,
        ItemCalculationStatus,
        RerunMode,
        ShortageRiskLevel,
    )
    from sqlalchemy import select

    source_spare, primary_result = source_rows[0]
    now = datetime.now(UTC)

    alternative_calculation = DemandCalculation(
        tenant_id=actor.tenant_id,
        calculation_code=(
            f"DL-ALT-{actor.tenant_id}-{group.id}"
        ),
        calculation_name="Alternative demand source",
        scenario_version_id=group.scenario_version_id,
        rerun_mode=RerunMode.NEW,
        execution_type=(
            CalculationExecutionType.SYNCHRONOUS
        ),
        requested_mode=DemandExecutionMode.ANALYTICAL,
        status=CalculationStatus.SUCCEEDED,
        progress_percent=Decimal("100"),
        input_snapshot_json={
            "scenario_version_id": (
                group.scenario_version_id
            ),
            "candidate_key": (
                "BINOMIAL:ANALYTICAL"
            ),
        },
        input_snapshot_hash="b" * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
        result_schema_version="1.0",
    )
    session.add(alternative_calculation)
    session.flush()

    alternative_child = CalculationGroupChild(
        tenant_id=actor.tenant_id,
        group_id=group.id,
        candidate_key="BINOMIAL:ANALYTICAL",
        reliability_model=(
            ReliabilityModelType.BINOMIAL
        ),
        execution_mode=DemandExecutionMode.ANALYTICAL,
        calculation_id=alternative_calculation.id,
        attempt_number=1,
        is_current_attempt=True,
        is_primary=False,
        selection_reason="Alternative candidate",
    )
    session.add(alternative_child)
    session.flush()

    alternative_run = DemandCalculationRun(
        tenant_id=actor.tenant_id,
        calculation_id=alternative_calculation.id,
        run_mode=DemandExecutionMode.ANALYTICAL,
        status=CalculationStatus.SUCCEEDED,
        attempt_number=1,
        is_current_attempt=True,
        progress_percent=Decimal("100"),
        engine_version="task2h-review",
        formula_version="task2h-review",
        converged=True,
    )
    session.add(alternative_run)
    session.flush()

    selected_quantity = Decimal("120.000000")
    alternative_result = DemandRunItemResult(
        tenant_id=actor.tenant_id,
        calculation_run_id=alternative_run.id,
        spare_part_id=source_spare.id,
        spare_part_code_snapshot=source_spare.code,
        spare_part_name_snapshot=source_spare.name,
        criticality_level="MEDIUM",
        calculation_status=(
            ItemCalculationStatus.CALCULATED
        ),
        selected_model_type=(
            ReliabilityModelType.BINOMIAL
        ),
        failure_process_mode=FailureProcessMode.AUTO,
        parameter_snapshot_json={
            "trials": "10.000000",
        },
        target_service_level=Decimal("0.95"),
        expected_demand=selected_quantity,
        variance=Decimal("4"),
        standard_deviation=Decimal("2"),
        p50=Decimal("110.000000"),
        p80=Decimal("115.000000"),
        p90=selected_quantity,
        p95=Decimal("125.000000"),
        p99=Decimal("130.000000"),
        target_quantile_demand=selected_quantity,
        gross_replacement_demand=selected_quantity,
        repair_pipeline_demand=Decimal("0"),
        repair_pipeline_peak=Decimal("0"),
        net_consumption_demand=selected_quantity,
        recommended_spare_quantity=selected_quantity,
        on_hand_quantity=Decimal("10"),
        available_quantity=Decimal("9"),
        in_transit_quantity=Decimal("3"),
        safety_stock_reserved=Decimal("1"),
        usable_inventory=Decimal("8"),
        net_demand_gap=Decimal("112"),
        inventory_coverage_rate=Decimal("0.08"),
        shortage_risk_level=ShortageRiskLevel.HIGH,
        minimum_inventory_point=Decimal("5"),
        maximum_simultaneous_gap=Decimal("12"),
        common_shock_demand=Decimal("0"),
        warning_codes_json=[],
    )
    session.add(alternative_result)
    session.flush()

    decision = session.scalar(
        select(CalculationItemDecision).where(
            CalculationItemDecision.tenant_id
            == actor.tenant_id,
            CalculationItemDecision.group_id
            == group.id,
            CalculationItemDecision.spare_part_id
            == source_spare.id,
        )
    )
    assert decision is not None
    assert decision.source_child_id == primary_child.id
    assert (
        primary_result.recommended_spare_quantity
        == Decimal("100.000000")
    )

    decision.selected_child_id = alternative_child.id
    decision.final_quantity = selected_quantity
    decision.decision_type = (
        CalculationDecisionType.ALTERNATIVE_CANDIDATE
    )
    decision.reason = "Accepted alternative candidate"
    decision.risk = "HIGH"
    decision.requires_admin_confirmation = True
    decision.confirmed_by_admin = False
    session.commit()

    return (
        source_spare,
        decision,
        alternative_child,
        alternative_result,
    )


def test_task2h_review_alternative_candidate_risk_is_preserved(
    session,
    actor_contributor,
) -> None:
    service = _demand_list_service()
    group, primary_child, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    (
        source_spare,
        _,
        alternative_child,
        alternative_result,
    ) = _task2h_add_alternative_selected_decision(
        session,
        actor_contributor,
        group,
        primary_child,
        source_rows,
    )

    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Alternative candidate review",
        description=None,
        idempotency_key=(
            "task2h-review-alternative"
        ),
    )
    target = next(
        item
        for item in created.items
        if item.spare_part_id == source_spare.id
    )
    assert target.source_group_child_id == (
        alternative_child.id
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=(
            alternative_result
            .recommended_spare_quantity
        ),
        adjustment_reason=(
            "Keep selected alternative quantity"
        ),
    )
    updated_item = next(
        item
        for item in updated.items
        if item.id == target.id
    )

    assert updated_item.decision_type == (
        CalculationDecisionType.ALTERNATIVE_CANDIDATE
    )
    assert updated_item.decision_risk == "HIGH"
    assert (
        updated_item.requires_admin_confirmation
        is True
    )


def test_task2h_review_snapshots_include_plan_fields(
    session,
    actor_contributor,
) -> None:
    from app.models import CalculationItemDecision
    from sqlalchemy import select

    service = _demand_list_service()
    group, child, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    source_spare, _ = source_rows[0]
    decision = session.scalar(
        select(CalculationItemDecision).where(
            CalculationItemDecision.tenant_id
            == actor_contributor.tenant_id,
            CalculationItemDecision.group_id
            == group.id,
            CalculationItemDecision.spare_part_id
            == source_spare.id,
        )
    )
    assert decision is not None

    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Complete snapshot review",
        description=None,
        idempotency_key=(
            "task2h-review-snapshot"
        ),
    )
    item = next(
        row
        for row in created.items
        if row.spare_part_id == source_spare.id
    )
    interval = item.interval_snapshot_json
    decision_snapshot = item.decision_snapshot_json
    assert interval is not None
    assert decision_snapshot is not None

    assert interval[
        "system_source_child_id"
    ] == child.id
    assert interval["selected_child_id"] == child.id
    assert interval["selected_p50"] == "90.000000"
    assert interval["selected_p80"] == "95.000000"
    assert interval["selected_p90"] == "100.000000"
    assert interval["selected_p95"] == "105.000000"
    assert interval["selected_p99"] == "110.000000"

    assert decision_snapshot["created_at"] == (
        decision.created_at.isoformat()
    )
    assert decision_snapshot["updated_at"] == (
        decision.updated_at.isoformat()
    )


def test_task2h_review_nested_numeric_snapshots_are_strings(
    session,
    actor_contributor,
) -> None:
    service = _demand_list_service()
    group, _, _, source_rows = (
        _completed_group_with_decisions(
            session,
            actor_contributor,
        )
    )
    source_spare, source_result = source_rows[0]
    source_result.parameter_snapshot_json = {
        "nested": {
            "shape": 1.8,
            "series": [
                0.1,
                {
                    "rate": 2.5,
                },
            ],
        },
    }
    source_result.selection_reason_json = {
        "weights": [
            0.25,
            {
                "score": 1.5,
            },
        ],
    }
    session.commit()

    created = service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group.id,
        name="Numeric snapshot review",
        description=None,
        idempotency_key=(
            "task2h-review-numeric"
        ),
    )
    item = next(
        row
        for row in created.items
        if row.spare_part_id == source_spare.id
    )

    assert item.parameter_snapshot_json == {
        "nested": {
            "shape": "1.800000",
            "series": [
                "0.100000",
                {
                    "rate": "2.500000",
                },
            ],
        },
    }
    assert item.source_snapshot_json[
        "selection_reason_json"
    ] == {
        "weights": [
            "0.250000",
            {
                "score": "1.500000",
            },
        ],
    }


def test_task2h_review_read_model_deep_copies_nested_json(
    session,
    actor_contributor,
) -> None:
    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="task2h-review-deep-copy",
    )
    persisted = service.repository.get(
        session,
        actor_contributor.tenant_id,
        created.id,
    )
    assert persisted is not None

    loaded = service.get(
        session,
        actor_contributor,
        created.id,
    )
    loaded_item = loaded.items[0]
    persisted_item = next(
        item
        for item in persisted.items
        if item.id == loaded_item.id
    )
    assert loaded_item.interval_snapshot_json is not None
    assert (
        persisted_item.interval_snapshot_json
        is not None
    )

    loaded_item.interval_snapshot_json[
        "candidates"
    ][0]["warnings"].append(
        "TASK2H-MUTATION"
    )

    assert "TASK2H-MUTATION" not in (
        persisted_item.interval_snapshot_json[
            "candidates"
        ][0]["warnings"]
    )


def test_task2h_review_constructor_accepts_dependencies() -> None:
    module = import_module(
        "app.services.demand_list_service"
    )
    service_class = module.DemandListService

    repository = object()
    item_repository = object()
    calculation_group_service = object()

    service = service_class(
        repository=repository,
        item_repository=item_repository,
        calculation_group_service=(
            calculation_group_service
        ),
    )

    assert service.repository is repository
    assert service.item_repository is item_repository
    assert (
        service.calculation_group_service
        is calculation_group_service
    )
# Task 2J final idempotency remediation RED.


def _task2j_install_receipt_race(
    service,
    monkeypatch,
    receipt,
    *,
    race_key: str,
):
    from copy import deepcopy
    from types import SimpleNamespace

    from sqlalchemy.exc import IntegrityError

    assert receipt.response_snapshot_json is not None
    response_snapshot = deepcopy(
        receipt.response_snapshot_json
    )
    for event in response_snapshot["events"]:
        if event["event_type"] == "CREATED":
            event["idempotency_key"] = race_key

    raced_receipt = SimpleNamespace(
        event_type=receipt.event_type,
        idempotency_key=race_key,
        request_hash=receipt.request_hash,
        response_snapshot_json=response_snapshot,
    )
    state = {"lookups": 0}

    def lookup_receipt(
        session_arg,
        tenant_id,
        idempotency_key,
    ):
        del session_arg, tenant_id
        assert idempotency_key == race_key
        state["lookups"] += 1
        if state["lookups"] == 1:
            return None
        return raced_receipt

    def duplicate_receipt(*args, **kwargs):
        del args, kwargs
        raise IntegrityError(
            "INSERT INTO demand_list_events",
            {"idempotency_key": race_key},
            Exception("duplicate idempotency receipt"),
        )

    monkeypatch.setattr(
        service.repository,
        "get_event_by_idempotency_key",
        lookup_receipt,
    )
    monkeypatch.setattr(
        service.repository,
        "append_event",
        duplicate_receipt,
    )
    return raced_receipt, state


def test_task2j_idempotent_replay_deep_copies_receipt_json(
    session,
    actor_contributor,
) -> None:
    from app.models import DemandListEvent

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    arguments = {
        "calculation_group_id": group.id,
        "name": "Replay isolation",
        "description": "Nested receipt JSON",
        "idempotency_key": "task2j-replay-isolation",
    }

    service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    receipt = session.query(DemandListEvent).one()
    assert receipt.response_snapshot_json is not None

    replay = service.create_from_group(
        session,
        actor_contributor,
        **arguments,
    )
    replay_interval = (
        replay.items[0].interval_snapshot_json
    )
    assert replay_interval is not None

    replay_interval["candidates"][0][
        "warnings"
    ].append("TASK2J-REPLAY-MUTATION")

    stored_warnings = (
        receipt.response_snapshot_json["items"][0]
        ["interval_snapshot_json"]["candidates"][0]
        ["warnings"]
    )
    assert "TASK2J-REPLAY-MUTATION" not in stored_warnings


def test_task2j_same_hash_unique_conflict_replays_winner(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.models import DemandList, DemandListEvent

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    group_id = group.id
    base_arguments = {
        "calculation_group_id": group_id,
        "name": "Concurrent idempotency",
        "description": "Same request hash",
    }

    winner = service.create_from_group(
        session,
        actor_contributor,
        **base_arguments,
        idempotency_key="task2j-winner-same",
    )
    receipt = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.idempotency_key
            == "task2j-winner-same"
        )
        .one()
    )
    raced_receipt, state = (
        _task2j_install_receipt_race(
            service,
            monkeypatch,
            receipt,
            race_key="task2j-race-same",
        )
    )

    replay = service.create_from_group(
        session,
        actor_contributor,
        **base_arguments,
        idempotency_key="task2j-race-same",
    )

    assert state["lookups"] == 2
    assert replay.model_dump(mode="json") == (
        raced_receipt.response_snapshot_json
    )
    assert replay.id == winner.id
    assert session.query(DemandList).count() == 1


def test_task2j_different_hash_unique_conflict_is_controlled(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandList, DemandListEvent

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    group_id = group.id

    service.create_from_group(
        session,
        actor_contributor,
        calculation_group_id=group_id,
        name="Concurrent winner",
        description="Original request",
        idempotency_key="task2j-winner-different",
    )
    receipt = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.idempotency_key
            == "task2j-winner-different"
        )
        .one()
    )
    _, state = _task2j_install_receipt_race(
        service,
        monkeypatch,
        receipt,
        race_key="task2j-race-different",
    )

    with pytest.raises(ConflictError) as exc:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group_id,
            name="Concurrent different request",
            description="Different request hash",
            idempotency_key=(
                "task2j-race-different"
            ),
        )

    assert state["lookups"] == 2
    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert exc.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }
    assert session.query(DemandList).count() == 1
