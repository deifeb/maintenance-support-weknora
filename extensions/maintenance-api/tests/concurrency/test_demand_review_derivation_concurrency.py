from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandList,
    DemandReview,
    DemandReviewEvent,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK4_FEATURE_MISSING"
DEMAND_LIST_SERVICE_MODULE = "app.services.demand_list_service"
REVIEW_SERVICE_MODULE = "app.services.demand_review_service"
SCHEMA_MODULE = "app.schemas.demand_review"


def _task4_contract():
    demand_list_module = importlib.import_module(DEMAND_LIST_SERVICE_MODULE)
    review_module = importlib.import_module(REVIEW_SERVICE_MODULE)
    schema = importlib.import_module(SCHEMA_MODULE)
    missing: list[str] = []
    demand_list_type = demand_list_module.DemandListService
    review_type = review_module.DemandReviewService
    if not hasattr(demand_list_type, "create_derived_draft_in_transaction"):
        missing.append(
            "DemandListService.create_derived_draft_in_transaction"
        )
    if not hasattr(demand_list_module, "DemandListDerivedItemOverride"):
        missing.append("DemandListDerivedItemOverride")
    if not hasattr(review_type, "derive"):
        missing.append("DemandReviewService.derive")
    if not hasattr(schema, "DemandReviewDeriveRead"):
        missing.append("DemandReviewDeriveRead")
    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: {', '.join(missing)}",
            pytrace=False,
        )
    return demand_list_module, review_module


def _create_ready_review(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> tuple[DemandReview, DemandList]:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-DERIVE-RACE-{suffix}",
        name=f"Derive race scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-DERIVE-RACE-{suffix}",
        version_name=f"Derive race version {suffix}",
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
            "name": f"Derive race source {suffix}",
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
    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-DERIVE-RACE-{suffix}",
        name=f"Derive race spare {suffix}",
        unit="EA",
    )
    session.add(spare)
    session.flush()
    repository.add_item(
        session,
        tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        original_quantity=Decimal("10.000000"),
        final_quantity=Decimal("10.000000"),
        source_snapshot={"recommended_spare_quantity": "10.000000"},
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
    )
    review = DemandReview(
        tenant_id=tenant_id,
        source_demand_list_id=source.id,
        source_demand_list_version=source.version,
        source_lineage_id=source.lineage_id,
        source_version_number=source.version_number,
        status=DemandReviewStatus.READY_TO_DERIVE,
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="5" * 64,
        source_snapshot_json={"source_id": source.id},
        total_finding_count=0,
        blocking_finding_count=0,
        pending_finding_count=0,
        pending_blocking_finding_count=0,
    )
    session.add(review)
    session.flush()
    return review, source


def _derived_count(session: Session, source: DemandList) -> int:
    return len(
        list(
            session.scalars(
                select(DemandList).where(
                    DemandList.tenant_id == source.tenant_id,
                    DemandList.lineage_id == source.lineage_id,
                    DemandList.id != source.id,
                )
            ).all()
        )
    )


def test_review_lock_is_acquired_before_source_lock(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, review_module = _task4_contract()
    review, source = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "LOCK-ORDER",
    )
    service = review_module.DemandReviewService()
    order: list[str] = []
    original_review_lock = service.repository.get_for_update
    original_source_lock = DemandListRepository.get_for_update

    def review_lock(*args, **kwargs):
        order.append("review")
        return original_review_lock(*args, **kwargs)

    def source_lock(self, *args, **kwargs):
        order.append("source")
        return original_source_lock(self, *args, **kwargs)

    monkeypatch.setattr(service.repository, "get_for_update", review_lock)
    monkeypatch.setattr(
        demand_list_module.DemandListRepository,
        "get_for_update",
        source_lock,
    )

    service.derive(
        session,
        actor_admin,
        review.id,
        expected_review_version=review.version,
        idempotency_key="task4-lock-order",
    )

    assert source.id is not None
    assert order[:2] == ["review", "source"]


