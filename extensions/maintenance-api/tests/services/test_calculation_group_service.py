from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import Any

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
)
from app.models import (
    DemandCalculationRun,
    DemandRunItemResult,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    CalculationStatus,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    ReliabilityModelType,
    ScenarioVersionStatus,
    ShortageRiskLevel,
)
from app.security.actor import ActorContext
from app.services.calculation_group_service import (
    CalculationGroupService,
)
from app.services.demand_calculation_service import (
    CandidateExecutionSpec,
)
from sqlalchemy.orm import Session


def add_version(
    session: Session,
    tenant_id: str,
    *,
    status: ScenarioVersionStatus = ScenarioVersionStatus.PUBLISHED,
) -> DemandScenarioVersion:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"GROUP-{tenant_id}-{status.value}",
        name="Calculation group scenario",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=status,
    )
    session.add(version)
    session.flush()
    return version


def compatible_snapshot() -> dict[str, Any]:
    return {
        "stages": [
            {
                "code": "S1",
                "duration_hours": "24",
            }
        ],
        "simulation": {"max_runs": 50000},
        "items": [
            {
                "installed_positions": "10",
                "reliability": {
                    "model_type": "WEIBULL",
                    "failure_rate": "0.001",
                    "weibull_shape": "1.8",
                    "weibull_scale": "1000",
                    "binomial_trials": 10,
                    "binomial_probability": "0.1",
                    "negative_binomial_r": "2",
                    "negative_binomial_p": "0.5",
                    "empirical_mean": "3",
                    "empirical_variance": "4",
                },
                "age_groups": [
                    {
                        "distribution_type": "FIXED",
                        "fixed_hours": "100",
                    }
                ],
                "common_shocks": [],
            }
        ],
    }


def service_with_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[str, Any] | None = None,
) -> CalculationGroupService:
    service = CalculationGroupService()
    trusted_snapshot = snapshot or compatible_snapshot()
    monkeypatch.setattr(
        service.calculation_service,
        "build_snapshot",
        lambda *args, **kwargs: (trusted_snapshot, []),
    )
    return service


def add_item_result(
    session: Session,
    child,
    spare: SparePart,
    *,
    quantity: str,
    criticality: str = "MEDIUM",
    warnings: list[str] | None = None,
) -> DemandRunItemResult:
    child.calculation.status = CalculationStatus.SUCCEEDED
    run = DemandCalculationRun(
        tenant_id=child.tenant_id,
        calculation_id=child.calculation_id,
        run_mode=child.execution_mode,
        status=CalculationStatus.SUCCEEDED,
        progress_percent=Decimal("100"),
        engine_version="comparison-test",
        formula_version="comparison-test",
        converged=True,
    )
    session.add(run)
    session.flush()
    recommended = Decimal(quantity)
    result = DemandRunItemResult(
        tenant_id=child.tenant_id,
        calculation_run_id=run.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        criticality_level=criticality,
        calculation_status=ItemCalculationStatus.CALCULATED,
        selected_model_type=child.reliability_model,
        failure_process_mode=FailureProcessMode.AUTO,
        target_service_level=Decimal("0.95"),
        expected_demand=recommended,
        variance=Decimal("1"),
        standard_deviation=Decimal("1"),
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
        available_quantity=Decimal("10"),
        usable_inventory=Decimal("10"),
        net_demand_gap=recommended - Decimal("10"),
        inventory_coverage_rate=Decimal("0.1"),
        shortage_risk_level=ShortageRiskLevel.HIGH,
        warning_codes_json=warnings,
    )
    session.add(result)
    session.flush()
    return result


def completed_comparison_group(
    session: Session,
    actor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
):
    version = add_version(session, actor.tenant_id)
    service = service_with_snapshot(monkeypatch)
    group = service.create(
        session,
        actor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "BINOMIAL:ANALYTICAL",
        ],
        idempotency_key="comparison-group",
    )
    spare_a = SparePart(
        tenant_id=actor.tenant_id,
        code="SP-COMP-A",
        name="Comparison spare A",
        unit="piece",
    )
    spare_b = SparePart(
        tenant_id=actor.tenant_id,
        code="SP-COMP-B",
        name="Comparison spare B",
        unit="piece",
    )
    session.add_all([spare_a, spare_b])
    session.flush()
    primary, alternative = group.current_children
    add_item_result(
        session,
        primary,
        spare_a,
        quantity="100",
        criticality="HIGH",
    )
    add_item_result(
        session,
        alternative,
        spare_b,
        quantity="55",
    )
    session.commit()
    service.refresh_status(session, actor, group.id)
    return service, group, spare_a, spare_b


