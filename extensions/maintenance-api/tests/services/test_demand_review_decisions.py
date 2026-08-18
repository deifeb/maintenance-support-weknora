from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandList,
    DemandReview,
    DemandReviewDecision,
    DemandReviewEvent,
    DemandReviewFinding,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewEventType,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from app.security.actor import ActorContext, MaintenanceRole
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK3_FEATURE_MISSING"
SCHEMA_MODULE = "app.schemas.demand_review"
SERVICE_MODULE = "app.services.demand_review_service"


def _future(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            pytest.fail(
                f"{FEATURE_MARKER}: {module_name}",
                pytrace=False,
            )
        raise


def _task3_contract():
    schema = _future(SCHEMA_MODULE)
    service_module = _future(SERVICE_MODULE)
    required_schema = (
        "DemandReviewDecisionRequest",
        "DemandReviewBatchDecisionItem",
        "DemandReviewBatchDecisionRequest",
    )
    missing = [name for name in required_schema if not hasattr(schema, name)]
    service_type = getattr(service_module, "DemandReviewService", None)
    if service_type is None:
        missing.append("DemandReviewService")
    else:
        for name in ("decide_finding", "batch_decide"):
            if not hasattr(service_type, name):
                missing.append(f"DemandReviewService.{name}")
    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: {', '.join(missing)}",
            pytrace=False,
        )
    return schema, service_type


def _service():
    _, service_type = _task3_contract()
    return service_type()


def _create_source(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> DemandList:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-DEC-{suffix}",
        name=f"Decision scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-DEC-{suffix}",
        version_name=f"Decision version {suffix}",
    )
    session.add(version)
    session.flush()
    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=version.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id=f"user-{suffix}",
        created_by_request_id=f"request-{suffix}",
    )
    session.add(group)
    session.flush()
    source = DemandListRepository().create_version(
        session,
        tenant_id,
        {
            "name": f"Decision source {suffix}",
            "scenario_version_id": version.id,
            "calculation_group_id": group.id,
            "status": DemandListStatus.PUBLISHED,
            "is_current": True,
            "created_by_user_id": f"user-{suffix}",
            "created_by_request_id": f"request-{suffix}",
        },
    )
    source.status = DemandListStatus.PUBLISHED
    source.is_current = True
    session.flush()
    return source


def _add_source_item(
    session: Session,
    tenant_id: str,
    source: DemandList,
    suffix: str,
):
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-DEC-{suffix}",
        name=f"Decision spare {suffix}",
        unit="EA",
    )
    session.add(spare)
    session.flush()
    item = DemandListRepository().add_item(
        session,
        tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        original_quantity=Decimal("10.000000"),
        final_quantity=Decimal("10.000000"),
        source_snapshot={"source": suffix},
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
    )
    session.flush()
    return item


