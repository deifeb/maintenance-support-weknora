from __future__ import annotations

import importlib
import inspect
from copy import deepcopy
from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Any

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandList,
    DemandListEvent,
    DemandListItem,
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
    DemandListEventType,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewEventType,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from sqlalchemy import select
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK4_FEATURE_MISSING"
DEMAND_LIST_SERVICE_MODULE = "app.services.demand_list_service"
REVIEW_SERVICE_MODULE = "app.services.demand_review_service"
SCHEMA_MODULE = "app.schemas.demand_review"


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


def _task4_contract():
    demand_list_module = _future(DEMAND_LIST_SERVICE_MODULE)
    review_module = _future(REVIEW_SERVICE_MODULE)
    schema = _future(SCHEMA_MODULE)
    demand_list_type = getattr(demand_list_module, "DemandListService", None)
    review_type = getattr(review_module, "DemandReviewService", None)
    override_type = getattr(
        demand_list_module,
        "DemandListDerivedItemOverride",
        None,
    )
    missing: list[str] = []
    if demand_list_type is None:
        missing.append("DemandListService")
    elif not hasattr(
        demand_list_type,
        "create_derived_draft_in_transaction",
    ):
        missing.append(
            "DemandListService.create_derived_draft_in_transaction"
        )
    if override_type is None:
        missing.append("DemandListDerivedItemOverride")
    if review_type is None:
        missing.append("DemandReviewService")
    elif not hasattr(review_type, "derive"):
        missing.append("DemandReviewService.derive")
    if not hasattr(schema, "DemandReviewDeriveRead"):
        missing.append("DemandReviewDeriveRead")
    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: {', '.join(missing)}",
            pytrace=False,
        )
    return demand_list_module, review_module, schema


