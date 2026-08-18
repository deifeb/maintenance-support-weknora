from __future__ import annotations

import importlib
import inspect

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandList,
    DemandReview,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewEventType,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK5_SERVICE_FEATURE_MISSING"
REVIEW_SERVICE_MODULE = "app.services.demand_review_service"
REVIEW_REPOSITORY_MODULE = "app.repositories.demand_review_repository"
REVIEW_SCHEMA_MODULE = "app.schemas.demand_review"


def _future(module_name: str):
    return importlib.import_module(module_name)


def _task5_service_contract():
    service_module = _future(REVIEW_SERVICE_MODULE)
    repository_module = _future(REVIEW_REPOSITORY_MODULE)
    schema_module = _future(REVIEW_SCHEMA_MODULE)

    service_type = getattr(service_module, "DemandReviewService", None)
    repository_type = getattr(repository_module, "DemandReviewRepository", None)

    missing: list[str] = []
    for method_name in ("list", "get", "void"):
        if service_type is None or not hasattr(service_type, method_name):
            missing.append(f"DemandReviewService.{method_name}")

    for method_name in ("list_decisions", "list_events"):
        if repository_type is None or not hasattr(repository_type, method_name):
            missing.append(f"DemandReviewRepository.{method_name}")

    if repository_type is not None:
        parameters = inspect.signature(repository_type.list_page).parameters
        for parameter_name in (
            "status",
            "source_demand_list_id",
            "sort_by",
            "sort_order",
        ):
            if parameter_name not in parameters:
                missing.append(
                    f"DemandReviewRepository.list_page.{parameter_name}"
                )

    for schema_name in (
        "DemandReviewSummaryRead",
        "DemandReviewPublicRead",
        "DemandReviewDecisionRead",
        "DemandReviewEventRead",
        "DemandReviewTransitionRequest",
    ):
        if not hasattr(schema_module, schema_name):
            missing.append(schema_name)

    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: {', '.join(missing)}",
            pytrace=False,
        )

    return service_module, repository_module, schema_module


def _source(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> DemandList:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-T5-{suffix}",
        name=f"Task 5 scenario {suffix}",
    )
    session.add(template)
    session.flush()

    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-T5-{suffix}",
        version_name=f"Task 5 version {suffix}",
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
            "name": f"Task 5 source {suffix}",
            "description": "Formal review API support source",
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


def _review_for_source(
    session: Session,
    source: DemandList,
    suffix: str,
    *,
    status: DemandReviewStatus = DemandReviewStatus.OPEN,
) -> DemandReview:
    failure_code = None
    failure_summary = None
    if status is DemandReviewStatus.FAILED:
        failure_code = "TASK5-FAILED"
        failure_summary = "Task 5 failure fixture"

    review = DemandReview(
        tenant_id=source.tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=status,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash=(suffix * 64)[:64],
        source_snapshot_json={"fixture": suffix},
        total_finding_count=0,
        blocking_finding_count=0,
        pending_finding_count=0,
        pending_blocking_finding_count=0,
        failure_code=failure_code,
        failure_summary=failure_summary,
    )
    session.add(review)
    session.flush()
    return review


def _review(
    session: Session,
    tenant_id: str,
    suffix: str,
    *,
    status: DemandReviewStatus = DemandReviewStatus.OPEN,
) -> DemandReview:
    return _review_for_source(
        session,
        _source(session, tenant_id, suffix),
        suffix,
        status=status,
    )


def _service():
    service_module, _, _ = _task5_service_contract()
    return service_module.DemandReviewService()


def test_task5_service_contract_is_available() -> None:
    service_module, repository_module, schema_module = (
        _task5_service_contract()
    )

    assert hasattr(service_module.DemandReviewService, "list")
    assert hasattr(service_module.DemandReviewService, "get")
    assert hasattr(service_module.DemandReviewService, "void")
    assert hasattr(repository_module.DemandReviewRepository, "list_events")
    assert hasattr(
        repository_module.DemandReviewRepository,
        "list_decisions",
    )
    assert hasattr(schema_module, "DemandReviewPublicRead")


