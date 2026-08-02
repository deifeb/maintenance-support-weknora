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
        "DemandListTransitionRequest",
        "DemandListConfirmRequest",
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


def test_task3a_transition_schema_requires_positive_version() -> None:
    schema = _schema("DemandListTransitionRequest")

    with pytest.raises(ValidationError):
        schema(expected_version=0)


def test_task3a_transition_schema_rejects_extra_fields() -> None:
    schema = _schema("DemandListTransitionRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            tenant_id="forbidden",
        )


def test_task3a_confirm_schema_strips_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    request = schema(
        expected_version=2,
        confirmation_note="  Reviewed by maintenance admin  ",
    )

    assert request.confirmation_note == (
        "Reviewed by maintenance admin"
    )


def test_task3a_confirm_schema_rejects_blank_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="   ",
        )


def test_task3a_confirm_schema_rejects_overlong_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="x" * 1001,
        )


def test_task3a_confirm_schema_rejects_extra_fields() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="Approved",
            actor_user_id="forbidden",
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


def test_closure_rejects_empty_comparison_before_aggregate_write(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.core.exceptions import BusinessValidationError

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    comparison = service.calculation_group_service.comparison(
        session,
        actor_contributor,
        group.id,
    )
    empty_comparison = comparison.model_copy(
        update={"rows": []},
    )
    monkeypatch.setattr(
        service.calculation_group_service,
        "comparison",
        lambda *_args, **_kwargs: empty_comparison,
    )

    with pytest.raises(BusinessValidationError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Empty comparison must fail",
            description=None,
            idempotency_key="closure-empty-comparison",
        )

    assert captured.value.code == "DEMAND_LIST_EMPTY"
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
    expected_summary_keys = {
        "item_id",
        "original_quantity",
        "final_quantity",
        "decision_reason",
        "decision_type",
        "decision_risk",
        "requires_admin_confirmation",
        "confirmed_by_admin",
        "risk_rule_version",
        "version",
    }
    assert set(event.before_summary_json) == (
        expected_summary_keys
    )
    assert set(event.after_summary_json) == (
        expected_summary_keys
    )
    assert event.before_summary_json[
        "final_quantity"
    ] == format(target.final_quantity, "f")
    assert event.before_summary_json["version"] == (
        target.version
    )
    assert event.after_summary_json[
        "final_quantity"
    ] == "91.250000"
    assert event.after_summary_json[
        "decision_reason"
    ] == "Event evidence"
    assert event.after_summary_json["version"] == (
        target.version + 1
    )
    assert updated_item.decision_snapshot_json == (
        original_decision_snapshot
    )


def test_closure_item_update_preserves_complete_decision_history(
    session,
    actor_contributor,
) -> None:
    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="closure-item-audit",
    )
    target = created.items[0]
    expected_keys = {
        "item_id",
        "original_quantity",
        "final_quantity",
        "decision_reason",
        "decision_type",
        "decision_risk",
        "requires_admin_confirmation",
        "confirmed_by_admin",
        "risk_rule_version",
        "version",
    }

    first = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("9"),
        adjustment_reason="First reviewed adjustment",
    )
    first_item = next(
        item for item in first.items if item.id == target.id
    )
    second = service.update_item(
        session,
        actor_contributor,
        first.id,
        target.id,
        expected_version=first.version,
        final_quantity=Decimal("7"),
        adjustment_reason="Second reviewed adjustment",
    )
    events = [
        event
        for event in second.events
        if event.event_type.value == "ITEM_UPDATED"
    ]

    assert len(events) == 2
    assert set(events[0].before_summary_json) == expected_keys
    assert set(events[0].after_summary_json) == expected_keys
    assert events[0].after_summary_json == (
        events[1].before_summary_json
    )
    assert events[0].after_summary_json["decision_reason"] == (
        "First reviewed adjustment"
    )
    assert events[1].after_summary_json["decision_reason"] == (
        "Second reviewed adjustment"
    )
    assert events[1].after_summary_json["final_quantity"] == (
        "7.000000"
    )
    assert events[0].after_summary_json["decision_type"] == (
        first_item.decision_type.value
        if first_item.decision_type is not None
        else None
    )
    assert events[0].after_summary_json["decision_risk"] == (
        first_item.decision_risk
    )
    assert events[0].after_summary_json[
        "requires_admin_confirmation"
    ] is first_item.requires_admin_confirmation
    assert events[0].after_summary_json[
        "confirmed_by_admin"
    ] is first_item.confirmed_by_admin
    assert events[0].after_summary_json[
        "risk_rule_version"
    ] == first_item.risk_rule_version


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


# Task 3B RED: shared lifecycle command shell and submit.


def _task3_create_draft(
    session,
    actor,
    *,
    key: str,
    name: str = "Task 3 lifecycle draft",
):
    return _task2g_create_draft(
        session,
        actor,
        key=key,
        name=name,
    )


def _task3_persisted_list(
    session,
    demand_list_id: int,
):
    from app.models import DemandList

    row = session.get(DemandList, demand_list_id)
    assert row is not None
    return row


def _task3_latest_event(
    session,
    demand_list_id: int,
):
    from app.models import DemandListEvent

    event = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.demand_list_id
            == demand_list_id
        )
        .order_by(DemandListEvent.id.desc())
        .first()
    )
    assert event is not None
    return event


def test_task3b_submit_moves_draft_and_records_counts(
    session,
    actor_contributor,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-submit-success",
    )

    submitted = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3b-submit-command",
    )

    assert submitted.status.value == (
        "PENDING_CONFIRMATION"
    )
    assert submitted.version == created.version + 1
    assert submitted.submitted_by_user_id == (
        actor_contributor.user_id
    )
    assert submitted.submitted_by_request_id == (
        actor_contributor.request_id
    )
    assert submitted.submitted_at is not None

    event = submitted.events[-1]
    assert event.event_type.value == "SUBMITTED"
    assert event.after_summary_json == {
        "lineage_id": submitted.lineage_id,
        "version_number": submitted.version_number,
        "status": "PENDING_CONFIRMATION",
        "is_current": False,
        "item_count": 2,
        "high_risk_item_count": 0,
        "requires_admin_confirmation_count": 0,
        "unconfirmed_item_count": 0,
        "version": submitted.version,
    }


def test_task3b_submit_counts_required_high_risk_items(
    session,
    actor_contributor,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-submit-risk-counts",
    )
    high = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        high.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Create high-risk review",
    )

    submitted = service.submit(
        session,
        actor_contributor,
        updated.id,
        expected_version=updated.version,
        idempotency_key="task3b-submit-risk-command",
    )

    summary = submitted.events[-1].after_summary_json
    assert summary["high_risk_item_count"] == 1
    assert (
        summary[
            "requires_admin_confirmation_count"
        ]
        == 1
    )
    assert summary["unconfirmed_item_count"] == 1


def test_task3b_submit_rejects_empty_list(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandListItem

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-empty-source",
    )
    session.query(DemandListItem).filter(
        DemandListItem.demand_list_id == created.id
    ).delete(synchronize_session=False)
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-empty-submit",
        )

    assert captured.value.code == "DEMAND_LIST_EMPTY"


def test_task3b_viewer_cannot_submit(
    session,
    actor_contributor,
    actor_viewer,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-viewer-source",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.submit(
            session,
            actor_viewer,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-viewer-submit",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3b_submit_rejects_stale_version_details(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-stale-source",
    )
    stale = created.version + 1

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=stale,
            idempotency_key="task3b-stale-submit",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": created.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3b_submit_rejects_invalid_transition(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-transition-source",
    )
    row = _task3_persisted_list(
        session,
        created.id,
    )
    row.status = DemandListStatus.CONFIRMED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=created.version,
            idempotency_key=(
                "task3b-transition-submit"
            ),
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "submit",
        "expected_status": "DRAFT",
        "actual_status": "CONFIRMED",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3b_submit_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-tenant-source",
    )
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.submit(
            session,
            tenant_b,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-tenant-submit",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": created.id,
    }