def _create_review(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    specs: tuple[dict[str, Any], ...] | None = None,
    status: DemandReviewStatus = DemandReviewStatus.OPEN,
) -> tuple[DemandReview, list[DemandReviewFinding]]:
    source = _create_source(session, tenant_id, suffix)
    review = DemandReview(
        tenant_id=tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=status,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="d" * 64,
        source_snapshot_json={"source_id": source.id},
    )
    if status is DemandReviewStatus.DERIVED:
        review.derived_demand_list_id = source.id
    session.add(review)
    session.flush()

    if specs is None:
        specs = (
            {
                "blocking": True,
                "requires_admin_acceptance": False,
                "quantity_effect": True,
            },
        )

    findings: list[DemandReviewFinding] = []
    for index, spec in enumerate(specs, start=1):
        item = _add_source_item(
            session,
            tenant_id,
            source,
            f"{suffix}-{index}",
        )
        quantity_effect = bool(spec.get("quantity_effect", True))
        suggestion = (
            {
                "final_quantity": str(
                    spec.get("suggested_quantity", "8.000000")
                ),
                "reason": "SERVER_SUGGESTION",
            }
            if quantity_effect
            else {"action": "REVIEW_EVIDENCE"}
        )
        finding = DemandReviewFinding(
            tenant_id=tenant_id,
            review_id=review.id,
            finding_key=f"DECISION:{suffix}:{index}",
            rule_code="INVENTORY_GAP" if quantity_effect else "EVIDENCE_VALIDITY",
            finding_type="QUANTITY" if quantity_effect else "EVIDENCE",
            severity=spec.get("severity", DemandReviewSeverity.HIGH),
            blocking=bool(spec.get("blocking", True)),
            requires_admin_acceptance=bool(
                spec.get("requires_admin_acceptance", False)
            ),
            source_demand_list_item_id=item.id,
            effect_key=(
                f"FINAL_QUANTITY:{item.id}"
                if quantity_effect
                else spec.get("effect_key")
            ),
            evidence_snapshot_json={"source_item_id": item.id},
            suggestion_snapshot_json=suggestion,
            decision_status=spec.get(
                "decision_status",
                DemandReviewDecisionStatus.PENDING,
            ),
        )
        session.add(finding)
        findings.append(finding)
    session.flush()
    review.total_finding_count = len(findings)
    review.blocking_finding_count = sum(1 for row in findings if row.blocking)
    review.pending_finding_count = sum(
        1
        for row in findings
        if row.decision_status is DemandReviewDecisionStatus.PENDING
    )
    review.pending_blocking_finding_count = sum(
        1
        for row in findings
        if row.blocking
        and row.decision_status is DemandReviewDecisionStatus.PENDING
    )
    session.flush()
    return review, findings


def _decide(
    session: Session,
    actor: ActorContext,
    review: DemandReview,
    finding: DemandReviewFinding,
    *,
    action: DemandReviewDecisionStatus,
    expected_review_version: int | None = None,
    expected_finding_version: int | None = None,
    final_quantity: Decimal | None = None,
    reason: str | None = None,
    idempotency_key: str = "decision-key",
):
    return _service().decide_finding(
        session,
        actor,
        review.id,
        finding.id,
        expected_review_version=(
            review.version
            if expected_review_version is None
            else expected_review_version
        ),
        expected_finding_version=(
            finding.version
            if expected_finding_version is None
            else expected_finding_version
        ),
        action=action,
        final_quantity=final_quantity,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def _batch_item(
    schema,
    finding: DemandReviewFinding,
    *,
    action: DemandReviewDecisionStatus = DemandReviewDecisionStatus.REJECTED,
    expected_finding_version: int | None = None,
    final_quantity: Decimal | None = None,
    reason: str | None = None,
):
    return schema.DemandReviewBatchDecisionItem(
        finding_id=finding.id,
        expected_finding_version=(
            finding.version
            if expected_finding_version is None
            else expected_finding_version
        ),
        action=action.value,
        final_quantity=final_quantity,
        reason=reason,
    )


def _batch(
    session: Session,
    actor: ActorContext,
    review: DemandReview,
    commands,
    *,
    expected_review_version: int | None = None,
    idempotency_key: str = "batch-key",
):
    return _service().batch_decide(
        session,
        actor,
        review.id,
        expected_review_version=(
            review.version
            if expected_review_version is None
            else expected_review_version
        ),
        commands=tuple(commands),
        idempotency_key=idempotency_key,
    )


def _decisions(
    session: Session,
    review_id: int,
) -> list[DemandReviewDecision]:
    return list(
        session.scalars(
            select(DemandReviewDecision)
            .where(DemandReviewDecision.review_id == review_id)
            .order_by(DemandReviewDecision.id.asc())
        ).all()
    )


def _events(
    session: Session,
    review_id: int,
) -> list[DemandReviewEvent]:
    return list(
        session.scalars(
            select(DemandReviewEvent)
            .where(DemandReviewEvent.review_id == review_id)
            .order_by(DemandReviewEvent.id.asc())
        ).all()
    )


def _row_snapshot(row) -> tuple[tuple[str, Any], ...]:
    return tuple(
        (column.name, getattr(row, column.name))
        for column in row.__table__.columns
    )


def test_decision_request_schema_enforces_action_quantity_reason_contract() -> None:
    schema, _ = _task3_contract()
    request_type = schema.DemandReviewDecisionRequest

    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="ACCEPTED",
            final_quantity=Decimal("2"),
        )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="REJECTED",
            final_quantity=Decimal("2"),
        )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="EDIT_ACCEPTED",
            final_quantity=None,
            reason="needed",
        )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="EDIT_ACCEPTED",
            final_quantity=Decimal("2"),
            reason="   ",
        )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="EDIT_ACCEPTED",
            final_quantity=Decimal("-1"),
            reason="needed",
        )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            expected_finding_version=1,
            action="REJECTED",
            unexpected=True,
        )

    request = request_type(
        expected_review_version=2,
        expected_finding_version=3,
        action="EDIT_ACCEPTED",
        final_quantity=Decimal("7.250000"),
        reason="  validated  ",
    )
    assert request.reason == "validated"
    assert request.final_quantity == Decimal("7.250000")