def test_review_list_filters_and_uses_stable_id_sort(
    session: Session,
    actor_viewer,
) -> None:
    service = _service()
    source = _source(session, actor_viewer.tenant_id, "LIST")
    first = _review_for_source(
        session,
        source,
        "A",
        status=DemandReviewStatus.OPEN,
    )
    _review_for_source(
        session,
        source,
        "B",
        status=DemandReviewStatus.READY_TO_DERIVE,
    )
    third = _review_for_source(
        session,
        source,
        "C",
        status=DemandReviewStatus.OPEN,
    )
    session.commit()

    result = service.list(
        session,
        actor_viewer,
        page=1,
        page_size=20,
        status=DemandReviewStatus.OPEN,
        source_demand_list_id=source.id,
        sort_by="id",
        sort_order="asc",
    )

    assert [item.id for item in result.items] == [first.id, third.id]
    assert result.total == 2
    assert result.page == 1
    assert result.page_size == 20


def test_review_list_public_summary_excludes_tenant_id(
    session: Session,
    actor_viewer,
) -> None:
    service = _service()
    _review(session, actor_viewer.tenant_id, "PUBLIC-LIST")
    session.commit()

    result = service.list(
        session,
        actor_viewer,
        page=1,
        page_size=20,
        status=None,
        source_demand_list_id=None,
        sort_by="created_at",
        sort_order="desc",
    )

    payload = result.items[0].model_dump(mode="json")
    assert "tenant_id" not in payload


def test_review_get_returns_public_audit_history_without_replay_fields(
    session: Session,
    actor_viewer,
) -> None:
    service_module, repository_module, _ = _task5_service_contract()
    source = _source(session, actor_viewer.tenant_id, "DETAIL")
    review = _review_for_source(session, source, "DETAIL")
    repository = repository_module.DemandReviewRepository()

    finding = repository.append_finding(
        session,
        actor_viewer.tenant_id,
        review_id=review.id,
        data={
            "finding_key": "TASK5-DETAIL",
            "rule_code": "TASK5",
            "finding_type": "TRACE",
            "severity": "LOW",
            "blocking": False,
            "requires_admin_acceptance": False,
            "source_demand_list_item_id": None,
            "effect_key": None,
            "evidence_snapshot_json": {"evidence": True},
            "suggestion_snapshot_json": {"suggestion": True},
        },
    )
    repository.append_decision(
        session,
        actor_viewer.tenant_id,
        review_id=review.id,
        finding_id=finding.id,
        data={
            "action": "REJECTED",
            "suggested_quantity": None,
            "final_quantity": None,
            "reason": "Not applicable",
            "actor_user_id": actor_viewer.user_id,
            "actor_roles_json": [actor_viewer.role.value],
            "request_id": actor_viewer.request_id,
            "request_hash": "d" * 64,
            "review_version_before": 1,
            "review_version_after": 2,
            "finding_version_before": 1,
            "finding_version_after": 2,
            "before_snapshot_json": {"decision_status": "PENDING"},
            "after_snapshot_json": {"decision_status": "REJECTED"},
        },
    )
    repository.append_event(
        session,
        actor_viewer.tenant_id,
        review_id=review.id,
        data={
            "event_type": DemandReviewEventType.DECIDED,
            "actor_user_id": actor_viewer.user_id,
            "actor_roles_json": [actor_viewer.role.value],
            "request_id": actor_viewer.request_id,
            "before_summary_json": {"status": "OPEN"},
            "after_summary_json": {"status": "OPEN"},
        },
    )
    session.commit()

    result = service_module.DemandReviewService().get(
        session,
        actor_viewer,
        review.id,
    )
    payload = result.model_dump(mode="json")

    assert "tenant_id" not in payload
    assert len(payload["decisions"]) == 1
    assert len(payload["events"]) == 1
    assert "request_hash" not in payload["decisions"][0]
    assert "request_hash" not in payload["events"][0]
    assert "response_snapshot_json" not in payload["events"][0]


