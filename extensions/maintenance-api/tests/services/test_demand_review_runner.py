from __future__ import annotations

import importlib
import inspect
from decimal import Decimal

import pytest
from app.core.exceptions import AppException
from app.models import (
    AIReviewFinding,
    AIReviewRun,
    CalculationGroup,
    DemandList,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.demand_review import DemandReview
from app.models.enums import (
    CalculationGroupStatus,
    DemandListStatus,
    DemandReviewSeverity,
)
from app.repositories.demand_list_repository import DemandListRepository
from app.security.actor import ActorContext
from app.services.snapshot_service import snapshot_service
from sqlalchemy import func, select
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK2_FEATURE_MISSING"
SERVICE_MODULE = "app.services.demand_review_service"
RULES_MODULE = "app.services.demand_review_rules"
SCHEMA_MODULE = "app.schemas.demand_review"

EXPECTED_RULE_CODES = {
    "COMPLETENESS",
    "CONFIGURATION_APPLICABILITY",
    "KIT_COMPLETENESS",
    "RATIO_CONSISTENCY",
    "MUTUAL_EXCLUSION",
    "COMMON_PART_DUPLICATION",
    "SUBSTITUTE_VALIDITY",
    "RELIABILITY_ANOMALY",
    "MODEL_ANOMALY",
    "INVENTORY_GAP",
    "EVIDENCE_VALIDITY",
}


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


def _service():
    return _future(SERVICE_MODULE).DemandReviewService()


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
        code=f"SC-RUN-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-RUN-{suffix}",
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
            "name": f"Run source {suffix}",
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

    spare = SparePart(
        tenant_id=tenant_id,
        code=f"SP-RUN-{suffix}",
        name=f"Spare {suffix}",
        unit="EA",
    )
    session.add(spare)
    session.flush()
    DemandListRepository().add_item(
        session,
        tenant_id,
        demand_list_id=source.id,
        spare_part_id=spare.id,
        original_quantity=Decimal("1.000000"),
        final_quantity=Decimal("1.000000"),
        source_snapshot={"source": suffix},
        spare_part_code_snapshot=spare.code,
        spare_part_name_snapshot=spare.name,
        spare_part_unit_snapshot=spare.unit,
    )
    session.flush()
    return source


def _run(
    session: Session,
    actor: ActorContext,
    source: DemandList,
    *,
    expected_source_version: int | None = None,
    idempotency_key: str = "run-key",
):
    return _service().run(
        session,
        actor,
        source.id,
        expected_source_version=(
            source.version
            if expected_source_version is None
            else expected_source_version
        ),
        idempotency_key=idempotency_key,
    )


@pytest.mark.parametrize(
    ("status", "is_current"),
    [
        (DemandListStatus.DRAFT, False),
        (DemandListStatus.CONFIRMED, False),
        (DemandListStatus.PUBLISHED, False),
    ],
)
def test_run_rejects_non_current_or_non_published_source(
    session: Session,
    actor_context,
    status: DemandListStatus,
    is_current: bool,
) -> None:
    source = _create_source(
        session,
        "tenant-a",
        f"STATUS-{status.value}",
        status=status,
        is_current=is_current,
    )
    with pytest.raises(AppException) as caught:
        _run(
            session,
            actor_context(tenant_id="tenant-a"),
            source,
        )
    assert caught.value.code == "DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED"


def test_run_hides_cross_tenant_source_as_not_found(
    session: Session,
    actor_context,
) -> None:
    source = _create_source(session, "tenant-b", "TENANT-B")
    with pytest.raises(AppException) as caught:
        _run(
            session,
            actor_context(tenant_id="tenant-a"),
            source,
        )
    assert caught.value.status_code == 404
    assert caught.value.code == "RESOURCE_NOT_FOUND"


def test_run_rejects_source_version_conflict(
    session: Session,
    actor_context,
) -> None:
    source = _create_source(session, "tenant-a", "VERSION")
    with pytest.raises(AppException) as caught:
        _run(
            session,
            actor_context(tenant_id="tenant-a"),
            source,
            expected_source_version=source.version + 1,
        )
    assert caught.value.code == "REVIEW_VERSION_CONFLICT"
    assert caught.value.details["conflict_object"] == "source_demand_list"


def test_run_requires_non_empty_idempotency_key(
    session: Session,
    actor_context,
) -> None:
    source = _create_source(session, "tenant-a", "EMPTY-KEY")
    with pytest.raises(AppException) as caught:
        _run(
            session,
            actor_context(tenant_id="tenant-a"),
            source,
            idempotency_key="   ",
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_run_key_and_hash_replays_original_snapshot(
    session: Session,
    actor_context,
) -> None:
    source = _create_source(session, "tenant-a", "REPLAY")
    actor = actor_context(tenant_id="tenant-a")
    first = _run(
        session,
        actor,
        source,
        idempotency_key="same-run-key",
    )
    second = _run(
        session,
        actor,
        source,
        idempotency_key="same-run-key",
    )

    assert second.model_dump(mode="json") == first.model_dump(mode="json")
    count = session.scalar(
        select(func.count())
        .select_from(DemandReview)
        .where(
            DemandReview.tenant_id == actor.tenant_id,
            DemandReview.source_demand_list_id == source.id,
        )
    )
    assert count == 1


def test_same_run_key_with_different_request_hash_is_rejected(
    session: Session,
    actor_context,
) -> None:
    source = _create_source(session, "tenant-a", "REUSED")
    actor = actor_context(tenant_id="tenant-a")
    _run(
        session,
        actor,
        source,
        idempotency_key="reused-run-key",
    )
    with pytest.raises(AppException) as caught:
        _run(
            session,
            actor,
            source,
            expected_source_version=source.version + 1,
            idempotency_key="reused-run-key",
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_run_request_hash_is_exact_canonical_command_payload() -> None:
    module = _future(SERVICE_MODULE)
    payload = {
        "command": "RUN",
        "demand_list_id": 41,
        "expected_source_version": 7,
    }
    expected = snapshot_service.canonical_hash(payload)
    assert module.DemandReviewService._run_request_hash(
        demand_list_id=41,
        expected_source_version=7,
    ) == expected


def test_rule_set_v1_is_exact_and_repeated_output_is_stable() -> None:
    rules = _future(RULES_MODULE)
    schema = _future(SCHEMA_MODULE)
    assert set(rules.RULE_CODES) == EXPECTED_RULE_CODES
    assert rules.SEVERITY_ORDER == {
        DemandReviewSeverity.CRITICAL: 0,
        DemandReviewSeverity.HIGH: 1,
        DemandReviewSeverity.MEDIUM: 2,
        DemandReviewSeverity.LOW: 3,
    }

    snapshot = schema.DemandReviewSnapshot(
        schema_version="1",
        captured_at="2026-08-17T00:00:00+00:00",
        request={
            "command": "RUN",
            "demand_list_id": 1,
            "expected_source_version": 1,
        },
        source_demand_list={
            "id": 1,
            "status": "PUBLISHED",
            "is_current": True,
        },
        source_items=(
            {
                "id": 7,
                "spare_part_id": 11,
                "final_quantity": "5.000000",
            },
        ),
        source_events=(),
        current_inventory=(),
        master_data_evidence={
            "parts_by_id": {},
            "spare_parts_by_id": {},
            "reliability_profiles_by_id": {},
            "configuration_versions_by_id": {},
            "configuration_items_by_id": {},
            "substitution_evidence": {
                "status": "UNAVAILABLE",
                "records": [],
                "reason": "NO_AUTHORITATIVE_RELATION",
            },
            "kit_evidence": {
                "status": "UNAVAILABLE",
                "records": [],
                "reason": "NO_AUTHORITATIVE_RELATION",
            },
        },
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="a" * 64,
    )
    first = rules.run_rules(snapshot)
    second = rules.run_rules(snapshot)
    assert first == second
    assert [finding.finding_key for finding in first] == [
        finding.finding_key for finding in second
    ]
    assert any(
        finding.rule_code == "EVIDENCE_VALIDITY"
        for finding in first
    )


def test_rule_order_is_null_last_and_never_uses_or_zero() -> None:
    module = _future(RULES_MODULE)
    source = inspect.getsource(module)
    assert "source_demand_list_item_id is None" in source
    assert "source_demand_list_item_id is not None" in source
    assert "source_demand_list_item_id or 0" not in source


def test_quantity_effect_identity_uses_source_item_id() -> None:
    module = _future(RULES_MODULE)
    source = inspect.getsource(module)
    assert "FINAL_QUANTITY:" in source
    assert "source_demand_list_item_id" in source


def test_formal_run_does_not_use_ai_review_persistence(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    _future(SERVICE_MODULE)
    source = _create_source(session, "tenant-a", "NO-AI")
    actor = actor_context(tenant_id="tenant-a")

    async def forbidden_ai_review(*args, **kwargs):
        del args, kwargs
        raise AssertionError("formal review invoked AI review service")

    ai_review_module = importlib.import_module(
        "app.services.ai_review_service"
    )
    monkeypatch.setattr(
        ai_review_module.AIReviewService,
        "create_demand_list_review",
        forbidden_ai_review,
    )

    before_runs = session.scalar(
        select(func.count()).select_from(AIReviewRun)
    )
    before_findings = session.scalar(
        select(func.count()).select_from(AIReviewFinding)
    )
    _run(
        session,
        actor,
        source,
        idempotency_key="formal-no-ai",
    )
    assert session.scalar(
        select(func.count()).select_from(AIReviewRun)
    ) == before_runs
    assert session.scalar(
        select(func.count()).select_from(AIReviewFinding)
    ) == before_findings