def test_batch_request_schema_rejects_empty_and_duplicate_finding_ids() -> None:
    schema, _ = _task3_contract()
    item_type = schema.DemandReviewBatchDecisionItem
    request_type = schema.DemandReviewBatchDecisionRequest

    with pytest.raises(ValidationError):
        request_type(expected_review_version=1, decisions=())

    command = item_type(
        finding_id=41,
        expected_finding_version=1,
        action="REJECTED",
    )
    with pytest.raises(ValidationError):
        request_type(
            expected_review_version=1,
            decisions=(command, command),
        )


@pytest.mark.parametrize(
    "action",
    [
        DemandReviewDecisionStatus.ACCEPTED,
        DemandReviewDecisionStatus.REJECTED,
        DemandReviewDecisionStatus.EDIT_ACCEPTED,
    ],
)
def test_contributor_can_make_ordinary_final_decisions(
    session: Session,
    actor_context,
    action: DemandReviewDecisionStatus,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", f"ORD-{action.value}")
    finding = findings[0]
    initial_review_version = review.version
    initial_finding_version = finding.version

    response = _decide(
        session,
        actor_context(
            tenant_id="tenant-a",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        review,
        finding,
        action=action,
        final_quantity=(
            Decimal("7.250000")
            if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            else None
        ),
        reason=(
            "  validated locally  "
            if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            else "ordinary decision"
        ),
        idempotency_key=f"ordinary-{action.value}",
    )

    session.refresh(review)
    session.refresh(finding)
    assert finding.decision_status is action
    assert finding.version == initial_finding_version + 1
    assert review.version == initial_review_version + 1
    assert response.version == review.version
    rows = _decisions(session, review.id)
    assert len(rows) == 1
    assert rows[0].action == action.value
    if action is DemandReviewDecisionStatus.ACCEPTED:
        assert rows[0].suggested_quantity == Decimal("8.000000")
        assert rows[0].final_quantity is None
    if action is DemandReviewDecisionStatus.EDIT_ACCEPTED:
        assert rows[0].final_quantity == Decimal("7.250000")
        assert rows[0].reason == "validated locally"


def test_viewer_cannot_decide_finding(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "VIEWER")
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(
                tenant_id="tenant-a",
                role=MaintenanceRole.VIEWER,
            ),
            review,
            findings[0],
            action=DemandReviewDecisionStatus.REJECTED,
        )
    assert caught.value.status_code == 403
    assert caught.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


@pytest.mark.parametrize(
    "action",
    [
        DemandReviewDecisionStatus.ACCEPTED,
        DemandReviewDecisionStatus.EDIT_ACCEPTED,
    ],
)
def test_contributor_cannot_accept_or_edit_high_risk_finding(
    session: Session,
    actor_context,
    action: DemandReviewDecisionStatus,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        f"RISK-{action.value}",
        specs=(
            {
                "blocking": True,
                "requires_admin_acceptance": True,
                "quantity_effect": True,
            },
        ),
    )
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(
                tenant_id="tenant-a",
                role=MaintenanceRole.CONTRIBUTOR,
            ),
            review,
            findings[0],
            action=action,
            final_quantity=(
                Decimal("6.000000")
                if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
                else None
            ),
            reason="high risk edit",
        )
    assert caught.value.status_code == 403
    assert caught.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_contributor_can_reject_high_risk_finding(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "RISK-REJECT",
        specs=(
            {
                "blocking": True,
                "requires_admin_acceptance": True,
                "quantity_effect": True,
            },
        ),
    )
    response = _decide(
        session,
        actor_context(
            tenant_id="tenant-a",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        review,
        findings[0],
        action=DemandReviewDecisionStatus.REJECTED,
        reason="not applicable",
    )
    assert response.findings[0].decision_status is DemandReviewDecisionStatus.REJECTED


@pytest.mark.parametrize(
    "action",
    [
        DemandReviewDecisionStatus.ACCEPTED,
        DemandReviewDecisionStatus.EDIT_ACCEPTED,
    ],
)
def test_admin_can_accept_or_edit_high_risk_finding(
    session: Session,
    actor_context,
    action: DemandReviewDecisionStatus,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        f"ADMIN-{action.value}",
        specs=(
            {
                "blocking": True,
                "requires_admin_acceptance": True,
                "quantity_effect": True,
            },
        ),
    )
    response = _decide(
        session,
        actor_context(
            tenant_id="tenant-a",
            role=MaintenanceRole.ADMIN,
        ),
        review,
        findings[0],
        action=action,
        final_quantity=(
            Decimal("6.000000")
            if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            else None
        ),
        reason=(
            "admin validated"
            if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            else None
        ),
        idempotency_key=f"admin-{action.value}",
    )
    assert response.findings[0].decision_status is action


@pytest.mark.parametrize(
    "status",
    [DemandReviewStatus.DERIVED, DemandReviewStatus.VOIDED],
)
def test_terminal_review_state_rejects_decision(
    session: Session,
    actor_context,
    status: DemandReviewStatus,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        f"STATE-{status.value}",
        status=status,
    )
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            findings[0],
            action=DemandReviewDecisionStatus.REJECTED,
        )
    assert caught.value.code == "REVIEW_STATE_CONFLICT"


