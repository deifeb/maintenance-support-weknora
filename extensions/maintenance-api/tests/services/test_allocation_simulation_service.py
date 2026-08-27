from __future__ import annotations

import importlib
from copy import deepcopy
from decimal import Decimal

import pytest
from app.models import (
    AllocationRuleVersion,
    AllocationSimulation,
    AllocationSimulationResult,
    CalculationGroup,
    DemandList,
    DemandListItem,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryReservation,
    InventoryReservationLine,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import DemandListStatus
from sqlalchemy import select

FEATURE_MISSING = "PLAN05_4D_TASK3_FEATURE_MISSING"


def _service_api():
    name = "app.services.allocation_simulation_service"
    if importlib.util.find_spec(name) is None:
        pytest.fail(
            f"{FEATURE_MISSING}: missing Task 3 module: {name}",
            pytrace=False,
        )
    module = importlib.import_module(name)
    missing = [
        attr
        for attr in ("AllocationSimulationService",)
        if not hasattr(module, attr)
    ]
    if missing:
        pytest.fail(
            f"{FEATURE_MISSING}: missing service API: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _seed_context(session, *, tenant_id: str = "tenant-a"):
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"scenario-{tenant_id}",
        name=f"Scenario {tenant_id}",
    )
    session.add(template)
    session.flush()

    scenario = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code="v1",
        version_name="Version 1",
    )
    session.add(scenario)
    session.flush()

    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=scenario.id,
        primary_candidate_key="primary",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id="seed-user",
        created_by_request_id="seed-request",
    )
    session.add(group)
    session.flush()

    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{tenant_id}",
        name=f"Spare {tenant_id}",
        unit="EA",
        is_critical=True,
    )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{tenant_id}",
        name=f"Warehouse {tenant_id}",
    )
    session.add_all([spare, warehouse])
    session.flush()

    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code="PICK-01",
        name="Pick 01",
        location_type="PICK",
        is_pickable=True,
        is_active=True,
    )
    session.add(location)
    session.flush()

    demand_list = DemandList(
        tenant_id=tenant_id,
        name="Current published demand",
        lineage_id=f"demand-{tenant_id}",
        version_number=1,
        scenario_version_id=scenario.id,
        calculation_group_id=group.id,
        status=DemandListStatus.PUBLISHED,
        is_current=True,
        created_by_user_id="seed-user",
        created_by_request_id="seed-request",
    )
    session.add(demand_list)
    session.flush()

    item = DemandListItem(
        tenant_id=tenant_id,
        demand_list_id=demand_list.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
        criticality_level_snapshot="CRITICAL",
        original_quantity=Decimal("5.000000"),
        final_quantity=Decimal("5.000000"),
        source_snapshot_json={"seed": True},
    )
    session.add(item)

    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=spare.id,
        lot_id=None,
        on_hand_quantity=Decimal("10.0000"),
        reserved_quantity=Decimal("2.0000"),
        damaged_quantity=Decimal("1.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("3.0000"),
        version=1,
    )
    session.add(balance)
    session.flush()

    common_rule = dict(
        tenant_id=tenant_id,
        lineage_id=f"rule-{tenant_id}",
        scope_json={"warehouse_ids": [warehouse.id]},
        hard_rules_json={
            "exclude_frozen": True,
            "exclude_expired": True,
            "require_available": True,
        },
        weights_json={"availability": "1.000000"},
        normalization_json={"availability": {"min": "0", "max": "10"}},
        effective_from=None,
        effective_to=None,
        change_reason="Task 3 simulation seed",
        version=1,
    )
    baseline = AllocationRuleVersion(
        **common_rule,
        version_number=1,
        status="PUBLISHED",
    )
    candidate = AllocationRuleVersion(
        **common_rule,
        version_number=2,
        status="DRAFT",
    )
    session.add_all([baseline, candidate])
    session.flush()

    return {
        "candidate": candidate,
        "baseline": baseline,
        "demand_list": demand_list,
        "item": item,
        "balance": balance,
        "warehouse": warehouse,
    }


def _submit(service, session, actor, context, *, key: str):
    return service.submit(
        session,
        actor,
        candidate_rule_id=context["candidate"].id,
        baseline_rule_id=context["baseline"].id,
        source_demand_list_id=context["demand_list"].id,
        sample_ref="task3-red-sample",
        idempotency_key=key,
    )