def test_task3b_submit_rolls_back_row_and_event_on_failure(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-rollback-source",
    )

    def fail_event(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "task3b forced event failure"
        )

    monkeypatch.setattr(
        service.repository,
        "append_event",
        fail_event,
    )

    with pytest.raises(
        RuntimeError,
        match="task3b forced event failure",
    ):
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-rollback-submit",
        )

    row = _task3_persisted_list(
        session,
        created.id,
    )
    assert row.status.value == "DRAFT"
    assert row.version == created.version
    assert row.submitted_at is None
    assert row.submitted_by_user_id is None
    assert row.submitted_by_request_id is None
    assert _task3_latest_event(
        session,
        created.id,
    ).event_type.value == "CREATED"


# Task 3C RED: administrator confirmation evidence.


def _task3_pending_high_risk_list(
    session,
    actor,
    *,
    source_key: str,
    submit_key: str,
):
    service, created = _task3_create_draft(
        session,
        actor,
        key=source_key,
    )
    target = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )
    updated = service.update_item(
        session,
        actor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Require admin confirmation",
    )
    pending = service.submit(
        session,
        actor,
        updated.id,
        expected_version=updated.version,
        idempotency_key=submit_key,
    )
    return service, pending, target.id


def test_task3c_admin_confirms_all_required_items(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, pending, target_id = (
        _task3_pending_high_risk_list(
            session,
            actor_contributor,
            source_key="task3c-confirm-source",
            submit_key="task3c-confirm-submit",
        )
    )

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="  Reviewed risk evidence  ",
        idempotency_key="task3c-confirm-command",
    )

    target = next(
        item
        for item in confirmed.items
        if item.id == target_id
    )
    low = next(
        item
        for item in confirmed.items
        if item.id != target_id
    )

    assert confirmed.status.value == "CONFIRMED"
    assert confirmed.version == pending.version + 1
    assert confirmed.confirmed_by_user_id == (
        actor_admin.user_id
    )
    assert confirmed.confirmed_by_request_id == (
        actor_admin.request_id
    )
    assert confirmed.confirmed_at is not None
    assert target.confirmed_by_admin is True
    assert target.version == 3
    assert low.confirmed_by_admin is False
    assert low.version == 1

    event = confirmed.events[-1]
    assert event.event_type.value == "CONFIRMED"
    assert event.after_summary_json[
        "confirmation_note"
    ] == "Reviewed risk evidence"
    assert event.after_summary_json[
        "confirmed_item_ids"
    ] == [target_id]
    assert event.after_summary_json[
        "confirmed_item_count"
    ] == 1


def test_task3c_confirm_without_required_items_is_audited(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-low-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-low-submit",
    )

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="No elevated risks found",
        idempotency_key="task3c-low-confirm",
    )

    assert confirmed.status.value == "CONFIRMED"
    assert confirmed.events[-1].after_summary_json[
        "confirmed_item_ids"
    ] == []
    assert confirmed.events[-1].after_summary_json[
        "confirmed_item_count"
    ] == 0
    assert all(
        item.version == 1
        for item in confirmed.items
    )


def test_task3c_contributor_cannot_confirm(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-role-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-role-submit",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.confirm(
            session,
            actor_contributor,
            pending.id,
            expected_version=pending.version,
            confirmation_note="Forbidden",
            idempotency_key="task3c-role-confirm",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3c_direct_blank_note_has_stable_code(
    session,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.confirm(
            session,
            actor_admin,
            999,
            expected_version=1,
            confirmation_note="   ",
            idempotency_key="task3c-blank-note",
        )

    assert captured.value.code == (
        "DEMAND_LIST_CONFIRMATION_NOTE_REQUIRED"
    )


def test_task3c_direct_overlong_note_has_stable_code(
    session,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.confirm(
            session,
            actor_admin,
            999,
            expected_version=1,
            confirmation_note="x" * 1001,
            idempotency_key="task3c-long-note",
        )

    assert captured.value.code == (
        "DEMAND_LIST_CONFIRMATION_NOTE_INVALID"
    )


def test_task3c_confirm_rejects_invalid_transition(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-transition-source",
    )

    with pytest.raises(ConflictError) as captured:
        service.confirm(
            session,
            actor_admin,
            created.id,
            expected_version=created.version,
            confirmation_note="Invalid transition",
            idempotency_key="task3c-transition-confirm",
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "confirm",
        "expected_status": "PENDING_CONFIRMATION",
        "actual_status": "DRAFT",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3c_confirm_rejects_stale_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-stale-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-stale-submit",
    )
    stale = pending.version + 1

    with pytest.raises(ConflictError) as captured:
        service.confirm(
            session,
            actor_admin,
            pending.id,
            expected_version=stale,
            confirmation_note="Stale confirmation",
            idempotency_key="task3c-stale-confirm",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": pending.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3c_confirm_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError
    from app.security.actor import MaintenanceRole

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-tenant-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-tenant-submit",
    )
    tenant_b_admin = actor_context(
        tenant_id="tenant-b",
        user_id="admin-b",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-b",
        token_id="token-admin-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.confirm(
            session,
            tenant_b_admin,
            pending.id,
            expected_version=pending.version,
            confirmation_note="Cross tenant",
            idempotency_key="task3c-tenant-confirm",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": pending.id,
    }


def test_task3c_confirm_commits_once(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-commit-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-commit-submit",
    )

    original_commit = session.commit
    commit_calls = []

    def counted_commit():
        commit_calls.append("commit")
        return original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Commit once",
        idempotency_key="task3c-commit-confirm",
    )

    assert commit_calls == ["commit"]


def test_task3c_confirmed_ids_are_sorted(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandListItem

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-sorted-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-sorted-submit",
    )

    items = (
        session.query(DemandListItem)
        .filter(
            DemandListItem.demand_list_id
            == pending.id
        )
        .order_by(DemandListItem.id.desc())
        .all()
    )
    assert len(items) == 2
    for item in items:
        item.requires_admin_confirmation = True
        item.confirmed_by_admin = False
    session.commit()

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Confirm sorted IDs",
        idempotency_key="task3c-sorted-confirm",
    )

    assert confirmed.events[-1].after_summary_json[
        "confirmed_item_ids"
    ] == sorted(item.id for item in items)


def test_task3c_confirm_rolls_back_items_row_and_event(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    service, pending, target_id = (
        _task3_pending_high_risk_list(
            session,
            actor_contributor,
            source_key="task3c-rollback-source",
            submit_key="task3c-rollback-submit",
        )
    )
    before_versions = {
        item.id: item.version
        for item in pending.items
    }
    before_flags = {
        item.id: item.confirmed_by_admin
        for item in pending.items
    }

    def fail_event(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "task3c forced event failure"
        )

    monkeypatch.setattr(
        service.repository,
        "append_event",
        fail_event,
    )

    with pytest.raises(
        RuntimeError,
        match="task3c forced event failure",
    ):
        service.confirm(
            session,
            actor_admin,
            pending.id,
            expected_version=pending.version,
            confirmation_note="Rollback confirmation",
            idempotency_key="task3c-rollback-confirm",
        )

    row = _task3_persisted_list(
        session,
        pending.id,
    )
    assert row.status.value == (
        "PENDING_CONFIRMATION"
    )
    assert row.version == pending.version
    assert row.confirmed_by_user_id is None
    assert row.confirmed_by_request_id is None
    assert row.confirmed_at is None

    reloaded = service.get(
        session,
        actor_admin,
        pending.id,
    )
    assert {
        item.id: item.version
        for item in reloaded.items
    } == before_versions
    assert {
        item.id: item.confirmed_by_admin
        for item in reloaded.items
    } == before_flags
    assert next(
        item
        for item in reloaded.items
        if item.id == target_id
    ).confirmed_by_admin is False
    assert all(
        event.event_type.value != "CONFIRMED"
        for event in reloaded.events
    )


# Task 3D RED: atomic publication and published immutability.


def _task3_confirmed_list(
    session,
    actor_contributor,
    actor_admin,
    *,
    source_key: str,
    submit_key: str,
    confirm_key: str,
):
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key=source_key,
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key=submit_key,
    )
    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Lifecycle approval",
        idempotency_key=confirm_key,
    )
    return service, confirmed