def test_review_version_conflict_is_structured(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "REVIEW-VERSION")
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            findings[0],
            action=DemandReviewDecisionStatus.REJECTED,
            expected_review_version=review.version + 1,
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert caught.value.details["conflict_object"] == "demand_review"
    assert caught.value.details["expected_version"] == review.version + 1
    assert caught.value.details["actual_version"] == review.version


def test_finding_version_conflict_is_structured(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "FINDING-VERSION")
    finding = findings[0]
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            finding,
            action=DemandReviewDecisionStatus.REJECTED,
            expected_finding_version=finding.version + 1,
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert caught.value.details["conflict_object"] == "demand_review_finding"
    assert caught.value.details["expected_version"] == finding.version + 1
    assert caught.value.details["actual_version"] == finding.version


def test_cross_tenant_review_is_hidden_as_not_found(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-b", "TENANT-B")
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            findings[0],
            action=DemandReviewDecisionStatus.REJECTED,
        )
    assert caught.value.status_code == 404
    assert caught.value.code == "RESOURCE_NOT_FOUND"


def test_finding_from_other_review_is_hidden_as_not_found(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review_a, _ = _create_review(session, "tenant-a", "REVIEW-A")
    review_b, findings_b = _create_review(session, "tenant-a", "REVIEW-B")
    finding_b = findings_b[0]
    with pytest.raises(AppException) as caught:
        _service().decide_finding(
            session,
            actor_context(tenant_id="tenant-a"),
            review_a.id,
            finding_b.id,
            expected_review_version=review_a.version,
            expected_finding_version=finding_b.version,
            action=DemandReviewDecisionStatus.REJECTED,
            final_quantity=None,
            reason="wrong review",
            idempotency_key="wrong-review",
        )
    assert caught.value.status_code == 404
    assert caught.value.code == "RESOURCE_NOT_FOUND"
    assert review_b.id != review_a.id


def test_edit_accepted_requires_final_quantity_effect_finding(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "EDIT-EFFECT",
        specs=(
            {
                "blocking": True,
                "requires_admin_acceptance": False,
                "quantity_effect": False,
            },
        ),
    )
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            findings[0],
            action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
            final_quantity=Decimal("5.000000"),
            reason="manual quantity",
        )
    assert caught.value.status_code == 422