def _create_source(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    quantities: tuple[str, ...] = ("10.000000", "20.000000"),
) -> tuple[DemandList, list[DemandListItem]]:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-DERIVE-{suffix}",
        name=f"Derive scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-DERIVE-{suffix}",
        version_name=f"Derive version {suffix}",
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
    repository = DemandListRepository()
    source = repository.create_version(
        session,
        tenant_id,
        {
            "name": f"Derive source {suffix}",
            "description": f"Formal review source {suffix}",
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

    items: list[DemandListItem] = []
    for index, quantity in enumerate(quantities, start=1):
        spare = SparePart(
            tenant_id=tenant_id,
            code=f"SP-DERIVE-{suffix}-{index}",
            name=f"Derive spare {suffix}-{index}",
            unit="EA",
        )
        session.add(spare)
        session.flush()
        child_id = 1000 + index
        item = repository.add_item(
            session,
            tenant_id,
            demand_list_id=source.id,
            spare_part_id=spare.id,
            original_quantity=Decimal(quantity),
            final_quantity=Decimal(quantity),
            source_snapshot={
                "recommended_spare_quantity": quantity,
                "legacy_source": {"keep": index},
            },
            spare_part_code_snapshot=spare.code,
            spare_part_name_snapshot=spare.name,
            spare_part_unit_snapshot=spare.unit,
        )
        item.criticality_level_snapshot = "LOW"
        item.decision_snapshot_json = {
            "source_child_id": child_id,
            "legacy_decision": {"keep": index},
        }
        item.interval_snapshot_json = {
            "system_source_child_id": child_id,
            "selected_child_id": child_id,
            "candidates": [
                {
                    "child_id": child_id,
                    "candidate_key": f"candidate-{index}",
                    "reliability_model": "WEIBULL",
                    "execution_mode": "ANALYTICAL",
                    "recommended_quantity": quantity,
                    "p50": quantity,
                    "p80": quantity,
                    "p90": quantity,
                    "p95": quantity,
                    "p99": quantity,
                    "warnings": [],
                }
            ],
        }
        item.parameter_snapshot_json = {"legacy_parameter": index}
        item.warning_snapshot_json = [f"LEGACY-{index}"]
        item.inventory_snapshot_json = {"on_hand": str(index)}
        session.flush()
        items.append(item)
    return source, items


def _create_ready_review(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    quantities: tuple[str, ...] = ("10.000000", "20.000000"),
) -> tuple[DemandReview, DemandList, list[DemandListItem]]:
    source, items = _create_source(
        session,
        tenant_id,
        suffix,
        quantities=quantities,
    )
    review = DemandReview(
        tenant_id=tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=DemandReviewStatus.READY_TO_DERIVE,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="4" * 64,
        source_snapshot_json={"source_id": source.id},
        total_finding_count=0,
        blocking_finding_count=0,
        pending_finding_count=0,
        pending_blocking_finding_count=0,
    )
    session.add(review)
    session.flush()
    return review, source, items


def _add_resolved_finding(
    session: Session,
    review: DemandReview,
    source_item: DemandListItem,
    *,
    suffix: str,
    action: DemandReviewDecisionStatus,
    suggested_quantity: str | None = "7.000000",
    final_quantity: str | None = None,
    reason: str | None = "formal review decision",
) -> tuple[DemandReviewFinding, DemandReviewDecision]:
    suggestion: dict[str, Any] = {
        "reason": "SERVER_SUGGESTION",
    }
    if suggested_quantity is not None:
        suggestion["final_quantity"] = suggested_quantity
    finding = DemandReviewFinding(
        tenant_id=review.tenant_id,
        review_id=review.id,
        finding_key=f"DERIVE:{suffix}:{source_item.id}",
        rule_code="INVENTORY_GAP",
        finding_type="QUANTITY",
        severity=DemandReviewSeverity.HIGH,
        blocking=True,
        requires_admin_acceptance=False,
        source_demand_list_item_id=source_item.id,
        effect_key=f"FINAL_QUANTITY:{source_item.id}",
        evidence_snapshot_json={"source_item_id": source_item.id},
        suggestion_snapshot_json=suggestion,
        decision_status=action,
    )
    session.add(finding)
    session.flush()
    decision = DemandReviewDecision(
        tenant_id=review.tenant_id,
        review_id=review.id,
        finding_id=finding.id,
        action=action.value,
        suggested_quantity=(
            Decimal(suggested_quantity)
            if suggested_quantity is not None
            else None
        ),
        final_quantity=(
            Decimal(final_quantity)
            if final_quantity is not None
            else None
        ),
        reason=reason,
        actor_user_id="review-admin",
        actor_roles_json=["admin"],
        request_id=f"decision-{suffix}",
        request_hash=(str(finding.id) * 64)[:64],
        review_version_before=review.version,
        review_version_after=review.version,
        finding_version_before=finding.version,
        finding_version_after=finding.version,
        before_snapshot_json={"decision_status": "PENDING"},
        after_snapshot_json={"decision_status": action.value},
    )
    session.add(decision)
    session.flush()
    review.total_finding_count += 1
    review.blocking_finding_count += 1
    session.flush()
    return finding, decision


def _source_snapshot(
    session: Session,
    source_id: int,
) -> dict[str, Any]:
    source = session.get(DemandList, source_id)
    assert source is not None
    items = list(
        session.scalars(
            select(DemandListItem)
            .where(DemandListItem.demand_list_id == source_id)
            .order_by(DemandListItem.id)
        ).all()
    )
    return {
        "id": source.id,
        "status": source.status.value,
        "is_current": source.is_current,
        "version": source.version,
        "version_number": source.version_number,
        "superseded_by_id": source.superseded_by_id,
        "superseded_at": source.superseded_at,
        "items": [
            {
                "id": item.id,
                "final_quantity": str(item.final_quantity),
                "decision_type": (
                    item.decision_type.value
                    if item.decision_type is not None
                    else None
                ),
                "decision_reason": item.decision_reason,
                "decision_snapshot": deepcopy(
                    item.decision_snapshot_json
                ),
                "interval_snapshot": deepcopy(
                    item.interval_snapshot_json
                ),
                "parameter_snapshot": deepcopy(
                    item.parameter_snapshot_json
                ),
                "warning_snapshot": deepcopy(
                    item.warning_snapshot_json
                ),
                "inventory_snapshot": deepcopy(
                    item.inventory_snapshot_json
                ),
                "version": item.version,
            }
            for item in items
        ],
    }


def _derived_rows(
    session: Session,
    source: DemandList,
) -> list[DemandList]:
    return list(
        session.scalars(
            select(DemandList)
            .where(
                DemandList.tenant_id == source.tenant_id,
                DemandList.lineage_id == source.lineage_id,
                DemandList.id != source.id,
            )
            .order_by(DemandList.id)
        ).all()
    )


def _derive(
    session: Session,
    actor,
    review: DemandReview,
    *,
    idempotency_key: str = "task4-formal-derive",
    expected_review_version: int | None = None,
):
    _, review_module, _ = _task4_contract()
    return review_module.DemandReviewService().derive(
        session,
        actor,
        review.id,
        expected_review_version=(
            review.version
            if expected_review_version is None
            else expected_review_version
        ),
        idempotency_key=idempotency_key,
    )


def test_task4_contract_exposes_exact_flush_only_interfaces() -> None:
    demand_list_module, review_module, schema = _task4_contract()
    override_type = demand_list_module.DemandListDerivedItemOverride
    assert is_dataclass(override_type)
    assert [field.name for field in fields(override_type)] == [
        "final_quantity",
        "reason",
        "review_id",
        "finding_id",
        "decision_id",
    ]
    helper = inspect.signature(
        demand_list_module.DemandListService
        .create_derived_draft_in_transaction
    )
    assert list(helper.parameters) == [
        "self",
        "session",
        "actor",
        "source_demand_list_id",
        "expected_source_version",
        "require_current",
        "item_overrides",
        "derivation_context",
        "event_idempotency_key",
        "event_request_hash",
    ]
    derive = inspect.signature(review_module.DemandReviewService.derive)
    assert list(derive.parameters) == [
        "self",
        "session",
        "actor",
        "review_id",
        "expected_review_version",
        "idempotency_key",
    ]
    assert schema.DemandReviewDeriveRead is not None


def test_internal_helper_flushes_but_never_commits_or_rolls_back(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, _, _ = _task4_contract()
    source, _ = _create_source(session, actor_admin.tenant_id, "HELPER-TX")
    service = demand_list_module.DemandListService()
    calls: list[str] = []
    original_flush = session.flush
    original_commit = session.commit
    original_rollback = session.rollback

    def counted_flush(*args, **kwargs):
        calls.append("flush")
        return original_flush(*args, **kwargs)

    def forbidden_commit(*args, **kwargs):
        calls.append("commit")
        return original_commit(*args, **kwargs)

    def forbidden_rollback(*args, **kwargs):
        calls.append("rollback")
        return original_rollback(*args, **kwargs)

    monkeypatch.setattr(session, "flush", counted_flush)
    monkeypatch.setattr(session, "commit", forbidden_commit)
    monkeypatch.setattr(session, "rollback", forbidden_rollback)

    derived, event = service.create_derived_draft_in_transaction(
        session,
        actor_admin,
        source.id,
        expected_source_version=source.version,
        require_current=True,
        item_overrides={},
        derivation_context={"origin": "formal_review"},
    )

    assert derived.id is not None
    assert event.id is not None
    assert "flush" in calls
    assert "commit" not in calls
    assert "rollback" not in calls


def test_formal_derive_calls_helper_with_require_current_true(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, review_module, _ = _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "FORMAL-CURRENT",
    )
    captured: dict[str, Any] = {}
    original = (
        demand_list_module.DemandListService
        .create_derived_draft_in_transaction
    )

    def wrapped(self, *args, **kwargs):
        captured.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        demand_list_module.DemandListService,
        "create_derived_draft_in_transaction",
        wrapped,
    )
    review_module.DemandReviewService().derive(
        session,
        actor_admin,
        review.id,
        expected_review_version=review.version,
        idempotency_key="task4-formal-current",
    )
    assert captured["require_current"] is True
    assert captured["expected_source_version"] == review.source_demand_list_version


def test_public_derive_preserves_require_current_false_helper_mode(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, _, _ = _task4_contract()
    source, _ = _create_source(session, actor_admin.tenant_id, "PUBLIC-BASELINE")
    service = demand_list_module.DemandListService()
    captured: dict[str, Any] = {}
    original = service.create_derived_draft_in_transaction

    def wrapped(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        service,
        "create_derived_draft_in_transaction",
        wrapped,
    )
    service.derive(
        session,
        actor_admin,
        source.id,
        expected_version=source.version,
        idempotency_key="task4-public-helper-mode",
    )
    assert captured["require_current"] is False


@pytest.mark.parametrize(
    ("action", "expected_quantity"),
    [
        (DemandReviewDecisionStatus.REJECTED, Decimal("10.000000")),
        (DemandReviewDecisionStatus.ACCEPTED, Decimal("7.000000")),
        (DemandReviewDecisionStatus.EDIT_ACCEPTED, Decimal("6.500000")),
    ],
)
def test_decision_to_quantity_override_mapping(
    session: Session,
    actor_admin,
    action: DemandReviewDecisionStatus,
    expected_quantity: Decimal,
) -> None:
    _task4_contract()
    review, source, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        f"MAP-{action.value}",
        quantities=("10.000000",),
    )
    _add_resolved_finding(
        session,
        review,
        items[0],
        suffix=action.value,
        action=action,
        suggested_quantity="7.000000",
        final_quantity=(
            "6.500000"
            if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            else None
        ),
        reason="mapped review quantity",
    )

    result = _derive(session, actor_admin, review)

    assert result.derived_demand_list.derived_from_id == source.id
    assert result.derived_demand_list.items[0].final_quantity == expected_quantity


@pytest.mark.parametrize("broken", ["missing", "malformed"])
def test_accepted_quantity_requires_valid_server_suggestion(
    session: Session,
    actor_admin,
    broken: str,
) -> None:
    _task4_contract()
    review, _, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        f"BROKEN-SUGGESTION-{broken}",
        quantities=("10.000000",),
    )
    finding, _ = _add_resolved_finding(
        session,
        review,
        items[0],
        suffix=broken,
        action=DemandReviewDecisionStatus.ACCEPTED,
        suggested_quantity="7.000000",
    )
    finding.suggestion_snapshot_json = (
        {"reason": "SERVER_SUGGESTION"}
        if broken == "missing"
        else {
            "final_quantity": "not-a-decimal",
            "reason": "SERVER_SUGGESTION",
        }
    )
    session.flush()

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"


def test_edit_accepted_requires_persisted_final_quantity(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "EDIT-MISSING",
        quantities=("10.000000",),
    )
    _add_resolved_finding(
        session,
        review,
        items[0],
        suffix="edit-missing",
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity=None,
    )

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"


def test_formal_derive_creates_same_lineage_draft_and_copies_all_items(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, source, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "LINEAGE",
    )

    result = _derive(session, actor_admin, review)

    derived = result.derived_demand_list
    assert derived.status is DemandListStatus.DRAFT
    assert derived.lineage_id == source.lineage_id
    assert derived.derived_from_id == source.id
    assert derived.version_number == source.version_number + 1
    assert len(derived.items) == len(items)


def test_formal_derive_keeps_source_and_source_items_immutable(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, source, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "IMMUTABLE",
        quantities=("10.000000",),
    )
    _add_resolved_finding(
        session,
        review,
        items[0],
        suffix="immutable",
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity="6.000000",
    )
    before = _source_snapshot(session, source.id)

    _derive(session, actor_admin, review)

    assert _source_snapshot(session, source.id) == before


def test_changed_quantity_preserves_snapshots_and_adds_namespaced_audit(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, items = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "AUDIT",
        quantities=("10.000000",),
    )
    source_item = items[0]
    original_decision_snapshot = deepcopy(
        source_item.decision_snapshot_json
    )
    finding, decision = _add_resolved_finding(
        session,
        review,
        source_item,
        suffix="audit",
        action=DemandReviewDecisionStatus.EDIT_ACCEPTED,
        final_quantity="6.250000",
        reason="formal audited quantity",
    )

    result = _derive(session, actor_admin, review)
    derived_item = result.derived_demand_list.items[0]
    audit = derived_item.decision_snapshot_json

    assert audit is not None
    for key, value in original_decision_snapshot.items():
        assert audit[key] == value
    assert audit["demand_review"] == {
        "review_id": review.id,
        "finding_id": finding.id,
        "decision_id": decision.id,
    }
    assert "formal_review_id" not in audit
    assert "formal_finding_id" not in audit
    assert "formal_decision_id" not in audit
    assert "source_demand_list_id" not in audit
    assert derived_item.decision_type.value == "MANUAL_QUANTITY"
    assert derived_item.decision_reason == "formal audited quantity"
    assert derived_item.interval_snapshot_json == source_item.interval_snapshot_json
    assert derived_item.parameter_snapshot_json == source_item.parameter_snapshot_json
    assert derived_item.warning_snapshot_json == source_item.warning_snapshot_json
    assert derived_item.inventory_snapshot_json == source_item.inventory_snapshot_json


def test_formal_derive_sets_review_derived_projection_atomically(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "REVIEW-PROJECTION",
    )
    initial_version = review.version

    result = _derive(session, actor_admin, review)

    session.refresh(review)
    assert review.status is DemandReviewStatus.DERIVED
    assert review.derived_demand_list_id == result.derived_demand_list.id
    assert review.version == initial_version + 1
    assert result.review.status is DemandReviewStatus.DERIVED


@pytest.mark.parametrize(
    ("status", "is_current"),
    [
        (DemandListStatus.PUBLISHED, False),
        (DemandListStatus.VOIDED, False),
    ],
)
def test_stale_source_state_is_review_derivation_conflict(
    session: Session,
    actor_admin,
    status: DemandListStatus,
    is_current: bool,
) -> None:
    _task4_contract()
    review, source, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        f"STALE-{status.value}",
    )
    source.status = status
    source.is_current = is_current
    session.commit()

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"
    assert caught.value.details["expected_status"] == "PUBLISHED"
    assert caught.value.details["actual_status"] == status.value
    assert caught.value.details["expected_source_version"] == (
        review.source_demand_list_version
    )
    assert "actual_source_version" in caught.value.details