def test_task3d_publish_sets_current_and_metadata(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-publish-source",
        submit_key="task3d-publish-submit",
        confirm_key="task3d-publish-confirm",
    )

    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-publish-command",
    )

    assert published.status.value == "PUBLISHED"
    assert published.is_current is True
    assert published.version == confirmed.version + 1
    assert published.published_by_user_id == (
        actor_admin.user_id
    )
    assert published.published_by_request_id == (
        actor_admin.request_id
    )
    assert published.published_at is not None
    assert published.events[-1].event_type.value == (
        "PUBLISHED"
    )


def test_task3d_publish_rejects_unconfirmed_required_ids(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandListItem
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3d-unconfirmed-source",
    )
    target = created.items[0]
    row = _task3_persisted_list(
        session,
        created.id,
    )
    item = session.get(DemandListItem, target.id)
    assert item is not None
    item.requires_admin_confirmation = True
    item.confirmed_by_admin = False
    row.status = DemandListStatus.CONFIRMED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.publish(
            session,
            actor_admin,
            created.id,
            expected_version=created.version,
            idempotency_key=(
                "task3d-unconfirmed-publish"
            ),
        )

    assert captured.value.code == (
        "DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED"
    )
    assert captured.value.details == {
        "unconfirmed_item_ids": [target.id],
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3d_new_publish_supersedes_old_current(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, confirmed_v1 = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-v1-source",
        submit_key="task3d-v1-submit",
        confirm_key="task3d-v1-confirm",
    )
    published_v1 = service.publish(
        session,
        actor_admin,
        confirmed_v1.id,
        expected_version=confirmed_v1.version,
        idempotency_key="task3d-v1-publish",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3d-v2-derive",
    )
    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3d-v2-submit",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3d-v2-confirm",
    )

    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3d-v2-publish",
    )

    old = session.get(DemandList, published_v1.id)
    assert old is not None
    assert old.status.value == "PUBLISHED"
    assert old.is_current is False
    assert old.superseded_by_id == published_v2.id
    assert old.superseded_at is not None
    assert old.version == published_v1.version + 1

    current_rows = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v2.lineage_id,
            DemandList.status == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .all()
    )
    assert [row.id for row in current_rows] == [
        published_v2.id
    ]


def test_task3d_publish_rejects_empty_confirmed_list(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandListItem

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-empty-source",
        submit_key="task3d-empty-submit",
        confirm_key="task3d-empty-confirm",
    )
    session.query(DemandListItem).filter(
        DemandListItem.demand_list_id
        == confirmed.id
    ).delete(synchronize_session=False)
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.publish(
            session,
            actor_admin,
            confirmed.id,
            expected_version=confirmed.version,
            idempotency_key="task3d-empty-publish",
        )

    assert captured.value.code == "DEMAND_LIST_EMPTY"
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3d_contributor_cannot_publish(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-role-source",
        submit_key="task3d-role-submit",
        confirm_key="task3d-role-confirm",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.publish(
            session,
            actor_contributor,
            confirmed.id,
            expected_version=confirmed.version,
            idempotency_key="task3d-role-publish",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3d_publish_rejects_invalid_transition(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3d-transition-source",
    )

    with pytest.raises(ConflictError) as captured:
        service.publish(
            session,
            actor_admin,
            created.id,
            expected_version=created.version,
            idempotency_key=(
                "task3d-transition-publish"
            ),
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "publish",
        "expected_status": "CONFIRMED",
        "actual_status": "DRAFT",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3d_publish_rejects_stale_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-stale-source",
        submit_key="task3d-stale-submit",
        confirm_key="task3d-stale-confirm",
    )
    stale = confirmed.version + 1

    with pytest.raises(ConflictError) as captured:
        service.publish(
            session,
            actor_admin,
            confirmed.id,
            expected_version=stale,
            idempotency_key="task3d-stale-publish",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": confirmed.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3d_publish_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
    actor_admin,
) -> None:
    from app.core.exceptions import NotFoundError
    from app.security.actor import MaintenanceRole

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-tenant-source",
        submit_key="task3d-tenant-submit",
        confirm_key="task3d-tenant-confirm",
    )
    tenant_b_admin = actor_context(
        tenant_id="tenant-b",
        user_id="admin-b",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-b",
        token_id="token-admin-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.publish(
            session,
            tenant_b_admin,
            confirmed.id,
            expected_version=confirmed.version,
            idempotency_key="task3d-tenant-publish",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": confirmed.id,
    }


def test_task3d_publish_event_summaries_are_complete(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-summary-source",
        submit_key="task3d-summary-submit",
        confirm_key="task3d-summary-confirm",
    )

    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-summary-publish",
    )

    event = published.events[-1]
    assert event.before_summary_json == {
        "lineage_id": confirmed.lineage_id,
        "version_number": confirmed.version_number,
        "status": "CONFIRMED",
        "is_current": False,
        "version": confirmed.version,
        "previous_current": None,
    }
    assert event.after_summary_json == {
        "lineage_id": published.lineage_id,
        "version_number": published.version_number,
        "status": "PUBLISHED",
        "is_current": True,
        "item_count": len(published.items),
        "superseded_demand_list_id": None,
        "version": published.version,
    }


def test_task3d_publish_commits_once(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-commit-source",
        submit_key="task3d-commit-submit",
        confirm_key="task3d-commit-confirm",
    )

    original_commit = session.commit
    commit_calls = []

    def counted_commit():
        commit_calls.append("commit")
        return original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-commit-publish",
    )

    assert commit_calls == ["commit"]


def test_task3d_publish_rolls_back_both_versions_and_event(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, target_confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-rollback-target-source",
        submit_key="task3d-rollback-target-submit",
        confirm_key="task3d-rollback-target-confirm",
    )
    target = session.get(
        DemandList,
        target_confirmed.id,
    )
    assert target is not None

    target.version_number = 2
    session.commit()

    old = DemandList(
        tenant_id=target.tenant_id,
        name=target.name,
        description=target.description,
        lineage_id=target.lineage_id,
        version_number=1,
        derived_from_id=None,
        scenario_version_id=(
            target.scenario_version_id
        ),
        calculation_group_id=(
            target.calculation_group_id
        ),
        status=DemandListStatus.PUBLISHED,
        is_current=True,
        created_by_user_id=(
            target.created_by_user_id
        ),
        created_by_request_id=(
            target.created_by_request_id
        ),
        submitted_by_user_id=(
            target.submitted_by_user_id
        ),
        submitted_by_request_id=(
            target.submitted_by_request_id
        ),
        submitted_at=target.submitted_at,
        confirmed_by_user_id=(
            target.confirmed_by_user_id
        ),
        confirmed_by_request_id=(
            target.confirmed_by_request_id
        ),
        confirmed_at=target.confirmed_at,
        published_by_user_id=actor_admin.user_id,
        published_by_request_id=(
            actor_admin.request_id
        ),
        published_at=target.confirmed_at,
    )
    session.add(old)
    session.commit()

    old_id = old.id
    target_id = target.id
    old_version = old.version
    target_version = target.version

    def fail_snapshot(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "task3d forced snapshot failure"
        )

    monkeypatch.setattr(
        service,
        "_response_with_event_snapshot",
        fail_snapshot,
    )

    with pytest.raises(
        RuntimeError,
        match="task3d forced snapshot failure",
    ):
        service.publish(
            session,
            actor_admin,
            target_id,
            expected_version=target_version,
            idempotency_key=(
                "task3d-rollback-publish"
            ),
        )

    reloaded_old = session.get(
        DemandList,
        old_id,
    )
    reloaded_target = session.get(
        DemandList,
        target_id,
    )
    assert reloaded_old is not None
    assert reloaded_target is not None

    assert reloaded_old.status.value == "PUBLISHED"
    assert reloaded_old.is_current is True
    assert reloaded_old.superseded_by_id is None
    assert reloaded_old.superseded_at is None
    assert reloaded_old.version == old_version

    assert reloaded_target.status.value == "CONFIRMED"
    assert reloaded_target.is_current is False
    assert reloaded_target.published_by_user_id is None
    assert (
        reloaded_target.published_by_request_id
        is None
    )
    assert reloaded_target.published_at is None
    assert reloaded_target.version == target_version

    assert all(
        event.event_type.value != "PUBLISHED"
        for event in service.get(
            session,
            actor_admin,
            target_id,
        ).events
    )