def test_source_is_revalidated_after_review_lock_before_any_derived_write(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, review_module = _task4_contract()
    review, source = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "REVALIDATE",
    )
    service = review_module.DemandReviewService()
    original_review_lock = service.repository.get_for_update

    def review_lock(*args, **kwargs):
        locked = original_review_lock(*args, **kwargs)
        source.is_current = False
        source.version += 1
        session.flush()
        return locked

    monkeypatch.setattr(service.repository, "get_for_update", review_lock)

    with pytest.raises(AppException) as caught:
        service.derive(
            session,
            actor_admin,
            review.id,
            expected_review_version=review.version,
            idempotency_key="task4-revalidate",
        )

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"
    assert _derived_count(session, source) == 0
    assert demand_list_module.DemandListService is not None


def test_duplicate_derive_receipt_race_replays_single_winner(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, review_module = _task4_contract()
    review, source = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "DUPLICATE",
    )
    service = review_module.DemandReviewService()
    key = "task4-duplicate-race"
    original_review_version = review.version
    winner = service.derive(
        session,
        actor_admin,
        review.id,
        expected_review_version=original_review_version,
        idempotency_key=key,
    )
    receipt = session.scalar(
        select(DemandReviewEvent).where(
            DemandReviewEvent.review_id == review.id,
            DemandReviewEvent.command_type == DemandReviewCommandType.DERIVE,
            DemandReviewEvent.idempotency_key == key,
        )
    )
    assert receipt is not None
    session.expire_all()
    review_row = session.get(DemandReview, review.id)
    assert review_row is not None
    review_row.status = DemandReviewStatus.READY_TO_DERIVE
    review_row.derived_demand_list_id = None
    review_row.version = original_review_version
    session.commit()

    state = {"lookups": 0}
    original_find = service.repository.find_command_event

    def race_lookup(*args, **kwargs):
        state["lookups"] += 1
        if state["lookups"] == 1:
            return None
        return receipt

    def duplicate_event(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO demand_list_review_events",
            {"idempotency_key": key},
            Exception("duplicate derive receipt"),
        )

    monkeypatch.setattr(service.repository, "find_command_event", race_lookup)
    monkeypatch.setattr(service.repository, "append_event", duplicate_event)

    replay = service.derive(
        session,
        actor_admin,
        review.id,
        expected_review_version=original_review_version,
        idempotency_key=key,
    )

    assert state["lookups"] >= 2
    assert replay.derived_demand_list.id == winner.derived_demand_list.id
    assert _derived_count(session, source) == 1
    assert original_find is not None


def test_review_derive_racing_source_supersede_has_serialized_stale_outcome(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, review_module = _task4_contract()
    review, source = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "SUPERSEDE-RACE",
    )
    service = review_module.DemandReviewService()
    original_source_lock = DemandListRepository.get_for_update

    def source_lock(self, session_arg, tenant_id, demand_list_id):
        locked = original_source_lock(
            self,
            session_arg,
            tenant_id,
            demand_list_id,
        )
        assert locked is not None
        locked.is_current = False
        locked.version += 1
        session_arg.flush()
        return locked

    monkeypatch.setattr(
        demand_list_module.DemandListRepository,
        "get_for_update",
        source_lock,
    )

    with pytest.raises(AppException) as caught:
        service.derive(
            session,
            actor_admin,
            review.id,
            expected_review_version=review.version,
            idempotency_key="task4-source-race",
        )

    assert caught.value.code == "REVIEW_DERIVATION_CONFLICT"
    assert _derived_count(session, source) == 0


def test_stale_review_version_loses_before_source_lock_or_mutation(
    session: Session,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demand_list_module, review_module = _task4_contract()
    review, source = _create_ready_review(
        session,
        actor_admin.tenant_id,
        "STALE-REVIEW",
    )
    service = review_module.DemandReviewService()
    source_lock_calls = 0
    original_source_lock = DemandListRepository.get_for_update

    def source_lock(self, *args, **kwargs):
        nonlocal source_lock_calls
        source_lock_calls += 1
        return original_source_lock(self, *args, **kwargs)

    monkeypatch.setattr(
        demand_list_module.DemandListRepository,
        "get_for_update",
        source_lock,
    )

    with pytest.raises(AppException) as caught:
        service.derive(
            session,
            actor_admin,
            review.id,
            expected_review_version=review.version + 1,
            idempotency_key="task4-stale-review",
        )

    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert source_lock_calls == 0
    assert _derived_count(session, source) == 0