def test_redecision_appends_history_and_preserves_old_rows(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "REDECIDE")
    finding = findings[0]
    initial_finding_version = finding.version

    _decide(
        session,
        actor_context(tenant_id="tenant-a"),
        review,
        finding,
        action=DemandReviewDecisionStatus.REJECTED,
        reason="first decision",
        idempotency_key="redecision-1",
    )
    first_decision = _decisions(session, review.id)[0]
    first_event = next(
        row
        for row in _events(session, review.id)
        if row.command_type is DemandReviewCommandType.DECIDE_FINDING
    )
    decision_snapshot = _row_snapshot(first_decision)
    event_snapshot = _row_snapshot(first_event)

    session.refresh(review)
    session.refresh(finding)
    _decide(
        session,
        actor_context(tenant_id="tenant-a"),
        review,
        finding,
        action=DemandReviewDecisionStatus.ACCEPTED,
        idempotency_key="redecision-2",
    )

    history = _decisions(session, review.id)
    assert [row.action for row in history] == ["REJECTED", "ACCEPTED"]
    session.refresh(finding)
    assert finding.decision_status is DemandReviewDecisionStatus.ACCEPTED
    assert finding.version == initial_finding_version + 2
    assert _row_snapshot(history[0]) == decision_snapshot
    first_event_again = next(
        row
        for row in _events(session, review.id)
        if row.id == first_event.id
    )
    assert _row_snapshot(first_event_again) == event_snapshot


def test_blocking_pending_keeps_open_then_last_resolution_becomes_ready(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "READY-BLOCKING",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": True, "quantity_effect": True},
        ),
    )
    actor = actor_context(tenant_id="tenant-a")
    first_response = _decide(
        session,
        actor,
        review,
        findings[0],
        action=DemandReviewDecisionStatus.REJECTED,
        idempotency_key="ready-1",
    )
    assert first_response.status is DemandReviewStatus.OPEN
    assert first_response.pending_blocking_finding_count == 1

    session.refresh(review)
    session.refresh(findings[1])
    second_response = _decide(
        session,
        actor,
        review,
        findings[1],
        action=DemandReviewDecisionStatus.REJECTED,
        idempotency_key="ready-2",
    )
    assert second_response.status is DemandReviewStatus.READY_TO_DERIVE
    assert second_response.pending_blocking_finding_count == 0
    assert any(
        row.event_type is DemandReviewEventType.READY_TO_DERIVE
        for row in _events(session, review.id)
    )


def test_nonblocking_pending_does_not_block_ready_to_derive(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "READY-NONBLOCKING",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": False, "quantity_effect": False},
        ),
    )
    response = _decide(
        session,
        actor_context(tenant_id="tenant-a"),
        review,
        findings[0],
        action=DemandReviewDecisionStatus.REJECTED,
        idempotency_key="nonblocking-ready",
    )
    assert response.status is DemandReviewStatus.READY_TO_DERIVE
    assert response.pending_blocking_finding_count == 0
    assert response.pending_finding_count == 1