def test_task3d_published_items_are_immutable(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-immutable-source",
        submit_key="task3d-immutable-submit",
        confirm_key="task3d-immutable-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-immutable-publish",
    )

    with pytest.raises(ConflictError) as captured:
        service.update_item(
            session,
            actor_admin,
            published.id,
            published.items[0].id,
            expected_version=published.version,
            final_quantity=Decimal("1.000000"),
            adjustment_reason="Forbidden edit",
        )

    assert captured.value.code == (
        "PUBLISHED_DEMAND_LIST_IMMUTABLE"
    )
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


# Task 3E RED: derive an isolated draft in the same lineage.


def _task3_published_list(
    session,
    actor_contributor,
    actor_admin,
    *,
    source_key: str,
    submit_key: str,
    confirm_key: str,
    publish_key: str,
):
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key=source_key,
        submit_key=submit_key,
        confirm_key=confirm_key,
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=publish_key,
    )
    return service, published


def test_task3e_derive_copies_lineage_items_and_snapshots(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-source",
        submit_key="task3e-submit",
        confirm_key="task3e-confirm",
        publish_key="task3e-publish",
    )
    source_dump = published.model_dump(
        mode="json"
    )

    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-derive",
    )

    assert derived.status.value == "DRAFT"
    assert derived.is_current is False
    assert derived.lineage_id == published.lineage_id
    assert derived.version_number == (
        published.version_number + 1
    )
    assert derived.derived_from_id == published.id
    assert derived.scenario_version_id == (
        published.scenario_version_id
    )
    assert derived.calculation_group_id == (
        published.calculation_group_id
    )
    assert derived.name == published.name
    assert derived.description == published.description
    assert derived.version == 1
    assert len(derived.items) == len(published.items)
    assert all(
        item.version == 1
        for item in derived.items
    )

    source_by_spare = {
        item.spare_part_id: item
        for item in published.items
    }
    for item in derived.items:
        source = source_by_spare[item.spare_part_id]
        assert item.id != source.id
        assert item.original_quantity == (
            source.original_quantity
        )
        assert item.final_quantity == (
            source.final_quantity
        )
        assert item.decision_type == source.decision_type
        assert item.decision_risk == source.decision_risk
        assert (
            item.requires_admin_confirmation
            is source.requires_admin_confirmation
        )
        assert (
            item.confirmed_by_admin
            is source.confirmed_by_admin
        )
        assert item.source_snapshot_json == (
            source.source_snapshot_json
        )
        assert item.decision_snapshot_json == (
            source.decision_snapshot_json
        )
        assert item.interval_snapshot_json == (
            source.interval_snapshot_json
        )
        assert item.parameter_snapshot_json == (
            source.parameter_snapshot_json
        )
        assert item.warning_snapshot_json == (
            source.warning_snapshot_json
        )
        assert item.inventory_snapshot_json == (
            source.inventory_snapshot_json
        )

    derived.items[0].interval_snapshot_json[
        "candidates"
    ][0]["warnings"].append("TASK3E-MUTATION")
    reloaded_source = service.get(
        session,
        actor_admin,
        published.id,
    )
    assert "TASK3E-MUTATION" not in (
        reloaded_source.items[0]
        .interval_snapshot_json["candidates"][0]
        ["warnings"]
    )
    assert published.model_dump(mode="json") == (
        source_dump
    )


def test_task3e_derive_event_is_on_new_draft(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-event-source",
        submit_key="task3e-event-submit",
        confirm_key="task3e-event-confirm",
        publish_key="task3e-event-publish",
    )

    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-event-derive",
    )

    event = derived.events[-1]
    assert event.demand_list_id == derived.id
    assert event.event_type.value == "DERIVED"
    assert event.after_summary_json == {
        "derived_from_id": published.id,
        "lineage_id": published.lineage_id,
        "source_version_number": (
            published.version_number
        ),
        "new_version_number": (
            derived.version_number
        ),
        "copied_item_count": len(derived.items),
        "status": "DRAFT",
        "version": 1,
    }


def test_task3e_contributor_cannot_derive(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-role-source",
        submit_key="task3e-role-submit",
        confirm_key="task3e-role-confirm",
        publish_key="task3e-role-publish",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.derive(
            session,
            actor_contributor,
            published.id,
            expected_version=published.version,
            idempotency_key="task3e-role-derive",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3e_derive_requires_published_source(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-status-source",
        submit_key="task3e-status-submit",
        confirm_key="task3e-status-confirm",
    )

    with pytest.raises(ConflictError) as captured:
        service.derive(
            session,
            actor_admin,
            confirmed.id,
            expected_version=confirmed.version,
            idempotency_key="task3e-status-derive",
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "derive",
        "expected_status": "PUBLISHED",
        "actual_status": "CONFIRMED",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3e_derive_rejects_stale_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-stale-source",
        submit_key="task3e-stale-submit",
        confirm_key="task3e-stale-confirm",
        publish_key="task3e-stale-publish",
    )
    stale = published.version + 1

    with pytest.raises(ConflictError) as captured:
        service.derive(
            session,
            actor_admin,
            published.id,
            expected_version=stale,
            idempotency_key="task3e-stale-derive",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": published.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3e_derive_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
    actor_admin,
) -> None:
    from app.core.exceptions import NotFoundError
    from app.security.actor import MaintenanceRole

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-tenant-source",
        submit_key="task3e-tenant-submit",
        confirm_key="task3e-tenant-confirm",
        publish_key="task3e-tenant-publish",
    )
    tenant_b_admin = actor_context(
        tenant_id="tenant-b",
        user_id="admin-b",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-b",
        token_id="token-admin-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.derive(
            session,
            tenant_b_admin,
            published.id,
            expected_version=published.version,
            idempotency_key="task3e-tenant-derive",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": published.id,
    }


def test_task3e_derive_does_not_mutate_source(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-source-stable-source",
        submit_key="task3e-source-stable-submit",
        confirm_key="task3e-source-stable-confirm",
        publish_key="task3e-source-stable-publish",
    )
    source_before = service.get(
        session,
        actor_admin,
        published.id,
    ).model_dump(mode="json")

    service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key=(
            "task3e-source-stable-derive"
        ),
    )

    source_after = service.get(
        session,
        actor_admin,
        published.id,
    ).model_dump(mode="json")

    assert source_after == source_before


def test_task3e_derive_replays_exact_response(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
    )
    from app.models.enums import DemandListEventType

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-replay-source",
        submit_key="task3e-replay-submit",
        confirm_key="task3e-replay-confirm",
        publish_key="task3e-replay-publish",
    )

    first = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-replay-derive",
    )
    second = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-replay-derive",
    )

    assert second.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )

    lineage_rows = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_admin.tenant_id,
            DemandList.lineage_id
            == published.lineage_id,
        )
        .order_by(DemandList.version_number)
        .all()
    )
    assert [
        row.version_number
        for row in lineage_rows
    ] == [
        published.version_number,
        first.version_number,
    ]

    derived_events = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.event_type
            == DemandListEventType.DERIVED,
            DemandListEvent.demand_list_id
            == first.id,
        )
        .all()
    )
    assert len(derived_events) == 1


def test_task3e_derive_commits_once(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-commit-source",
        submit_key="task3e-commit-submit",
        confirm_key="task3e-commit-confirm",
        publish_key="task3e-commit-publish",
    )

    original_commit = session.commit
    commit_calls = []

    def counted_commit():
        commit_calls.append("commit")
        return original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-commit-derive",
    )

    assert commit_calls == ["commit"]


