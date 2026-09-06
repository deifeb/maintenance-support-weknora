from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.core.exceptions import AppException
from app.models import (
    CalculationGroup,
    DemandReview,
    DemandReviewEvent,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.models.enums import CalculationGroupStatus, DemandListStatus
from app.repositories.demand_list_repository import DemandListRepository
from app.services.demand_review_service import DemandReviewService
from sqlalchemy import func, select
from sqlalchemy.orm import Session

LOCK_MARKER = "I1_FORMAL_RUN_SOURCE_LOCK_MISSING"
REVALIDATION_MARKER = "I1_FORMAL_RUN_LOCKED_REVALIDATION_MISSING"


def _source(session: Session, tenant_id: str, suffix: str):
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-READINESS-{suffix}",
        name=f"Readiness scenario {suffix}",
    )
    session.add(template)
    session.flush()

    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-READINESS-{suffix}",
        version_name=f"Readiness version {suffix}",
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
            "name": f"Readiness source {suffix}",
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


def test_formal_run_locks_source_before_authority_and_version_checks(
    session: Session,
    actor_contributor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(session, actor_contributor.tenant_id, "LOCK-ORDER")
    service = DemandReviewService()
    order: list[str] = []

    original_lock = service.demand_list_repository.get_for_update
    original_authority = service._require_source_authority
    original_version = service._require_source_version

    def source_lock(*args, **kwargs):
        order.append("lock")
        return original_lock(*args, **kwargs)

    def authority_check(source_arg):
        order.append("authority")
        return original_authority(source_arg)

    def version_check(source_arg, expected_source_version):
        order.append("version")
        return original_version(source_arg, expected_source_version)

    monkeypatch.setattr(
        service.demand_list_repository,
        "get_for_update",
        source_lock,
    )
    monkeypatch.setattr(service, "_require_source_authority", authority_check)
    monkeypatch.setattr(service, "_require_source_version", version_check)

    service.run(
        session,
        actor_contributor,
        source.id,
        expected_source_version=source.version,
        idempotency_key="readiness-red-run-lock-order",
    )

    assert order[:3] == ["lock", "authority", "version"], (
        f"{LOCK_MARKER}: formal run must lock the source before "
        f"authority/version validation; observed={order}"
    )


def test_formal_run_rejects_source_that_is_stale_at_locked_reread(
    session: Session,
    actor_contributor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(session, actor_contributor.tenant_id, "LOCKED-STALE")
    service = DemandReviewService()

    stale_locked_source = SimpleNamespace(
        id=source.id,
        status=DemandListStatus.PUBLISHED,
        is_current=False,
        version=source.version + 1,
    )

    monkeypatch.setattr(
        service.demand_list_repository,
        "get_for_update",
        lambda *args, **kwargs: stale_locked_source,
    )

    try:
        service.run(
            session,
            actor_contributor,
            source.id,
            expected_source_version=source.version,
            idempotency_key="readiness-red-run-locked-stale",
        )
    except AppException as exc:
        assert exc.code in {
            "DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED",
            "REVIEW_VERSION_CONFLICT",
        }
        assert session.scalar(
            select(func.count()).select_from(DemandReview)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(DemandReviewEvent)
        ) == 0
        return

    pytest.fail(
        f"{REVALIDATION_MARKER}: unlocked read may see current source, "
        "but a stale/non-current locked reread must reject before any "
        "authoritative review or command receipt is written",
        pytrace=False,
    )