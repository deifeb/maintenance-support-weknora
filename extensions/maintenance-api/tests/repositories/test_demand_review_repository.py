from __future__ import annotations

import importlib
import inspect
from decimal import Decimal

import pytest
from app.models import (
    CalculationGroup,
    DemandList,
    DemandListItem,
    DemandReview,
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
    DemandReviewEventType,
    DemandReviewSeverity,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK2_FEATURE_MISSING"
FUTURE_MODULE = "app.repositories.demand_review_repository"


def _future_module():
    try:
        return importlib.import_module(FUTURE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == FUTURE_MODULE:
            pytest.fail(
                f"{FEATURE_MARKER}: {FUTURE_MODULE}",
                pytrace=False,
            )
        raise


def _repository():
    return _future_module().DemandReviewRepository()


def _create_source(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    status: DemandListStatus = DemandListStatus.PUBLISHED,
    is_current: bool = True,
) -> DemandList:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-REVIEW-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-REVIEW-{suffix}",
        version_name=f"Version {suffix}",
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
            "name": f"Demand review source {suffix}",
            "scenario_version_id": version.id,
            "calculation_group_id": group.id,
            "status": status,
            "is_current": is_current,
            "created_by_user_id": f"user-{suffix}",
            "created_by_request_id": f"request-{suffix}",
        },
    )
    source.status = status
    source.is_current = is_current
    session.flush()
    return source


def _create_review(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> DemandReview:
    source = _create_source(session, tenant_id, suffix)
    review = DemandReview(
        tenant_id=tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=DemandReviewStatus.OPEN,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash=(suffix.lower()[:1] or "a") * 64,
        source_snapshot_json={"source_id": source.id},
    )
    session.add(review)
    session.flush()
    return review


def _add_source_item(
    session: Session,
    tenant_id: str,
    source: DemandList,
    suffix: str,
) -> DemandListItem:
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-REVIEW-{suffix}",
        name=f"Spare {suffix}",
        unit="EA",
    )
    session.add(spare)
    session.flush()
    return DemandListRepository().add_item(
        session,
        tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        original_quantity=Decimal("5.000000"),
        final_quantity=Decimal("5.000000"),
        source_snapshot={"source": suffix},
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
    )


def test_repository_exposes_only_tenant_scoped_flush_only_contract() -> None:
    module = _future_module()
    repository_type = module.DemandReviewRepository
    required = (
        "get",
        "get_for_update",
        "list_page",
        "list_findings",
        "findings_for_update",
        "append_finding",
        "append_decision",
        "append_event",
        "find_command_event",
    )
    for name in required:
        method = getattr(repository_type, name)
        assert "tenant_id" in inspect.signature(method).parameters

    source = inspect.getsource(repository_type)
    assert "session.commit(" not in source
    assert ".commit()" not in source


def test_repository_reads_and_locks_are_tenant_scoped(
    session: Session,
) -> None:
    repository = _repository()
    review_a = _create_review(session, "tenant-a", "A")
    review_b = _create_review(session, "tenant-b", "B")

    assert repository.get(session, "tenant-a", review_a.id).id == review_a.id
    assert repository.get(session, "tenant-a", review_b.id) is None
    assert repository.get_for_update(session, "tenant-a", review_b.id) is None

    rows, total = repository.list_page(
        session,
        "tenant-a",
        page=1,
        page_size=20,
    )
    assert total == 1
    assert [row.id for row in rows] == [review_a.id]


def test_repository_findings_use_canonical_severity_item_null_last_order(
    session: Session,
) -> None:
    repository = _repository()
    review = _create_review(session, "tenant-a", "SORT")
    source = DemandListRepository().get(
        session,
        "tenant-a",
        review.source_demand_list_id,
    )
    assert source is not None
    item_one = _add_source_item(
        session,
        "tenant-a",
        source,
        "SORT-1",
    )
    item_two = _add_source_item(
        session,
        "tenant-a",
        source,
        "SORT-2",
    )
    rows = [
        DemandReviewFinding(
            tenant_id="tenant-a",
            review_id=review.id,
            finding_key="high-null",
            rule_code="EVIDENCE_VALIDITY",
            finding_type="EVIDENCE",
            severity=DemandReviewSeverity.HIGH,
            blocking=False,
            requires_admin_acceptance=False,
            source_demand_list_item_id=None,
            evidence_snapshot_json={},
            suggestion_snapshot_json={},
        ),
        DemandReviewFinding(
            tenant_id="tenant-a",
            review_id=review.id,
            finding_key="high-item-two",
            rule_code="INVENTORY_GAP",
            finding_type="QUANTITY",
            severity=DemandReviewSeverity.HIGH,
            blocking=True,
            requires_admin_acceptance=False,
            source_demand_list_item_id=item_two.id,
            evidence_snapshot_json={},
            suggestion_snapshot_json={},
        ),
        DemandReviewFinding(
            tenant_id="tenant-a",
            review_id=review.id,
            finding_key="critical-null",
            rule_code="COMPLETENESS",
            finding_type="COMPLETENESS",
            severity=DemandReviewSeverity.CRITICAL,
            blocking=True,
            requires_admin_acceptance=True,
            source_demand_list_item_id=None,
            evidence_snapshot_json={},
            suggestion_snapshot_json={},
        ),
        DemandReviewFinding(
            tenant_id="tenant-a",
            review_id=review.id,
            finding_key="high-item-one",
            rule_code="INVENTORY_GAP",
            finding_type="QUANTITY",
            severity=DemandReviewSeverity.HIGH,
            blocking=True,
            requires_admin_acceptance=False,
            source_demand_list_item_id=item_one.id,
            evidence_snapshot_json={},
            suggestion_snapshot_json={},
        ),
    ]
    session.add_all(rows)
    session.flush()

    expected = [
        "critical-null",
        "high-item-one",
        "high-item-two",
        "high-null",
    ]
    assert [
        row.finding_key
        for row in repository.list_findings(
            session,
            "tenant-a",
            review.id,
        )
    ] == expected
    assert [
        row.finding_key
        for row in repository.findings_for_update(
            session,
            "tenant-a",
            review.id,
        )
    ] == expected
    assert repository.list_findings(
        session,
        "tenant-b",
        review.id,
    ) == []


def test_repository_command_receipts_are_tenant_scoped(
    session: Session,
) -> None:
    repository = _repository()
    review_a = _create_review(session, "tenant-a", "EVENT-A")
    review_b = _create_review(session, "tenant-b", "EVENT-B")
    for tenant_id, review, request_hash in (
        ("tenant-a", review_a, "a" * 64),
        ("tenant-b", review_b, "b" * 64),
    ):
        session.add(
            DemandReviewEvent(
                tenant_id=tenant_id,
                review_id=review.id,
                event_type=DemandReviewEventType.OPENED,
                command_type=DemandReviewCommandType.RUN,
                actor_user_id=f"user-{tenant_id}",
                actor_roles_json=["contributor"],
                request_id=f"request-{tenant_id}",
                idempotency_key="shared-run-key",
                request_hash=request_hash,
                response_snapshot_json={"review_id": review.id},
            )
        )
    session.flush()

    event_a = repository.find_command_event(
        session,
        "tenant-a",
        command_type=DemandReviewCommandType.RUN,
        idempotency_key="shared-run-key",
    )
    event_b = repository.find_command_event(
        session,
        "tenant-b",
        command_type=DemandReviewCommandType.RUN,
        idempotency_key="shared-run-key",
    )
    assert event_a is not None
    assert event_b is not None
    assert event_a.review_id == review_a.id
    assert event_b.review_id == review_b.id