def test_task3e_derive_rolls_back_partial_copy(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    from app.models import (
        DemandList,
        DemandListEvent,
        DemandListItem,
    )
    from app.models.enums import DemandListEventType

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-rollback-source",
        submit_key="task3e-rollback-submit",
        confirm_key="task3e-rollback-confirm",
        publish_key="task3e-rollback-publish",
    )

    list_count_before = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_admin.tenant_id,
            DemandList.lineage_id
            == published.lineage_id,
        )
        .count()
    )
    item_count_before = (
        session.query(DemandListItem)
        .join(
            DemandList,
            DemandListItem.demand_list_id
            == DemandList.id,
        )
        .filter(
            DemandListItem.tenant_id
            == actor_admin.tenant_id,
            DemandList.lineage_id
            == published.lineage_id,
        )
        .count()
    )
    event_count_before = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.event_type
            == DemandListEventType.DERIVED,
        )
        .count()
    )

    original_copy = getattr(
        type(service),
        "_copy_item_to_derived",
        None,
    )
    copy_calls = []

    def fail_second_copy(*args, **kwargs):
        copy_calls.append("copy")
        if len(copy_calls) == 2:
            raise RuntimeError(
                "task3e forced copy failure"
            )
        if original_copy is None:
            return None
        return original_copy(
            service,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        service,
        "_copy_item_to_derived",
        fail_second_copy,
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="task3e forced copy failure",
    ):
        service.derive(
            session,
            actor_admin,
            published.id,
            expected_version=published.version,
            idempotency_key=(
                "task3e-rollback-derive"
            ),
        )

    assert len(copy_calls) == 2
    assert (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_admin.tenant_id,
            DemandList.lineage_id
            == published.lineage_id,
        )
        .count()
        == list_count_before
    )
    assert (
        session.query(DemandListItem)
        .join(
            DemandList,
            DemandListItem.demand_list_id
            == DemandList.id,
        )
        .filter(
            DemandListItem.tenant_id
            == actor_admin.tenant_id,
            DemandList.lineage_id
            == published.lineage_id,
        )
        .count()
        == item_count_before
    )
    assert (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.event_type
            == DemandListEventType.DERIVED,
        )
        .count()
        == event_count_before
    )


# Task 3F RED: void published versions without restoring history.


def test_task3f_void_current_published_clears_current(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-source",
        submit_key="task3f-submit",
        confirm_key="task3f-confirm",
        publish_key="task3f-publish",
    )

    voided = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-void",
    )

    assert voided.status.value == "VOIDED"
    assert voided.is_current is False
    assert voided.version == published.version + 1
    assert voided.voided_by_user_id == (
        actor_admin.user_id
    )
    assert voided.voided_by_request_id == (
        actor_admin.request_id
    )
    assert voided.voided_at is not None
    assert len(voided.items) == len(published.items)
    assert voided.events[-1].event_type.value == (
        "VOIDED"
    )


def test_task3f_void_does_not_restore_superseded_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, published_v1 = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-v1-source",
        submit_key="task3f-v1-submit",
        confirm_key="task3f-v1-confirm",
        publish_key="task3f-v1-publish",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3f-v2-derive",
    )
    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3f-v2-submit",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3f-v2-confirm",
    )
    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3f-v2-publish",
    )

    service.void(
        session,
        actor_admin,
        published_v2.id,
        expected_version=published_v2.version,
        idempotency_key="task3f-v2-void",
    )

    old = session.get(DemandList, published_v1.id)
    assert old is not None
    assert old.status.value == "PUBLISHED"
    assert old.is_current is False

    current_count = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v1.lineage_id,
            DemandList.status
            == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .count()
    )
    assert current_count == 0


def test_task3f_void_noncurrent_published_history(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published_v1 = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-history-source",
        submit_key="task3f-history-submit",
        confirm_key="task3f-history-confirm",
        publish_key="task3f-history-publish",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3f-history-v2-derive",
    )
    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3f-history-v2-submit",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve history version 2",
        idempotency_key="task3f-history-v2-confirm",
    )
    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3f-history-v2-publish",
    )

    voided_v1 = service.void(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version + 1,
        idempotency_key="task3f-history-v1-void",
    )

    current_v2 = service.get(
        session,
        actor_admin,
        published_v2.id,
    )
    assert voided_v1.status.value == "VOIDED"
    assert voided_v1.is_current is False
    assert current_v2.status.value == "PUBLISHED"
    assert current_v2.is_current is True
    assert current_v2.version == published_v2.version


def test_task3f_contributor_cannot_void(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-role-source",
        submit_key="task3f-role-submit",
        confirm_key="task3f-role-confirm",
        publish_key="task3f-role-publish",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.void(
            session,
            actor_contributor,
            published.id,
            expected_version=published.version,
            idempotency_key="task3f-role-void",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3f_void_requires_published_source(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-status-source",
        submit_key="task3f-status-submit",
        confirm_key="task3f-status-confirm",
    )

    with pytest.raises(ConflictError) as captured:
        service.void(
            session,
            actor_admin,
            confirmed.id,
            expected_version=confirmed.version,
            idempotency_key="task3f-status-void",
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "void",
        "expected_status": "PUBLISHED",
        "actual_status": "CONFIRMED",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3f_void_rejects_stale_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-stale-source",
        submit_key="task3f-stale-submit",
        confirm_key="task3f-stale-confirm",
        publish_key="task3f-stale-publish",
    )
    stale = published.version + 1

    with pytest.raises(ConflictError) as captured:
        service.void(
            session,
            actor_admin,
            published.id,
            expected_version=stale,
            idempotency_key="task3f-stale-void",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": published.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3f_void_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
    actor_admin,
) -> None:
    from app.core.exceptions import NotFoundError
    from app.security.actor import MaintenanceRole

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-tenant-source",
        submit_key="task3f-tenant-submit",
        confirm_key="task3f-tenant-confirm",
        publish_key="task3f-tenant-publish",
    )
    tenant_b_admin = actor_context(
        tenant_id="tenant-b",
        user_id="admin-b",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-b",
        token_id="token-admin-b",
    )

    with pytest.raises(NotFoundError) as captured:
        service.void(
            session,
            tenant_b_admin,
            published.id,
            expected_version=published.version,
            idempotency_key="task3f-tenant-void",
        )

    assert captured.value.code == "RESOURCE_NOT_FOUND"
    assert captured.value.details == {
        "resource": "demand_list",
        "identifier": published.id,
    }


def test_task3f_void_commits_once(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-commit-source",
        submit_key="task3f-commit-submit",
        confirm_key="task3f-commit-confirm",
        publish_key="task3f-commit-publish",
    )

    original_commit = session.commit
    commit_calls = []

    def counted_commit():
        commit_calls.append("commit")
        return original_commit()

    monkeypatch.setattr(
        session,
        "commit",
        counted_commit,
    )

    service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-commit-void",
    )

    assert commit_calls == ["commit"]


def test_task3f_void_event_summaries_are_complete(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-summary-source",
        submit_key="task3f-summary-submit",
        confirm_key="task3f-summary-confirm",
        publish_key="task3f-summary-publish",
    )

    voided = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-summary-void",
    )

    event = voided.events[-1]
    assert event.before_summary_json == {
        "lineage_id": published.lineage_id,
        "version_number": published.version_number,
        "status": "PUBLISHED",
        "is_current": True,
        "version": published.version,
    }
    assert event.after_summary_json == {
        "lineage_id": voided.lineage_id,
        "version_number": voided.version_number,
        "status": "VOIDED",
        "is_current": False,
        "version": voided.version,
    }


def test_task3f_void_replays_exact_response(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandListEvent
    from app.models.enums import DemandListEventType

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-replay-source",
        submit_key="task3f-replay-submit",
        confirm_key="task3f-replay-confirm",
        publish_key="task3f-replay-publish",
    )

    first = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-replay-void",
    )
    second = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-replay-void",
    )

    assert second.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )

    voided_events = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.demand_list_id
            == published.id,
            DemandListEvent.event_type
            == DemandListEventType.VOIDED,
            DemandListEvent.idempotency_key
            == "task3f-replay-void",
        )
        .all()
    )
    assert len(voided_events) == 1