def test_ready_review_stays_ready_after_final_redecision(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "READY-REDECIDE")
    actor = actor_context(tenant_id="tenant-a")
    first = _decide(
        session,
        actor,
        review,
        findings[0],
        action=DemandReviewDecisionStatus.REJECTED,
        idempotency_key="ready-redecision-1",
    )
    assert first.status is DemandReviewStatus.READY_TO_DERIVE

    session.refresh(review)
    session.refresh(findings[0])
    second = _decide(
        session,
        actor,
        review,
        findings[0],
        action=DemandReviewDecisionStatus.ACCEPTED,
        idempotency_key="ready-redecision-2",
    )
    assert second.status is DemandReviewStatus.READY_TO_DERIVE
    assert second.pending_blocking_finding_count == 0


def test_single_decision_same_key_same_hash_replays_after_versions_advance(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "SINGLE-REPLAY")
    finding = findings[0]
    actor = actor_context(tenant_id="tenant-a")
    expected_review_version = review.version
    expected_finding_version = finding.version

    first = _decide(
        session,
        actor,
        review,
        finding,
        action=DemandReviewDecisionStatus.REJECTED,
        expected_review_version=expected_review_version,
        expected_finding_version=expected_finding_version,
        reason="stable",
        idempotency_key="single-replay",
    )
    replay = _decide(
        session,
        actor,
        review,
        finding,
        action=DemandReviewDecisionStatus.REJECTED,
        expected_review_version=expected_review_version,
        expected_finding_version=expected_finding_version,
        reason="stable",
        idempotency_key="single-replay",
    )
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert len(_decisions(session, review.id)) == 1
    receipts = [
        row
        for row in _events(session, review.id)
        if row.command_type is DemandReviewCommandType.DECIDE_FINDING
    ]
    assert len(receipts) == 1


def test_single_decision_same_key_different_hash_is_rejected_before_version_check(
    session: Session,
    actor_context,
) -> None:
    _task3_contract()
    review, findings = _create_review(session, "tenant-a", "SINGLE-REUSE")
    finding = findings[0]
    actor = actor_context(tenant_id="tenant-a")
    expected_review_version = review.version
    expected_finding_version = finding.version

    _decide(
        session,
        actor,
        review,
        finding,
        action=DemandReviewDecisionStatus.REJECTED,
        expected_review_version=expected_review_version,
        expected_finding_version=expected_finding_version,
        reason="first",
        idempotency_key="single-reuse",
    )
    with pytest.raises(AppException) as caught:
        _decide(
            session,
            actor,
            review,
            finding,
            action=DemandReviewDecisionStatus.ACCEPTED,
            expected_review_version=expected_review_version,
            expected_finding_version=expected_finding_version,
            idempotency_key="single-reuse",
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_batch_success_updates_each_finding_once_and_review_once(
    session: Session,
    actor_context,
) -> None:
    schema, _ = _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "BATCH-SUCCESS",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": True, "quantity_effect": True},
        ),
    )
    review_version = review.version
    finding_versions = {row.id: row.version for row in findings}
    commands = (
        _batch_item(schema, findings[1], reason="second"),
        _batch_item(schema, findings[0], reason="first"),
    )
    response = _batch(
        session,
        actor_context(tenant_id="tenant-a"),
        review,
        commands,
        expected_review_version=review_version,
        idempotency_key="batch-success",
    )
    session.refresh(review)
    for finding in findings:
        session.refresh(finding)
        assert finding.version == finding_versions[finding.id] + 1
        assert finding.decision_status is DemandReviewDecisionStatus.REJECTED
    assert review.version == review_version + 1
    assert response.status is DemandReviewStatus.READY_TO_DERIVE
    assert response.pending_blocking_finding_count == 0
    receipts = [
        row
        for row in _events(session, review.id)
        if row.command_type is DemandReviewCommandType.BATCH_DECIDE
    ]
    assert len(receipts) == 1


