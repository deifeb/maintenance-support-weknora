from __future__ import annotations

import importlib
import inspect
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandList,
    DemandReview,
    DemandReviewDecision,
    DemandReviewFinding,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from sqlalchemy import select
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK3_FEATURE_MISSING"
REPOSITORY_MODULE = "app.repositories.demand_review_repository"
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
    repository_module = _future(REPOSITORY_MODULE)
    schema = _future(SCHEMA_MODULE)
    service_module = _future(SERVICE_MODULE)
    repository_type = repository_module.DemandReviewRepository
    service_type = service_module.DemandReviewService
    missing: list[str] = []
    for name in (
        "DemandReviewDecisionRequest",
        "DemandReviewBatchDecisionItem",
        "DemandReviewBatchDecisionRequest",
    ):
        if not hasattr(schema, name):
            missing.append(name)
    for name in ("decide_finding", "batch_decide"):
        if not hasattr(service_type, name):
            missing.append(f"DemandReviewService.{name}")
    if "finding_ids" not in inspect.signature(
        repository_type.findings_for_update
    ).parameters:
        missing.append("DemandReviewRepository.findings_for_update[finding_ids]")
    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: {', '.join(missing)}",
            pytrace=False,
        )
    return repository_type, schema, service_type


def _create_source(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> DemandList:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-LOCK-{suffix}",
        name=f"Lock scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-LOCK-{suffix}",
        version_name=f"Lock version {suffix}",
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
            "name": f"Lock source {suffix}",
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


def _create_review(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    count: int = 3,
) -> tuple[DemandReview, list[DemandReviewFinding]]:
    source = _create_source(session, tenant_id, suffix)
    review = DemandReview(
        tenant_id=tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=DemandReviewStatus.OPEN,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="c" * 64,
        source_snapshot_json={"source_id": source.id},
    )
    session.add(review)
    session.flush()
    findings: list[DemandReviewFinding] = []
    for index in range(1, count + 1):
        spare = SparePart(
            tenant_id=tenant_id,
            code=f"SP-LOCK-{suffix}-{index}",
            name=f"Lock spare {suffix}-{index}",
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
        finding = DemandReviewFinding(
            tenant_id=tenant_id,
            review_id=review.id,
            finding_key=f"LOCK:{suffix}:{index}",
            rule_code="INVENTORY_GAP",
            finding_type="QUANTITY",
            severity=DemandReviewSeverity.HIGH,
            blocking=True,
            requires_admin_acceptance=False,
            source_demand_list_item_id=item.id,
            effect_key=f"FINAL_QUANTITY:{item.id}",
            evidence_snapshot_json={"source_item_id": item.id},
            suggestion_snapshot_json={
                "final_quantity": "8.000000",
                "reason": "SERVER_SUGGESTION",
            },
        )
        session.add(finding)
        findings.append(finding)
    session.flush()
    review.total_finding_count = len(findings)
    review.blocking_finding_count = len(findings)
    review.pending_finding_count = len(findings)
    review.pending_blocking_finding_count = len(findings)
    session.flush()
    return review, findings


def _batch_item(schema, finding: DemandReviewFinding, *, version: int | None = None):
    return schema.DemandReviewBatchDecisionItem(
        finding_id=finding.id,
        expected_finding_version=(finding.version if version is None else version),
        action="REJECTED",
        reason=f"reject-{finding.id}",
    )


def _decision_count(session: Session, review_id: int) -> int:
    return len(
        list(
            session.scalars(
                select(DemandReviewDecision).where(
                    DemandReviewDecision.review_id == review_id
                )
            ).all()
        )
    )


def test_selected_finding_locks_are_returned_in_ascending_id_order(
    session: Session,
) -> None:
    repository_type, _, _ = _task3_contract()
    review, findings = _create_review(session, "tenant-a", "REPO-ORDER")
    repository = repository_type()
    requested = tuple(row.id for row in reversed(findings))
    locked = repository.findings_for_update(
        session,
        "tenant-a",
        review.id,
        finding_ids=requested,
    )
    assert [row.id for row in locked] == sorted(requested)


def test_batch_locks_review_then_findings_ascending_before_first_mutation(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    repository_type, schema, service_type = _task3_contract()
    review, findings = _create_review(session, "tenant-a", "FLOW")
    repository = repository_type()
    calls: list[tuple[str, object]] = []

    original_review_lock = repository.get_for_update
    original_finding_lock = repository.findings_for_update
    original_append = repository.append_decision

    def review_lock(session_arg, tenant_id, review_id):
        calls.append(("review", review_id))
        return original_review_lock(session_arg, tenant_id, review_id)

    def finding_lock(
        session_arg,
        tenant_id,
        review_id,
        *,
        finding_ids=None,
    ):
        calls.append(("findings", tuple(finding_ids or ())))
        return original_finding_lock(
            session_arg,
            tenant_id,
            review_id,
            finding_ids=finding_ids,
        )

    def append_decision(session_arg, tenant_id, **kwargs):
        calls.append(("mutation", kwargs["finding_id"]))
        return original_append(session_arg, tenant_id, **kwargs)

    monkeypatch.setattr(repository, "get_for_update", review_lock)
    monkeypatch.setattr(repository, "findings_for_update", finding_lock)
    monkeypatch.setattr(repository, "append_decision", append_decision)

    commands = tuple(
        _batch_item(schema, row)
        for row in reversed(findings)
    )
    service_type(repository=repository).batch_decide(
        session,
        actor_context(tenant_id="tenant-a"),
        review.id,
        expected_review_version=review.version,
        commands=commands,
        idempotency_key="lock-flow",
    )

    assert calls[0] == ("review", review.id)
    assert calls[1] == (
        "findings",
        tuple(sorted(row.id for row in findings)),
    )
    first_mutation = next(index for index, item in enumerate(calls) if item[0] == "mutation")
    assert first_mutation > 1


def test_batch_stale_item_is_revalidated_before_any_append(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    repository_type, schema, service_type = _task3_contract()
    review, findings = _create_review(session, "tenant-a", "REVALIDATE")
    repository = repository_type()
    append_calls: list[int] = []
    original_append = repository.append_decision

    def append_decision(session_arg, tenant_id, **kwargs):
        append_calls.append(kwargs["finding_id"])
        return original_append(session_arg, tenant_id, **kwargs)

    monkeypatch.setattr(repository, "append_decision", append_decision)
    commands = (
        _batch_item(schema, findings[0]),
        _batch_item(schema, findings[1], version=findings[1].version + 1),
    )
    with pytest.raises(AppException) as caught:
        service_type(repository=repository).batch_decide(
            session,
            actor_context(tenant_id="tenant-a"),
            review.id,
            expected_review_version=review.version,
            commands=commands,
            idempotency_key="revalidate-before-append",
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert append_calls == []
    assert _decision_count(session, review.id) == 0


def test_overlapping_stale_batch_loses_on_review_version_without_partial_write(
    session: Session,
    actor_context,
) -> None:
    _, schema, service_type = _task3_contract()
    review, findings = _create_review(session, "tenant-a", "OVERLAP")
    actor = actor_context(tenant_id="tenant-a")
    initial_review_version = review.version
    versions = {row.id: row.version for row in findings}

    winner_commands = (
        _batch_item(schema, findings[0], version=versions[findings[0].id]),
        _batch_item(schema, findings[1], version=versions[findings[1].id]),
    )
    service_type().batch_decide(
        session,
        actor,
        review.id,
        expected_review_version=initial_review_version,
        commands=winner_commands,
        idempotency_key="overlap-winner",
    )
    assert _decision_count(session, review.id) == 2

    loser_commands = (
        _batch_item(schema, findings[1], version=versions[findings[1].id]),
        _batch_item(schema, findings[2], version=versions[findings[2].id]),
    )
    with pytest.raises(AppException) as caught:
        service_type().batch_decide(
            session,
            actor,
            review.id,
            expected_review_version=initial_review_version,
            commands=loser_commands,
            idempotency_key="overlap-loser",
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert caught.value.details["conflict_object"] == "demand_review"
    assert _decision_count(session, review.id) == 2