def test_task3f_void_rolls_back_row_and_event(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
) -> None:
    from app.models import DemandListEvent
    from app.models.enums import DemandListEventType

    service, published = _task3_published_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-rollback-source",
        submit_key="task3f-rollback-submit",
        confirm_key="task3f-rollback-confirm",
        publish_key="task3f-rollback-publish",
    )
    published_version = published.version
    published_item_snapshots = [
        item.model_dump(mode="json")
        for item in published.items
    ]
    event_count_before = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.demand_list_id
            == published.id,
        )
        .count()
    )

    def fail_snapshot(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "task3f forced snapshot failure"
        )

    monkeypatch.setattr(
        service,
        "_response_with_event_snapshot",
        fail_snapshot,
    )

    with pytest.raises(
        RuntimeError,
        match="task3f forced snapshot failure",
    ):
        service.void(
            session,
            actor_admin,
            published.id,
            expected_version=published.version,
            idempotency_key="task3f-rollback-void",
        )

    reloaded = service.get(
        session,
        actor_admin,
        published.id,
    )
    assert reloaded.status.value == "PUBLISHED"
    assert reloaded.is_current is True
    assert reloaded.version == published_version
    assert reloaded.voided_by_user_id is None
    assert reloaded.voided_by_request_id is None
    assert reloaded.voided_at is None
    assert [
        item.model_dump(mode="json")
        for item in reloaded.items
    ] == published_item_snapshots

    event_count_after = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.demand_list_id
            == published.id,
        )
        .count()
    )
    assert event_count_after == event_count_before

    voided_event_count = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_admin.tenant_id,
            DemandListEvent.demand_list_id
            == published.id,
            DemandListEvent.event_type
            == DemandListEventType.VOIDED,
        )
        .count()
    )
    assert voided_event_count == 0


# Task 3G RED: exact replay and shared race recovery for every action.


_TASK3G_ACTIONS = (
    "submit",
    "confirm",
    "publish",
    "derive",
    "void",
)


def _task3g_build_action_case(
    session,
    actor_contributor,
    actor_admin,
    *,
    action: str,
    prefix: str,
):
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key=f"{prefix}-source",
    )
    if action == "submit":
        return {
            "action": action,
            "service": service,
            "actor": actor_contributor,
            "demand_list_id": created.id,
            "expected_version": created.version,
            "confirmation_note": None,
        }

    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key=f"{prefix}-seed-submit",
    )
    if action == "confirm":
        return {
            "action": action,
            "service": service,
            "actor": actor_admin,
            "demand_list_id": pending.id,
            "expected_version": pending.version,
            "confirmation_note": (
                "  Task 3G confirmation  "
            ),
        }

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Task 3G seed confirmation",
        idempotency_key=f"{prefix}-seed-confirm",
    )
    if action == "publish":
        return {
            "action": action,
            "service": service,
            "actor": actor_admin,
            "demand_list_id": confirmed.id,
            "expected_version": confirmed.version,
            "confirmation_note": None,
        }

    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=f"{prefix}-seed-publish",
    )
    if action not in {"derive", "void"}:
        raise AssertionError(
            f"unsupported Task 3G action: {action}"
        )
    return {
        "action": action,
        "service": service,
        "actor": actor_admin,
        "demand_list_id": published.id,
        "expected_version": published.version,
        "confirmation_note": None,
    }


def _task3g_invoke(
    session,
    case,
    *,
    idempotency_key: str,
    expected_version: int | None = None,
    confirmation_note: str | None = None,
):
    kwargs = {
        "expected_version": (
            case["expected_version"]
            if expected_version is None
            else expected_version
        ),
        "idempotency_key": idempotency_key,
    }
    if case["action"] == "confirm":
        kwargs["confirmation_note"] = (
            case["confirmation_note"]
            if confirmation_note is None
            else confirmation_note
        )
    return getattr(
        case["service"],
        case["action"],
    )(
        session,
        case["actor"],
        case["demand_list_id"],
        **kwargs,
    )


def _task3g_expected_event_type(action: str):
    from app.models.enums import DemandListEventType

    return {
        "submit": DemandListEventType.SUBMITTED,
        "confirm": DemandListEventType.CONFIRMED,
        "publish": DemandListEventType.PUBLISHED,
        "derive": DemandListEventType.DERIVED,
        "void": DemandListEventType.VOIDED,
    }[action]


def _task3g_request_hash(case) -> str:
    kwargs = {
        "action": case["action"],
        "demand_list_id": case["demand_list_id"],
        "expected_version": case["expected_version"],
    }
    if case["action"] == "confirm":
        kwargs["confirmation_note"] = (
            case["confirmation_note"].strip()
        )
    return case["service"]._lifecycle_request_hash(
        **kwargs
    )


def _task3g_warning_list(read_model):
    interval = read_model.items[0].interval_snapshot_json
    assert interval is not None
    candidates = interval["candidates"]
    assert candidates
    warnings = candidates[0]["warnings"]
    assert isinstance(warnings, list)
    return warnings


def _task3g_snapshot_warning_list(snapshot):
    warnings = (
        snapshot["items"][0]
        ["interval_snapshot_json"]["candidates"][0]
        ["warnings"]
    )
    assert isinstance(warnings, list)
    return warnings


def _task3g_receipt(
    session,
    actor,
    *,
    idempotency_key: str,
):
    from app.models import DemandListEvent

    return (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor.tenant_id,
            DemandListEvent.idempotency_key
            == idempotency_key,
        )
        .one()
    )


def _task3g_install_lifecycle_race(
    session,
    case,
    monkeypatch,
    *,
    idempotency_key: str,
    winner_hash: str | None,
    winner_present: bool,
):
    from copy import deepcopy
    from types import SimpleNamespace

    from sqlalchemy.exc import IntegrityError

    service = case["service"]
    source_snapshot = service.get(
        session,
        case["actor"],
        case["demand_list_id"],
    ).model_dump(mode="json")
    expected_hash = _task3g_request_hash(case)
    raced_receipt = SimpleNamespace(
        event_type=_task3g_expected_event_type(
            case["action"]
        ),
        idempotency_key=idempotency_key,
        request_hash=(
            expected_hash
            if winner_hash is None
            else winner_hash
        ),
        response_snapshot_json=deepcopy(
            source_snapshot
        ),
    )
    original_error = IntegrityError(
        "INSERT INTO demand_list_events",
        {"idempotency_key": idempotency_key},
        Exception("duplicate lifecycle receipt"),
    )
    state = {
        "lookups": 0,
        "order": [],
    }

    def lookup_receipt(
        session_arg,
        tenant_id,
        key,
    ):
        del session_arg
        assert tenant_id == case["actor"].tenant_id
        assert key == idempotency_key
        state["lookups"] += 1
        state["order"].append(
            f"lookup-{state['lookups']}"
        )
        if state["lookups"] == 1:
            return None
        if winner_present:
            return raced_receipt
        return None

    def duplicate_receipt(*args, **kwargs):
        del args, kwargs
        raise original_error

    original_rollback = session.rollback

    def recorded_rollback():
        state["order"].append("rollback")
        return original_rollback()

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
    monkeypatch.setattr(
        session,
        "rollback",
        recorded_rollback,
    )
    return (
        raced_receipt,
        original_error,
        state,
    )


@pytest.mark.parametrize(
    "action",
    _TASK3G_ACTIONS,
)
def test_task3g_sequential_replay_is_exact_and_isolated(
    session,
    actor_contributor,
    actor_admin,
    action,
) -> None:
    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=f"task3g-replay-{action}",
    )
    key = f"task3g-replay-command-{action}"

    first = _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )
    replay = _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )

    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )
    receipt = _task3g_receipt(
        session,
        case["actor"],
        idempotency_key=key,
    )
    assert receipt.response_snapshot_json is not None

    _task3g_warning_list(replay).append(
        "TASK3G-REPLAY-MUTATION"
    )
    assert "TASK3G-REPLAY-MUTATION" not in (
        _task3g_snapshot_warning_list(
            receipt.response_snapshot_json
        )
    )

    third = _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )
    assert third.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )


def test_closure_lifecycle_receipts_are_non_recursive_and_exact(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandListEvent
    from app.schemas.demand_list import DemandListRead

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="closure-normalized-source",
        submit_key="closure-normalized-submit",
        confirm_key="closure-normalized-confirm",
    )
    key = "closure-normalized-publish"

    first = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=key,
    )
    receipt = session.query(DemandListEvent).filter(
        DemandListEvent.tenant_id == actor_admin.tenant_id,
        DemandListEvent.idempotency_key == key,
    ).one()
    stored = DemandListRead.model_validate(
        receipt.response_snapshot_json,
    )
    replay = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=key,
    )

    assert all(
        event.response_snapshot_json is None
        for event in stored.events
    )
    assert first.model_dump(mode="json") == (
        stored.model_dump(mode="json")
    )
    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )


@pytest.mark.parametrize(
    "action",
    _TASK3G_ACTIONS,
)
def test_task3g_same_key_changed_version_is_conflict(
    session,
    actor_contributor,
    actor_admin,
    action,
) -> None:
    from app.core.exceptions import ConflictError

    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=f"task3g-version-{action}",
    )
    key = f"task3g-version-command-{action}"

    _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )

    with pytest.raises(ConflictError) as captured:
        _task3g_invoke(
            session,
            case,
            idempotency_key=key,
            expected_version=(
                case["expected_version"] + 1
            ),
        )

    assert captured.value.code == (
        "IDEMPOTENCY_KEY_REUSED"
    )
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3g_confirm_same_key_changed_note_is_conflict(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action="confirm",
        prefix="task3g-note",
    )
    key = "task3g-note-command"

    _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )

    with pytest.raises(ConflictError) as captured:
        _task3g_invoke(
            session,
            case,
            idempotency_key=key,
            confirmation_note=(
                "Task 3G changed confirmation"
            ),
        )

    assert captured.value.code == (
        "IDEMPOTENCY_KEY_REUSED"
    )
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


@pytest.mark.parametrize(
    ("action", "mutation"),
    [
        (action, mutation)
        for action in _TASK3G_ACTIONS
        for mutation in (
            "wrong_event",
            "missing_snapshot",
            "malformed_snapshot",
        )
    ],
)
def test_task3g_receipt_integrity_is_enforced(
    session,
    actor_contributor,
    actor_admin,
    action,
    mutation,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import DemandListEventType

    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=(
            f"task3g-integrity-{action}-{mutation}"
        ),
    )
    key = (
        f"task3g-integrity-command-"
        f"{action}-{mutation}"
    )

    _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )
    receipt = _task3g_receipt(
        session,
        case["actor"],
        idempotency_key=key,
    )

    if mutation == "wrong_event":
        receipt.event_type = (
            DemandListEventType.CREATED
        )
    elif mutation == "missing_snapshot":
        receipt.response_snapshot_json = None
    else:
        receipt.response_snapshot_json = {
            "id": case["demand_list_id"],
        }
    session.commit()

    with pytest.raises(ConflictError) as captured:
        _task3g_invoke(
            session,
            case,
            idempotency_key=key,
        )

    assert captured.value.code == (
        "IDEMPOTENT_RESPONSE_UNAVAILABLE"
    )
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


@pytest.mark.parametrize(
    "action",
    _TASK3G_ACTIONS,
)
def test_task3g_same_hash_race_replays_after_rollback(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
    action,
) -> None:
    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=f"task3g-race-same-{action}",
    )
    key = f"task3g-race-same-command-{action}"
    (
        raced_receipt,
        _,
        state,
    ) = _task3g_install_lifecycle_race(
        session,
        case,
        monkeypatch,
        idempotency_key=key,
        winner_hash=None,
        winner_present=True,
    )

    replay = _task3g_invoke(
        session,
        case,
        idempotency_key=key,
    )

    assert state["lookups"] == 2
    assert state["order"][:3] == [
        "lookup-1",
        "rollback",
        "lookup-2",
    ]
    assert replay.model_dump(mode="json") == (
        raced_receipt.response_snapshot_json
    )

    _task3g_warning_list(replay).append(
        "TASK3G-RACE-MUTATION"
    )
    assert "TASK3G-RACE-MUTATION" not in (
        _task3g_snapshot_warning_list(
            raced_receipt.response_snapshot_json
        )
    )


@pytest.mark.parametrize(
    "action",
    _TASK3G_ACTIONS,
)
def test_task3g_different_hash_race_is_controlled(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
    action,
) -> None:
    from app.core.exceptions import ConflictError

    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=f"task3g-race-different-{action}",
    )
    key = (
        f"task3g-race-different-command-{action}"
    )
    _, _, state = _task3g_install_lifecycle_race(
        session,
        case,
        monkeypatch,
        idempotency_key=key,
        winner_hash="different-request-hash",
        winner_present=True,
    )

    with pytest.raises(ConflictError) as captured:
        _task3g_invoke(
            session,
            case,
            idempotency_key=key,
        )

    assert state["lookups"] == 2
    assert state["order"][:3] == [
        "lookup-1",
        "rollback",
        "lookup-2",
    ]
    assert captured.value.code == (
        "IDEMPOTENCY_KEY_REUSED"
    )
    assert captured.value.details == {
        "conflict_object": "demand_list",
        "retryable": False,
    }


@pytest.mark.parametrize(
    "action",
    _TASK3G_ACTIONS,
)
def test_task3g_no_winner_reraises_original_integrity_error(
    session,
    actor_contributor,
    actor_admin,
    monkeypatch,
    action,
) -> None:
    from sqlalchemy.exc import IntegrityError

    case = _task3g_build_action_case(
        session,
        actor_contributor,
        actor_admin,
        action=action,
        prefix=f"task3g-race-none-{action}",
    )
    key = f"task3g-race-none-command-{action}"
    (
        _,
        original_error,
        state,
    ) = _task3g_install_lifecycle_race(
        session,
        case,
        monkeypatch,
        idempotency_key=key,
        winner_hash=None,
        winner_present=False,
    )

    with pytest.raises(IntegrityError) as captured:
        _task3g_invoke(
            session,
            case,
            idempotency_key=key,
        )

    assert state["lookups"] == 2
    assert state["order"][:3] == [
        "lookup-1",
        "rollback",
        "lookup-2",
    ]
    assert captured.value is original_error


def test_task3g_shared_recovery_helper_contract() -> None:
    import inspect

    service = _demand_list_service()
    helper = getattr(
        type(service),
        "_recover_lifecycle_receipt",
    )
    assert list(
        inspect.signature(helper).parameters
    ) == [
        "self",
        "session",
        "actor",
        "idempotency_key",
        "request_hash",
        "expected_event_type",
        "original_error",
    ]


def test_task3g_all_mutation_handlers_use_shared_recovery() -> None:
    import inspect

    service_type = type(_demand_list_service())
    for method_name in (
        "create_from_group",
        "submit",
        "confirm",
        "publish",
        "derive",
        "void",
    ):
        source = inspect.getsource(
            getattr(service_type, method_name)
        )
        assert (
            "_recover_lifecycle_receipt(" in source
        ), method_name


# Task 3H: complete lifecycle proof and cross-module domain contract.