def test_batch_invalid_item_rolls_back_every_projection_and_history_write(
    session: Session,
    actor_context,
) -> None:
    schema, _ = _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "BATCH-ATOMIC",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": True, "quantity_effect": True},
        ),
    )
    review_version = review.version
    initial = {
        row.id: (row.version, row.decision_status)
        for row in findings
    }
    commands = (
        _batch_item(schema, findings[0], reason="valid"),
        _batch_item(
            schema,
            findings[1],
            expected_finding_version=findings[1].version + 1,
            reason="stale",
        ),
    )
    with pytest.raises(AppException) as caught:
        _batch(
            session,
            actor_context(tenant_id="tenant-a"),
            review,
            commands,
            expected_review_version=review_version,
            idempotency_key="batch-atomic",
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert _decisions(session, review.id) == []
    session.refresh(review)
    assert review.version == review_version
    for finding in findings:
        session.refresh(finding)
        assert (finding.version, finding.decision_status) == initial[finding.id]


def test_batch_same_key_replays_when_command_order_changes(
    session: Session,
    actor_context,
) -> None:
    schema, _ = _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "BATCH-ORDER",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": True, "quantity_effect": True},
        ),
    )
    review_version = review.version
    first_version = findings[0].version
    second_version = findings[1].version
    command_one = _batch_item(
        schema,
        findings[0],
        expected_finding_version=first_version,
        reason="one",
    )
    command_two = _batch_item(
        schema,
        findings[1],
        expected_finding_version=second_version,
        reason="two",
    )
    actor = actor_context(tenant_id="tenant-a")
    first = _batch(
        session,
        actor,
        review,
        (command_two, command_one),
        expected_review_version=review_version,
        idempotency_key="batch-order",
    )
    replay = _batch(
        session,
        actor,
        review,
        (command_one, command_two),
        expected_review_version=review_version,
        idempotency_key="batch-order",
    )
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert len(_decisions(session, review.id)) == 2
    receipts = [
        row
        for row in _events(session, review.id)
        if row.command_type is DemandReviewCommandType.BATCH_DECIDE
    ]
    assert len(receipts) == 1


def test_batch_same_key_different_hash_is_rejected(
    session: Session,
    actor_context,
) -> None:
    schema, _ = _task3_contract()
    review, findings = _create_review(
        session,
        "tenant-a",
        "BATCH-REUSE",
        specs=(
            {"blocking": True, "quantity_effect": True},
            {"blocking": True, "quantity_effect": True},
        ),
    )
    review_version = review.version
    versions = [row.version for row in findings]
    actor = actor_context(tenant_id="tenant-a")
    first_commands = tuple(
        _batch_item(
            schema,
            finding,
            expected_finding_version=versions[index],
            reason="same",
        )
        for index, finding in enumerate(findings)
    )
    _batch(
        session,
        actor,
        review,
        first_commands,
        expected_review_version=review_version,
        idempotency_key="batch-reuse",
    )
    changed_commands = (
        _batch_item(
            schema,
            findings[0],
            expected_finding_version=versions[0],
            action=DemandReviewDecisionStatus.ACCEPTED,
        ),
        _batch_item(
            schema,
            findings[1],
            expected_finding_version=versions[1],
            reason="same",
        ),
    )
    with pytest.raises(AppException) as caught:
        _batch(
            session,
            actor,
            review,
            changed_commands,
            expected_review_version=review_version,
            idempotency_key="batch-reuse",
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize("command", ["single", "batch"])
def test_decision_commands_require_nonempty_idempotency_key(
    session: Session,
    actor_context,
    command: str,
) -> None:
    schema, _ = _task3_contract()
    review, findings = _create_review(session, "tenant-a", f"KEY-{command}")
    actor = actor_context(tenant_id="tenant-a")
    with pytest.raises(AppException) as caught:
        if command == "single":
            _decide(
                session,
                actor,
                review,
                findings[0],
                action=DemandReviewDecisionStatus.REJECTED,
                idempotency_key="   ",
            )
        else:
            _batch(
                session,
                actor,
                review,
                (_batch_item(schema, findings[0]),),
                idempotency_key="   ",
            )
    assert caught.value.code == "IDEMPOTENCY_KEY_REQUIRED"