def test_review_get_cross_tenant_is_hidden_as_not_found(
    session: Session,
    actor_viewer,
) -> None:
    service = _service()
    review = _review(session, "tenant-other", "CROSS-TENANT")
    session.commit()

    with pytest.raises(AppException) as caught:
        service.get(session, actor_viewer, review.id)

    assert caught.value.status_code == 404


def test_void_open_review_is_versioned_and_audited(
    session: Session,
    actor_admin,
) -> None:
    _, repository_module, _ = _task5_service_contract()
    service = _service()
    review = _review(
        session,
        actor_admin.tenant_id,
        "VOID-OPEN",
        status=DemandReviewStatus.OPEN,
    )
    review_id = review.id
    session.commit()

    result = service.void(
        session,
        actor_admin,
        review_id,
        expected_review_version=1,
        idempotency_key="task5-void-open",
    )

    assert result.status is DemandReviewStatus.VOIDED
    assert result.version == 2

    events = repository_module.DemandReviewRepository().list_events(
        session,
        actor_admin.tenant_id,
        review_id,
    )
    event = events[-1]
    assert event.event_type is DemandReviewEventType.VOIDED
    assert event.command_type is DemandReviewCommandType.VOID
    assert event.idempotency_key == "task5-void-open"


def test_void_ready_review_is_allowed(
    session: Session,
    actor_admin,
) -> None:
    service = _service()
    review = _review(
        session,
        actor_admin.tenant_id,
        "VOID-READY",
        status=DemandReviewStatus.READY_TO_DERIVE,
    )
    session.commit()

    result = service.void(
        session,
        actor_admin,
        review.id,
        expected_review_version=1,
        idempotency_key="task5-void-ready",
    )

    assert result.status is DemandReviewStatus.VOIDED
    assert result.version == 2


def test_void_rejects_non_voidable_states(
    session: Session,
    actor_admin,
) -> None:
    service = _service()
    rows = [
        _review(
            session,
            actor_admin.tenant_id,
            "VOID-CREATED",
            status=DemandReviewStatus.CREATED,
        ),
        _review(
            session,
            actor_admin.tenant_id,
            "VOID-RUNNING",
            status=DemandReviewStatus.RUNNING,
        ),
        _review(
            session,
            actor_admin.tenant_id,
            "VOID-FAILED",
            status=DemandReviewStatus.FAILED,
        ),
        _review(
            session,
            actor_admin.tenant_id,
            "VOID-VOIDED",
            status=DemandReviewStatus.VOIDED,
        ),
    ]
    session.commit()

    for index, review in enumerate(rows):
        with pytest.raises(AppException) as caught:
            service.void(
                session,
                actor_admin,
                review.id,
                expected_review_version=1,
                idempotency_key=f"task5-invalid-state-{index}",
            )
        assert caught.value.code == "REVIEW_STATE_CONFLICT"


def test_void_requires_admin(
    session: Session,
    actor_contributor,
) -> None:
    service = _service()
    review = _review(
        session,
        actor_contributor.tenant_id,
        "VOID-RBAC",
        status=DemandReviewStatus.OPEN,
    )
    session.commit()

    with pytest.raises(AppException) as caught:
        service.void(
            session,
            actor_contributor,
            review.id,
            expected_review_version=1,
            idempotency_key="task5-void-rbac",
        )

    assert caught.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_void_idempotency_replays_and_rejects_hash_reuse(
    session: Session,
    actor_admin,
) -> None:
    service = _service()
    review = _review(
        session,
        actor_admin.tenant_id,
        "VOID-REPLAY",
        status=DemandReviewStatus.OPEN,
    )
    session.commit()

    first = service.void(
        session,
        actor_admin,
        review.id,
        expected_review_version=1,
        idempotency_key="task5-void-replay",
    )
    replay = service.void(
        session,
        actor_admin,
        review.id,
        expected_review_version=1,
        idempotency_key="task5-void-replay",
    )

    assert replay.model_dump(mode="json") == first.model_dump(mode="json")

    with pytest.raises(AppException) as caught:
        service.void(
            session,
            actor_admin,
            review.id,
            expected_review_version=2,
            idempotency_key="task5-void-replay",
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"