@pytest.mark.parametrize(
    ("action", "source_status", "expected_status"),
    [
        ("submit", "PENDING_CONFIRMATION", "DRAFT"),
        ("submit", "CONFIRMED", "DRAFT"),
        ("submit", "PUBLISHED", "DRAFT"),
        ("submit", "VOIDED", "DRAFT"),
        (
            "confirm",
            "DRAFT",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "CONFIRMED",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "PUBLISHED",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "VOIDED",
            "PENDING_CONFIRMATION",
        ),
        ("publish", "DRAFT", "CONFIRMED"),
        (
            "publish",
            "PENDING_CONFIRMATION",
            "CONFIRMED",
        ),
        ("publish", "PUBLISHED", "CONFIRMED"),
        ("publish", "VOIDED", "CONFIRMED"),
        ("derive", "DRAFT", "PUBLISHED"),
        (
            "derive",
            "PENDING_CONFIRMATION",
            "PUBLISHED",
        ),
        ("derive", "CONFIRMED", "PUBLISHED"),
        ("derive", "VOIDED", "PUBLISHED"),
        ("void", "DRAFT", "PUBLISHED"),
        (
            "void",
            "PENDING_CONFIRMATION",
            "PUBLISHED",
        ),
        ("void", "CONFIRMED", "PUBLISHED"),
        ("void", "VOIDED", "PUBLISHED"),
    ],
)
def test_task3h_invalid_transition_matrix(
    session,
    actor_contributor,
    actor_admin,
    action,
    source_status,
    expected_status,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key=(
            f"task3h-matrix-source-"
            f"{action}-{source_status}"
        ),
    )
    row = _task3_persisted_list(
        session,
        created.id,
    )
    row.status = DemandListStatus(source_status)
    row.is_current = (
        row.status is DemandListStatus.PUBLISHED
    )
    session.commit()

    kwargs = {
        "expected_version": created.version,
        "idempotency_key": (
            f"task3h-matrix-command-"
            f"{action}-{source_status}"
        ),
    }
    if action == "confirm":
        kwargs["confirmation_note"] = (
            "Matrix confirmation"
        )

    with pytest.raises(ConflictError) as captured:
        getattr(service, action)(
            session,
            actor_admin,
            created.id,
            **kwargs,
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": action,
        "expected_status": expected_status,
        "actual_status": source_status,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3h_complete_lifecycle_preserves_lineage_and_history(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from copy import deepcopy

    from app.models import DemandList, DemandListEvent
    from app.models.enums import DemandListStatus
    from app.schemas.demand_list import DemandListRead

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3h-create",
    )
    high = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )
    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        high.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Lifecycle risk change",
    )
    pending_v1 = service.submit(
        session,
        actor_contributor,
        updated.id,
        expected_version=updated.version,
        idempotency_key="task3h-submit-v1",
    )
    confirmed_v1 = service.confirm(
        session,
        actor_admin,
        pending_v1.id,
        expected_version=pending_v1.version,
        confirmation_note="Approve version 1",
        idempotency_key="task3h-confirm-v1",
    )
    assert confirmed_v1.status.value == "CONFIRMED"

    published_v1 = service.publish(
        session,
        actor_admin,
        confirmed_v1.id,
        expected_version=confirmed_v1.version,
        idempotency_key="task3h-publish-v1",
    )
    assert published_v1.status.value == "PUBLISHED"
    assert published_v1.is_current is True
    assert published_v1.version_number == 1

    high_v1 = next(
        item
        for item in published_v1.items
        if item.id == high.id
    )
    assert high_v1.requires_admin_confirmation is True
    assert high_v1.confirmed_by_admin is True

    v1_interval_before = (
        high_v1.interval_snapshot_json
    )
    assert v1_interval_before is not None
    v1_interval_before = deepcopy(v1_interval_before)

    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3h-derive-v2",
    )

    assert derived_v2.id != published_v1.id
    assert derived_v2.lineage_id == published_v1.lineage_id
    assert derived_v2.version_number == 2
    assert derived_v2.status.value == "DRAFT"
    assert derived_v2.is_current is False
    assert derived_v2.derived_from_id == published_v1.id
    assert any(
        item.confirmed_by_admin
        for item in derived_v2.items
        if item.requires_admin_confirmation
    )

    derived_interval = (
        derived_v2.items[0].interval_snapshot_json
    )
    assert derived_interval is not None
    derived_interval["candidates"][0][
        "warnings"
    ].append("TASK3H-V2-READ-MUTATION")

    reloaded_v1_before_publish = service.get(
        session,
        actor_admin,
        published_v1.id,
    )
    reloaded_high_v1 = next(
        item
        for item in reloaded_v1_before_publish.items
        if item.id == high.id
    )
    assert (
        reloaded_high_v1.interval_snapshot_json
        == v1_interval_before
    )
    assert reloaded_v1_before_publish.is_current is True

    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3h-submit-v2",
    )
    assert pending_v2.status.value == (
        "PENDING_CONFIRMATION"
    )

    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3h-confirm-v2",
    )
    assert confirmed_v2.status.value == "CONFIRMED"
    assert confirmed_v2.id == derived_v2.id

    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3h-publish-v2",
    )

    reloaded_v1 = service.get(
        session,
        actor_admin,
        published_v1.id,
    )
    assert reloaded_v1.status.value == "PUBLISHED"
    assert reloaded_v1.is_current is False
    assert reloaded_v1.superseded_by_id == published_v2.id
    assert published_v2.is_current is True
    assert published_v2.version_number == 2

    voided_v2 = service.void(
        session,
        actor_admin,
        published_v2.id,
        expected_version=published_v2.version,
        idempotency_key="task3h-void-v2",
    )
    assert voided_v2.status.value == "VOIDED"
    assert voided_v2.is_current is False

    current_count = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v1.lineage_id,
            DemandList.status
            == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .count()
    )
    assert current_count == 0

    assert [
        event.event_type.value
        for event in voided_v2.events
    ] == [
        "DERIVED",
        "SUBMITTED",
        "CONFIRMED",
        "PUBLISHED",
        "VOIDED",
    ]

    lineage_rows = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v1.lineage_id,
        )
        .order_by(DemandList.version_number)
        .all()
    )
    assert [
        row.id
        for row in lineage_rows
    ] == [
        published_v1.id,
        published_v2.id,
    ]
    assert [
        row.version_number
        for row in lineage_rows
    ] == [1, 2]

    lineage_ids = [
        row.id
        for row in lineage_rows
    ]
    lineage_events = (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.tenant_id
            == actor_contributor.tenant_id,
            DemandListEvent.demand_list_id.in_(
                lineage_ids
            ),
        )
        .order_by(
            DemandListEvent.occurred_at,
            DemandListEvent.id,
        )
        .all()
    )

    contributor_event_types = {
        "CREATED",
        "ITEM_UPDATED",
        "SUBMITTED",
    }
    admin_event_types = {
        "CONFIRMED",
        "PUBLISHED",
        "DERIVED",
        "VOIDED",
    }
    for event in lineage_events:
        event_type = event.event_type.value
        if event_type in contributor_event_types:
            expected_actor = actor_contributor
        elif event_type in admin_event_types:
            expected_actor = actor_admin
        else:
            raise AssertionError(
                f"unexpected lifecycle event: {event_type}"
            )
        assert event.actor_user_id == (
            expected_actor.user_id
        )
        assert event.request_id == (
            expected_actor.request_id
        )

    keyed_events = [
        event
        for event in lineage_events
        if event.idempotency_key is not None
    ]
    keys = [
        event.idempotency_key
        for event in keyed_events
    ]
    assert len(keys) == len(set(keys))
    assert set(keys) == {
        "task3h-create",
        "task3h-submit-v1",
        "task3h-confirm-v1",
        "task3h-publish-v1",
        "task3h-derive-v2",
        "task3h-submit-v2",
        "task3h-confirm-v2",
        "task3h-publish-v2",
        "task3h-void-v2",
    }

    for event in keyed_events:
        assert event.response_snapshot_json is not None
        validated = DemandListRead.model_validate(
            event.response_snapshot_json
        )
        assert validated.id == event.demand_list_id


def test_task3h_operational_eligibility_is_only_current_published(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3h-eligibility-source",
        submit_key="task3h-eligibility-submit",
        confirm_key="task3h-eligibility-confirm",
    )
    assert not (
        confirmed.status.value == "PUBLISHED"
        and confirmed.is_current
    )

    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=(
            "task3h-eligibility-publish"
        ),
    )
    assert (
        published.status.value == "PUBLISHED"
        and published.is_current
    )

    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key=(
            "task3h-eligibility-derive"
        ),
    )
    assert not (
        derived.status.value == "PUBLISHED"
        and derived.is_current
    )

    voided = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key=(
            "task3h-eligibility-void"
        ),
    )
    assert not (
        voided.status.value == "PUBLISHED"
        and voided.is_current
    )