def test_candidate_execution_spec_is_immutable() -> None:
    spec = CandidateExecutionSpec(
        candidate_key="WEIBULL:ANALYTICAL",
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        random_seed=20260723,
    )

    with pytest.raises(FrozenInstanceError):
        spec.random_seed = 1  # type: ignore[misc]


def test_comparison_uses_union_and_marks_missing_results(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, group, spare_a, spare_b = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )

    comparison = service.comparison(
        session,
        actor_contributor,
        group.id,
    )
    by_id = {
        row.spare_part_id: row
        for row in comparison.rows
    }

    assert set(by_id) == {spare_a.id, spare_b.id}
    assert (
        by_id[spare_a.id]
        .candidates["WEIBULL:ANALYTICAL"]
        .status
        == "SUCCEEDED"
    )
    assert (
        by_id[spare_a.id]
        .candidates["BINOMIAL:ANALYTICAL"]
        .status
        == "NO_RESULT"
    )


def test_comparison_requires_terminal_group(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, group, _, _ = completed_comparison_group(
        session,
        actor_contributor,
        monkeypatch,
    )
    group.status = CalculationGroupStatus.RUNNING
    session.commit()

    with pytest.raises(ConflictError) as exc:
        service.comparison(
            session,
            actor_contributor,
            group.id,
        )

    assert (
        exc.value.code
        == "CALCULATION_GROUP_NOT_TERMINAL"
    )


def test_high_risk_manual_reduction_requires_admin_confirmation(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    primary = group.current_children[0]

    decision = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=primary.id,
        final_quantity=Decimal("80"),
        reason="Accepted lower operational target",
    )

    assert decision.requires_admin_confirmation is True
    assert decision.risk == "HIGH"
    assert (
        decision.risk_rule_version
        == "DEMAND-DECISION-RISK-1"
    )
    assert decision.version == 1
    events = service.events(
        session,
        actor_contributor,
        group.id,
        after_sequence=0,
    )
    assert events[-1].event_type == "decision.updated"
    assert events[-1].payload_json["decision_version"] == 1


def test_decision_rejects_stale_version_and_missing_reason(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    primary = group.current_children[0]

    with pytest.raises(BusinessValidationError):
        service.save_decision(
            session,
            actor_contributor,
            group.id,
            spare_part_id=spare_a.id,
            expected_version=0,
            selected_child_id=primary.id,
            final_quantity=Decimal("80"),
            reason="",
        )

    created = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=primary.id,
        final_quantity=Decimal("100"),
        reason=None,
    )
    with pytest.raises(ConflictError) as exc:
        service.save_decision(
            session,
            actor_contributor,
            group.id,
            spare_part_id=spare_a.id,
            expected_version=0,
            selected_child_id=primary.id,
            final_quantity=Decimal("100"),
            reason=None,
        )
    assert created.version == 1
    assert (
        exc.value.code
        == "CALCULATION_DECISION_VERSION_CONFLICT"
    )


def test_group_creates_one_calculation_per_selected_candidate(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)

    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="group-create-1",
    )

    assert len(group.current_children) == 3
    assert len(
        {
            child.calculation_id
            for child in group.current_children
        }
    ) == 3
    assert all(
        child.attempt_number == 1
        for child in group.current_children
    )
    assert {
        child.calculation.requested_mode
        for child in group.current_children
    } == {
        DemandExecutionMode.ANALYTICAL,
        DemandExecutionMode.MONTE_CARLO,
    }
    assert group.last_event_sequence == 4


def test_candidate_submission_overrides_only_trusted_model_field(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)

    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="EXPONENTIAL:ANALYTICAL",
        selected_candidate_keys=[
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="trusted-candidate",
    )

    calculation = group.current_children[0].calculation
    snapshot = calculation.input_snapshot_json
    assert snapshot["candidate_key"] == (
        "EXPONENTIAL:ANALYTICAL"
    )
    assert snapshot["items"][0]["reliability"]["model_type"] == (
        "EXPONENTIAL"
    )
    assert snapshot["items"][0]["reliability"][
        "failure_rate"
    ] == "0.001"
    assert snapshot["random_seed"] == 20260723


def test_group_rejects_unpublished_scenario(
    session: Session,
    actor_contributor: ActorContext,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
        status=ScenarioVersionStatus.DRAFT,
    )

    with pytest.raises(ConflictError) as exc:
        CalculationGroupService().create(
            session,
            actor_contributor,
            scenario_version_id=version.id,
            primary_candidate_key="WEIBULL:ANALYTICAL",
            selected_candidate_keys=[
                "WEIBULL:ANALYTICAL",
            ],
            idempotency_key="unpublished",
        )

    assert exc.value.code == "SCENARIO_NOT_PUBLISHED"