def _row_snapshot(row) -> dict[str, object]:
    return {
        column.name: deepcopy(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _inventory_facts(session, tenant_id: str) -> dict[str, list[dict[str, object]]]:
    models = (
        InventoryBalance,
        InventoryTransaction,
        InventoryLedgerEntry,
        InventoryReservation,
        InventoryReservationLine,
    )
    facts: dict[str, list[dict[str, object]]] = {}
    for model in models:
        rows = list(
            session.scalars(
                select(model)
                .where(model.tenant_id == tenant_id)
                .order_by(model.id.asc())
            ).all()
        )
        facts[model.__tablename__] = [_row_snapshot(row) for row in rows]
    return facts


def test_submit_persists_pending_and_freezes_inputs(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()

    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-submit-1",
    )
    session.flush()

    assert simulation.status == "PENDING"
    assert simulation.tenant_id == actor_contributor.tenant_id
    assert simulation.input_snapshot_json
    assert len(simulation.inventory_fingerprint) == 64
    assert simulation.started_at is None
    assert simulation.completed_at is None

    frozen = deepcopy(simulation.input_snapshot_json)
    fingerprint = simulation.inventory_fingerprint
    context["item"].final_quantity = Decimal("9.000000")
    context["balance"].on_hand_quantity = Decimal("11.0000")
    session.flush()
    session.refresh(simulation)

    assert simulation.input_snapshot_json == frozen
    assert simulation.inventory_fingerprint == fingerprint


def test_submit_replays_same_idempotency_key(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()

    first = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-idempotent-1",
    )
    replay = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-idempotent-1",
    )

    assert replay.id == first.id
    assert (
        session.query(AllocationSimulation)
        .filter_by(
            tenant_id=actor_contributor.tenant_id,
            idempotency_key="task3-idempotent-1",
        )
        .count()
        == 1
    )


def test_claim_is_atomic_and_repeat_claim_is_noop(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-claim-1",
    )

    claimed = service.claim(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    duplicate = service.claim(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )

    assert claimed is not None
    assert claimed.status == "RUNNING"
    assert claimed.started_at is not None
    assert duplicate is None


def test_run_claimed_persists_baseline_and_candidate_results(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-results-1",
    )
    assert service.claim(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )

    completed = service.run_claimed(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    results = list(
        session.scalars(
            select(AllocationSimulationResult)
            .where(
                AllocationSimulationResult.tenant_id
                == actor_contributor.tenant_id,
                AllocationSimulationResult.simulation_id
                == simulation.id,
            )
            .order_by(AllocationSimulationResult.id.asc())
        ).all()
    )

    assert completed.status == "COMPLETED"
    assert completed.completed_at is not None
    assert results
    assert {result.demand_list_item_id for result in results} == {
        context["item"].id
    }
    assert any(result.candidate_rank is not None for result in results)
    assert any(result.candidate_score is not None for result in results)
    assert all(
        result.score_delta
        == (
            result.candidate_score - result.baseline_score
            if (
                result.candidate_score is not None
                and result.baseline_score is not None
            )
            else result.score_delta
        )
        for result in results
    )


def test_run_claimed_has_zero_inventory_side_effects(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-side-effect-1",
    )
    before = _inventory_facts(
        session,
        actor_contributor.tenant_id,
    )
    start_fingerprint = simulation.inventory_fingerprint

    assert service.claim(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    completed = service.run_claimed(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    session.flush()
    after = _inventory_facts(
        session,
        actor_contributor.tenant_id,
    )

    assert completed.status == "COMPLETED"
    assert completed.inventory_fingerprint == start_fingerprint
    assert after == before


def test_fail_safely_marks_failed_and_sanitizes_error(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-failure-1",
    )
    session.commit()

    service.fail_safely(
        actor_contributor.tenant_id,
        simulation.id,
        RuntimeError("password=super-secret\ninternal traceback details"),
    )

    session.expire_all()
    failed = session.get(AllocationSimulation, simulation.id)
    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.completed_at is not None
    assert failed.error_code == "ALLOCATION_SIMULATION_FAILED"
    assert failed.error_summary
    assert "super-secret" not in failed.error_summary
    assert "\n" not in failed.error_summary
    assert len(failed.error_summary) <= 500


def test_cancel_marks_pending_simulation_cancelled(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-cancel-1",
    )

    cancelled = service.cancel(
        session,
        actor_contributor,
        simulation.id,
        expected_version=simulation.version,
    )

    assert cancelled.status == "CANCELLED"
    assert cancelled.completed_at is not None


def test_latest_for_rule_is_tenant_scoped_and_returns_newest(
    session,
    actor_contributor,
    actor_context,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    other = _seed_context(session, tenant_id="tenant-b")
    service = service_api.AllocationSimulationService()

    first = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-latest-1",
    )
    second = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task3-latest-2",
    )
    other_actor = actor_context(tenant_id="tenant-b")
    _submit(
        service,
        session,
        other_actor,
        other,
        key="task3-latest-other",
    )

    latest = service.latest_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )

    assert first.id < second.id
    assert latest is not None
    assert latest.id == second.id
    assert latest.tenant_id == actor_contributor.tenant_id

# PLAN05_4D_TASK6_RED_CONTRACTS
TASK6_FEATURE_MISSING = "PLAN05_4D_TASK6_FEATURE_MISSING"


def _task6_simulation_schema_api():
    schema_api = importlib.import_module("app.schemas.allocation")
    required = (
        "AllocationSimulationSubmitCommand",
        "AllocationSimulationProgressRead",
        "AllocationSimulationResultsSummaryRead",
        "AllocationSimulationSummaryRead",
    )
    missing = [name for name in required if not hasattr(schema_api, name)]
    if missing:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: missing simulation API schema: "
            f"{', '.join(missing)}",
            pytrace=False,
        )
    return schema_api


def test_task6_simulation_submit_guards_expected_rule_version(
    session,
    actor_contributor,
) -> None:
    from inspect import signature

    from app.core.exceptions import AppException

    service_api = _service_api()
    schema_api = _task6_simulation_schema_api()
    service = service_api.AllocationSimulationService()
    if "expected_rule_version" not in signature(service.submit).parameters:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: AllocationSimulationService.submit "
            "must accept expected_rule_version",
            pytrace=False,
        )

    context = _seed_context(session)
    command = schema_api.AllocationSimulationSubmitCommand(
        expected_rule_version=context["candidate"].version + 1,
        baseline_rule_id=context["baseline"].id,
        source_demand_list_id=context["demand_list"].id,
        sample_ref="task6-version-conflict",
    )
    with pytest.raises(AppException) as raised:
        service.submit(
            session,
            actor_contributor,
            candidate_rule_id=context["candidate"].id,
            baseline_rule_id=command.baseline_rule_id,
            source_demand_list_id=command.source_demand_list_id,
            sample_ref=command.sample_ref,
            expected_rule_version=command.expected_rule_version,
            idempotency_key="task6-simulation-version",
        )
    assert raised.value.code == "ALLOCATION_RULE_VERSION_CONFLICT"
    assert raised.value.details["expected_version"] == command.expected_rule_version
    assert raised.value.details["actual_version"] == context["candidate"].version


# PLAN05_4D_TASK6_GREEN_B_TEST_CONTRACT
def test_task6_simulation_summary_schema_exposes_indeterminate_running_progress(
    session,
    actor_contributor,
) -> None:
    service_api = _service_api()
    context = _seed_context(session)
    service = service_api.AllocationSimulationService()
    simulation = _submit(
        service,
        session,
        actor_contributor,
        context,
        key="task6-progress-summary",
    )

    pending = service.latest_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )
    if (
        pending is None
        or not hasattr(pending, "progress")
        or not hasattr(pending, "results_summary")
        or not hasattr(service, "latest_read_for_rule")
    ):
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: latest simulation public progress/"
            "result summary support missing",
            pytrace=False,
        )
    assert pending.progress.phase == "QUEUED"
    assert pending.progress.percent == 0
    assert pending.results_summary.total_rows == 0
    assert pending.results_summary.demand_item_count == 0

    public_pending = service.latest_read_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )
    assert public_pending is not None
    assert public_pending.progress.phase == "QUEUED"
    assert public_pending.progress.percent == 0

    claimed = service.claim(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    assert claimed is not None
    running_summary = service.latest_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )
    assert running_summary is not None
    assert running_summary.progress.phase == "RUNNING"
    assert running_summary.progress.percent is None

    completed = service.run_claimed(
        session,
        actor_contributor.tenant_id,
        simulation.id,
    )
    assert completed.status == "COMPLETED"
    terminal_summary = service.latest_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )
    assert terminal_summary is not None
    assert terminal_summary.progress.phase == "TERMINAL"
    assert terminal_summary.progress.percent == 100
    assert terminal_summary.results_summary.total_rows >= 1
    assert terminal_summary.results_summary.demand_item_count == 1
    assert (
        terminal_summary.results_summary.high_priority_regression
        == terminal_summary.high_priority_regression
    )

    public_terminal = service.latest_read_for_rule(
        session,
        actor_contributor.tenant_id,
        context["candidate"].id,
    )
    assert public_terminal is not None
    assert public_terminal.status == "COMPLETED"
    assert public_terminal.version == terminal_summary.version
    assert public_terminal.progress.phase == "TERMINAL"
    assert public_terminal.results_summary == terminal_summary.results_summary

    schema_api = _task6_simulation_schema_api()

    submit_fields = set(schema_api.AllocationSimulationSubmitCommand.model_fields)
    assert {
        "expected_rule_version",
        "baseline_rule_id",
        "source_demand_list_id",
        "sample_ref",
    } <= submit_fields

    progress_fields = set(schema_api.AllocationSimulationProgressRead.model_fields)
    assert progress_fields == {"phase", "percent"}
    queued = schema_api.AllocationSimulationProgressRead(
        phase="QUEUED",
        percent=0,
    )
    running = schema_api.AllocationSimulationProgressRead(
        phase="RUNNING",
        percent=None,
    )
    terminal = schema_api.AllocationSimulationProgressRead(
        phase="TERMINAL",
        percent=100,
    )
    assert queued.percent == 0
    assert running.percent is None
    assert terminal.percent == 100

    result_fields = set(
        schema_api.AllocationSimulationResultsSummaryRead.model_fields
    )
    assert {
        "total_rows",
        "demand_item_count",
        "high_priority_regression",
    } <= result_fields
    summary_fields = set(schema_api.AllocationSimulationSummaryRead.model_fields)
    assert {
        "id",
        "status",
        "version",
        "progress",
        "blockers",
        "results_summary",
        "completed_at",
        "error_code",
        "error_summary",
    } <= summary_fields