def test_source_version_change_is_review_derivation_conflict(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, source, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "VERSION-CONFLICT",
    )
    source.version += 1
    session.commit()

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"
    assert caught.value.details["expected_source_version"] == (
        review.source_demand_list_version
    )
    assert caught.value.details["actual_source_version"] == source.version


def test_formal_derive_receipt_owns_key_not_demand_list_event(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "RECEIPT-NAMESPACE",
    )
    key = "task4-review-owned-key"

    result = _derive(
        session,
        actor_admin,
        review,
        idempotency_key=key,
    )

    review_events = list(
        session.scalars(
            select(DemandReviewEvent).where(
                DemandReviewEvent.review_id == review.id,
                DemandReviewEvent.command_type == DemandReviewCommandType.DERIVE,
            )
        ).all()
    )
    assert len(review_events) == 1
    assert review_events[0].event_type is DemandReviewEventType.DERIVED
    assert review_events[0].idempotency_key == key
    derived_events = list(
        session.scalars(
            select(DemandListEvent).where(
                DemandListEvent.demand_list_id == result.derived_demand_list.id,
                DemandListEvent.event_type == DemandListEventType.DERIVED,
            )
        ).all()
    )
    assert len(derived_events) == 1
    assert derived_events[0].idempotency_key is None


def test_atomic_rollback_when_item_copy_fails_mid_helper(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, _, _ = _task4_contract()
    review, source, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "ROLLBACK-COPY",
    )
    source_before = _source_snapshot(session, source.id)
    review_version = review.version
    original = demand_list_module.DemandListService._copy_item_to_derived
    calls = 0

    def fail_second(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("task4 forced derived item copy failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        demand_list_module.DemandListService,
        "_copy_item_to_derived",
        fail_second,
    )

    with pytest.raises(
        RuntimeError,
        match="task4 forced derived item copy failure",
    ):
        _derive(session, actor_admin, review)

    session.expire_all()
    reloaded = session.get(DemandReview, review.id)
    assert reloaded is not None
    assert _derived_rows(session, source) == []
    assert reloaded.status is DemandReviewStatus.READY_TO_DERIVE
    assert reloaded.version == review_version
    assert reloaded.derived_demand_list_id is None
    assert not list(
        session.scalars(
            select(DemandReviewEvent).where(
                DemandReviewEvent.review_id == review.id,
                DemandReviewEvent.event_type == DemandReviewEventType.DERIVED,
            )
        ).all()
    )
    assert _source_snapshot(session, source.id) == source_before


def test_atomic_rollback_when_review_event_append_fails_after_helper(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, review_module, _ = _task4_contract()
    review, source, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "ROLLBACK-REVIEW-EVENT",
    )
    source_before = _source_snapshot(session, source.id)
    review_version = review.version
    service = review_module.DemandReviewService()
    original_append = service.repository.append_event

    def fail_derive_event(session_arg, tenant_id, *, review_id, data):
        if data.get("command_type") is DemandReviewCommandType.DERIVE:
            raise RuntimeError("task4 forced review event failure")
        return original_append(
            session_arg,
            tenant_id,
            review_id=review_id,
            data=data,
        )

    monkeypatch.setattr(
        service.repository,
        "append_event",
        fail_derive_event,
    )

    with pytest.raises(
        RuntimeError,
        match="task4 forced review event failure",
    ):
        service.derive(
            session,
            actor_admin,
            review.id,
            expected_review_version=review.version,
            idempotency_key="task4-fail-review-event",
        )

    session.expire_all()
    reloaded = session.get(DemandReview, review.id)
    assert reloaded is not None
    assert _derived_rows(session, source) == []
    assert reloaded.status is DemandReviewStatus.READY_TO_DERIVE
    assert reloaded.version == review_version
    assert reloaded.derived_demand_list_id is None
    assert _source_snapshot(session, source.id) == source_before


def test_same_derive_key_and_hash_replays_original_derived_list(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, source, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "REPLAY",
    )
    version = review.version
    key = "task4-replay"

    first = _derive(
        session,
        actor_admin,
        review,
        idempotency_key=key,
        expected_review_version=version,
    )
    replay = _derive(
        session,
        actor_admin,
        review,
        idempotency_key=key,
        expected_review_version=version,
    )

    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert replay.derived_demand_list.id == first.derived_demand_list.id
    assert len(_derived_rows(session, source)) == 1


def test_same_derive_key_different_hash_is_rejected_before_state_check(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "REUSED",
    )
    version = review.version
    key = "task4-reused"
    _derive(
        session,
        actor_admin,
        review,
        idempotency_key=key,
        expected_review_version=version,
    )

    with pytest.raises(AppException) as caught:
        _derive(
            session,
            actor_admin,
            review,
            idempotency_key=key,
            expected_review_version=version + 1,
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_non_admin_cannot_formally_derive(
    session: Session,
    actor_contributor,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_contributor.tenant_id,
        "ROLE",
    )

    with pytest.raises(AppException) as caught:
        _derive(session, actor_contributor, review)

    assert caught.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_review_must_be_ready_to_derive(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "STATE",
    )
    review.status = DemandReviewStatus.OPEN
    session.commit()

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_STATE_CONFLICT"


def test_pending_blocking_findings_refuse_derivation(
    session: Session,
    actor_admin,
) -> None:
    _task4_contract()
    review, _, _ = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "UNRESOLVED",
    )
    review.total_finding_count = 1
    review.blocking_finding_count = 1
    review.pending_finding_count = 1
    review.pending_blocking_finding_count = 1
    session.commit()

    with pytest.raises(AppException) as caught:
        _derive(session, actor_admin, review)

    assert caught.value.code == "REVIEW_FINDINGS_UNRESOLVED"