def test_group_creation_is_idempotent_and_detects_key_reuse(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)
    request = {
        "scenario_version_id": version.id,
        "primary_candidate_key": "WEIBULL:ANALYTICAL",
        "selected_candidate_keys": [
            "WEIBULL:ANALYTICAL",
        ],
        "idempotency_key": "same-key",
    }

    first = service.create(
        session,
        actor_contributor,
        **request,
    )
    replay = service.create(
        session,
        actor_contributor,
        **request,
    )

    assert replay.id == first.id
    with pytest.raises(ConflictError) as exc:
        service.create(
            session,
            actor_contributor,
            **{
                **request,
                "selected_candidate_keys": [
                    "WEIBULL:ANALYTICAL",
                    "WEIBULL:MONTE_CARLO",
                ],
            },
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_group_rejects_inapplicable_candidate(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    snapshot = compatible_snapshot()
    snapshot["items"][0]["reliability"].pop("failure_rate")
    service = service_with_snapshot(monkeypatch, snapshot)

    with pytest.raises(BusinessValidationError) as exc:
        service.create(
            session,
            actor_contributor,
            scenario_version_id=version.id,
            primary_candidate_key="EXPONENTIAL:ANALYTICAL",
            selected_candidate_keys=[
                "EXPONENTIAL:ANALYTICAL",
            ],
            idempotency_key="inapplicable",
        )

    assert exc.value.code == "CANDIDATE_NOT_APPLICABLE"


def test_one_child_failure_preserves_successful_sibling(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
        ],
        idempotency_key="mixed-result",
    )
    group.child(
        "WEIBULL:ANALYTICAL"
    ).calculation.status = CalculationStatus.SUCCEEDED
    group.child(
        "WEIBULL:MONTE_CARLO"
    ).calculation.status = CalculationStatus.FAILED
    session.commit()

    refreshed = service.refresh_status(
        session,
        actor_contributor,
        group.id,
    )

    assert (
        refreshed.status
        is CalculationGroupStatus.PARTIALLY_COMPLETED
    )
    assert (
        refreshed.child(
            "WEIBULL:ANALYTICAL"
        ).calculation.status
        is CalculationStatus.SUCCEEDED
    )
    assert (
        refreshed.child(
            "WEIBULL:MONTE_CARLO"
        ).calculation.status
        is CalculationStatus.FAILED
    )


def test_retry_failed_creates_only_new_failed_attempt(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
        ],
        idempotency_key="retry-source",
    )
    group.child(
        "WEIBULL:ANALYTICAL"
    ).calculation.status = CalculationStatus.SUCCEEDED
    group.child(
        "WEIBULL:MONTE_CARLO"
    ).calculation.status = CalculationStatus.FAILED
    session.commit()

    retried = service.retry_failed(
        session,
        actor_contributor,
        group.id,
        idempotency_key="retry-mixed-1",
    )

    assert retried.child(
        "WEIBULL:ANALYTICAL"
    ).attempt_number == 1
    assert retried.child(
        "WEIBULL:MONTE_CARLO"
    ).attempt_number == 2
    assert (
        retried.child(
            "WEIBULL:MONTE_CARLO"
        ).calculation.status
        is CalculationStatus.PENDING
    )
    replay = service.retry_failed(
        session,
        actor_contributor,
        group.id,
        idempotency_key="retry-mixed-1",
    )
    assert replay.child(
        "WEIBULL:MONTE_CARLO"
    ).attempt_number == 2


def test_cancel_running_is_idempotent(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service = service_with_snapshot(monkeypatch)
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
        ],
        idempotency_key="cancel-source",
    )

    cancelled = service.cancel_running(
        session,
        actor_contributor,
        group.id,
        idempotency_key="cancel-1",
    )
    replay = service.cancel_running(
        session,
        actor_contributor,
        group.id,
        idempotency_key="cancel-1",
    )

    assert cancelled.status is CalculationGroupStatus.CANCELLED
    assert replay.id == cancelled.id
    assert (
        replay.current_children[0].calculation.status
        is CalculationStatus.CANCELLED
    )
# Task 2I: shared decision-risk policy integration coverage.


def _task2i_add_result_to_current_run(
    session: Session,
    child,
    spare: SparePart,
    *,
    quantity: str,
    warnings: list[str] | None = None,
) -> DemandRunItemResult:
    from sqlalchemy import select

    run = session.scalar(
        select(DemandCalculationRun).where(
            DemandCalculationRun.tenant_id
            == child.tenant_id,
            DemandCalculationRun.calculation_id
            == child.calculation_id,
            DemandCalculationRun.status
            == CalculationStatus.SUCCEEDED,
        )
    )
    assert run is not None

    recommended = Decimal(quantity)
    result = DemandRunItemResult(
        tenant_id=child.tenant_id,
        calculation_run_id=run.id,
        spare_part_id=spare.id,
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        criticality_level="MEDIUM",
        calculation_status=(
            ItemCalculationStatus.CALCULATED
        ),
        selected_model_type=child.reliability_model,
        failure_process_mode=FailureProcessMode.AUTO,
        target_service_level=Decimal("0.95"),
        expected_demand=recommended,
        variance=Decimal("1"),
        standard_deviation=Decimal("1"),
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
        available_quantity=Decimal("10"),
        usable_inventory=Decimal("10"),
        net_demand_gap=recommended - Decimal("10"),
        inventory_coverage_rate=Decimal("0.1"),
        shortage_risk_level=ShortageRiskLevel.HIGH,
        warning_codes_json=warnings,
    )
    session.add(result)
    session.commit()
    return result


def test_task2i_policy_integration_default_system_recommendation(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.enums import CalculationDecisionType

    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    primary, alternative = group.current_children
    _task2i_add_result_to_current_run(
        session,
        alternative,
        spare_a,
        quantity="120",
    )

    decision = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=primary.id,
        final_quantity=Decimal("100"),
        reason=None,
    )

    assert decision.decision_type == (
        CalculationDecisionType.SYSTEM_RECOMMENDATION
    )
    assert decision.risk == "LOW"
    assert (
        decision.requires_admin_confirmation
        is False
    )
    assert (
        decision.risk_rule_version
        == service.DECISION_RISK_RULE_VERSION
    )


def test_task2i_policy_integration_alternative_candidate(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.enums import CalculationDecisionType

    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    _, alternative = group.current_children
    _task2i_add_result_to_current_run(
        session,
        alternative,
        spare_a,
        quantity="120",
    )

    decision = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=alternative.id,
        final_quantity=Decimal("120"),
        reason="Accepted alternative candidate",
    )

    assert decision.decision_type == (
        CalculationDecisionType.ALTERNATIVE_CANDIDATE
    )
    assert decision.risk == "HIGH"
    assert (
        decision.requires_admin_confirmation
        is True
    )
    assert (
        decision.risk_rule_version
        == service.DECISION_RISK_RULE_VERSION
    )


def test_task2i_policy_integration_material_warning(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.enums import CalculationDecisionType
    from sqlalchemy import select

    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    primary = group.current_children[0]
    result = session.scalar(
        select(DemandRunItemResult).join(
            DemandCalculationRun,
            DemandRunItemResult.calculation_run_id
            == DemandCalculationRun.id,
        ).where(
            DemandRunItemResult.tenant_id
            == actor_contributor.tenant_id,
            DemandRunItemResult.spare_part_id
            == spare_a.id,
            DemandCalculationRun.calculation_id
            == primary.calculation_id,
        )
    )
    assert result is not None
    result.warning_codes_json = ["HIGH_VARIANCE"]
    session.commit()

    decision = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=primary.id,
        final_quantity=Decimal("100"),
        reason=None,
    )

    assert decision.decision_type == (
        CalculationDecisionType.SYSTEM_RECOMMENDATION
    )
    assert decision.risk == "HIGH"
    assert (
        decision.requires_admin_confirmation
        is True
    )
    assert (
        decision.risk_rule_version
        == service.DECISION_RISK_RULE_VERSION
    )


def test_task2i_policy_integration_outside_all_intervals(
    session: Session,
    actor_contributor: ActorContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.enums import CalculationDecisionType

    service, group, spare_a, _ = (
        completed_comparison_group(
            session,
            actor_contributor,
            monkeypatch,
        )
    )
    primary, alternative = group.current_children
    _task2i_add_result_to_current_run(
        session,
        alternative,
        spare_a,
        quantity="120",
    )

    decision = service.save_decision(
        session,
        actor_contributor,
        group.id,
        spare_part_id=spare_a.id,
        expected_version=0,
        selected_child_id=primary.id,
        final_quantity=Decimal("200"),
        reason="Operational override",
    )

    assert decision.decision_type == (
        CalculationDecisionType.MANUAL_QUANTITY
    )
    assert decision.risk == "HIGH"
    assert (
        decision.requires_admin_confirmation
        is True
    )
    assert (
        decision.risk_rule_version
        == service.DECISION_RISK_RULE_VERSION
    )
