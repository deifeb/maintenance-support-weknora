from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal
from types import ModuleType, SimpleNamespace

import pytest
from app.core.exceptions import AppException
from app.models import AllocationRuleVersion


def _apis() -> tuple[ModuleType, ModuleType]:
    required = (
        "app.schemas.allocation",
        "app.services.allocation_rule_service",
    )
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        pytest.fail("Task 2 RED requires: " + ", ".join(missing))

    schema_api = importlib.import_module("app.schemas.allocation")
    service_api = importlib.import_module("app.services.allocation_rule_service")
    return schema_api, service_api


def _draft_command(schema_api, *, lineage_id: str = "lineage-1", **overrides):
    values = {
        "lineage_id": lineage_id,
        "scope": {"warehouse_ids": [10]},
        "effective_from": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "effective_to": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "hard_rules": {
            "exclude_frozen": True,
            "exclude_expired": True,
            "require_available": True,
        },
        "weights": {"criticality": "1.000000"},
        "normalization": {"criticality": {"min": "0", "max": "10"}},
        "change_reason": "Task 2 contract",
    }
    values.update(overrides)
    return schema_api.AllocationRuleDraftCommand(**values)


def _stored_rule(
    session,
    *,
    tenant_id: str = "tenant-a",
    lineage_id: str = "lineage-1",
    version_number: int = 1,
    status: str = "DRAFT",
) -> AllocationRuleVersion:
    rule = AllocationRuleVersion(
        tenant_id=tenant_id,
        lineage_id=lineage_id,
        version_number=version_number,
        status=status,
        scope_json={"warehouse_ids": [10]},
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        effective_to=datetime(2026, 9, 1, tzinfo=timezone.utc),
        hard_rules_json={"exclude_frozen": True},
        weights_json={"criticality": "1.000000"},
        normalization_json={"criticality": {"min": "0", "max": "10"}},
        change_reason="seed",
        version=1,
    )
    session.add(rule)
    session.flush()
    return rule


def test_rule_snapshot_hash_is_canonical_and_covers_publish_inputs() -> None:
    schema_api, _ = _apis()
    first = schema_api.RuleSnapshot(
        scope={"warehouse_ids": [10], "part_categories": ["critical"]},
        effective_from="2026-08-01T00:00:00+00:00",
        effective_to="2026-09-01T00:00:00+00:00",
        hard_rules={"exclude_frozen": True, "exclude_expired": True},
        weights={"criticality": "0.700000", "availability": "0.300000"},
        normalization={
            "criticality": {"min": "0", "max": "10"},
            "availability": {"min": "0", "max": "10"},
        },
    )
    reordered = schema_api.RuleSnapshot(
        scope={"part_categories": ["critical"], "warehouse_ids": [10]},
        effective_from="2026-08-01T00:00:00+00:00",
        effective_to="2026-09-01T00:00:00+00:00",
        hard_rules={"exclude_expired": True, "exclude_frozen": True},
        weights={"availability": "0.300000", "criticality": "0.700000"},
        normalization={
            "availability": {"max": "10", "min": "0"},
            "criticality": {"max": "10", "min": "0"},
        },
    )
    changed = schema_api.RuleSnapshot(
        scope={"warehouse_ids": [20], "part_categories": ["critical"]},
        effective_from="2026-08-01T00:00:00+00:00",
        effective_to="2026-09-01T00:00:00+00:00",
        hard_rules={"exclude_frozen": True, "exclude_expired": True},
        weights={"criticality": "0.700000", "availability": "0.300000"},
        normalization={
            "criticality": {"min": "0", "max": "10"},
            "availability": {"min": "0", "max": "10"},
        },
    )

    assert first.canonical_hash == reordered.canonical_hash
    assert first.canonical_hash != changed.canonical_hash


def test_contributor_can_create_draft_but_viewer_cannot(
    session,
    actor_contributor,
    actor_viewer,
) -> None:
    schema_api, service_api = _apis()
    service = service_api.AllocationRuleService()

    created = service.create_draft(
        session,
        actor_contributor,
        command=_draft_command(schema_api),
    )
    assert created.status == "DRAFT"
    assert created.tenant_id == actor_contributor.tenant_id
    assert created.version_number == 1

    with pytest.raises(AppException) as raised:
        service.create_draft(
            session,
            actor_viewer,
            command=_draft_command(schema_api, lineage_id="lineage-viewer"),
        )
    assert raised.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"


@pytest.mark.parametrize("source_status", ["SIMULATED", "PUBLISHED"])
def test_revising_non_draft_rule_creates_new_draft_version(
    session,
    actor_contributor,
    source_status,
) -> None:
    schema_api, service_api = _apis()
    source = _stored_rule(session, status=source_status)
    service = service_api.AllocationRuleService()

    revised = service.revise(
        session,
        actor_contributor,
        source.id,
        command=_draft_command(
            schema_api,
            lineage_id=source.lineage_id,
            change_reason=f"revise {source_status}",
        ),
    )

    session.refresh(source)
    assert source.status == source_status
    assert revised.id != source.id
    assert revised.lineage_id == source.lineage_id
    assert revised.version_number == source.version_number + 1
    assert revised.status == "DRAFT"


@pytest.mark.parametrize(
    ("simulation", "expected_reason"),
    [
        (None, "missing"),
        (SimpleNamespace(status="FAILED"), "not-completed"),
        (
            SimpleNamespace(
                status="COMPLETED",
                rule_hash="stale-hash",
                blockers=[],
                high_priority_regression=Decimal("0"),
            ),
            "hash-mismatch",
        ),
        (
            SimpleNamespace(
                status="COMPLETED",
                rule_hash="rule-hash",
                blockers=[{"code": "HARD_RULE_BLOCKER"}],
                high_priority_regression=Decimal("0"),
            ),
            "hard-rule-blocker",
        ),
        (
            SimpleNamespace(
                status="COMPLETED",
                rule_hash="rule-hash",
                blockers=[],
                high_priority_regression=Decimal("0.200000"),
            ),
            "regression-threshold",
        ),
    ],
)
def test_publish_gate_requires_fresh_successful_unblocked_simulation(
    simulation,
    expected_reason,
) -> None:
    _, service_api = _apis()
    service = service_api.AllocationRuleService()
    rule_snapshot = SimpleNamespace(canonical_hash="rule-hash")

    with pytest.raises(AppException) as raised:
        service.validate_publish_gate(
            rule_snapshot=rule_snapshot,
            latest_simulation=simulation,
            max_high_priority_regression=Decimal("0.100000"),
        )

    assert raised.value.code == "ALLOCATION_RULE_SIMULATION_REQUIRED"
    assert expected_reason in str(raised.value.details).lower()


def test_publish_and_retire_are_admin_only_and_retire_is_idempotent(
    session,
    actor_admin,
    actor_contributor,
) -> None:
    schema_api, service_api = _apis()
    service = service_api.AllocationRuleService()
    published = _stored_rule(session, status="PUBLISHED")

    retire_command = schema_api.AllocationRuleRetireCommand(
        expected_version=published.version,
    )
    with pytest.raises(AppException) as raised:
        service.retire(
            session,
            actor_contributor,
            published.id,
            command=retire_command,
            idempotency_key="retire-contributor",
        )
    assert raised.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"

    retired = service.retire(
        session,
        actor_admin,
        published.id,
        command=retire_command,
        idempotency_key="retire-admin",
    )
    replay = service.retire(
        session,
        actor_admin,
        published.id,
        command=retire_command,
        idempotency_key="retire-admin",
    )

    assert retired.status == "RETIRED"
    assert replay.id == retired.id
    assert replay.status == "RETIRED"


def test_publish_audit_uses_existing_rule_fields_not_a_seventh_event_table(
    session,
    actor_admin,
) -> None:
    schema_api, service_api = _apis()
    service = service_api.AllocationRuleService()
    rule = _stored_rule(session, status="SIMULATED")

    published = service.publish_prevalidated(
        session,
        actor_admin,
        rule.id,
        command=schema_api.AllocationRulePublishCommand(
            expected_version=rule.version,
        ),
        idempotency_key="publish-audit",
    )

    assert published.status == "PUBLISHED"
    assert published.published_by_user_id == actor_admin.user_id
    assert published.published_by_request_id == actor_admin.request_id
    assert published.published_at is not None

# PLAN05_4D_TASK6_RED_CONTRACTS
TASK6_FEATURE_MISSING = "PLAN05_4D_TASK6_FEATURE_MISSING"


def _task6_publish_contract():
    schema_api, service_api = _apis()
    missing_schema = [
        name for name in ("AllocationRuleActionResult",)
        if not hasattr(schema_api, name)
    ]
    required_columns = {
        "publish_idempotency_key",
        "publish_request_hash",
        "publish_response_snapshot_json",
    }
    missing_columns = required_columns - set(AllocationRuleVersion.__table__.c.keys())
    if missing_schema or missing_columns:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: strict rule publish receipt contract missing; "
            f"schema={missing_schema}, columns={sorted(missing_columns)}",
            pytrace=False,
        )
    return schema_api, service_api


def test_task6_rule_publish_same_key_same_hash_replays_exact_response(
    session,
    actor_admin,
) -> None:
    schema_api, service_api = _task6_publish_contract()
    service = service_api.AllocationRuleService()
    rule = _stored_rule(session, status="SIMULATED")
    command = schema_api.AllocationRulePublishCommand(expected_version=rule.version)

    first = service.publish_prevalidated(
        session,
        actor_admin,
        rule.id,
        command=command,
        idempotency_key="task6-publish-replay",
    )
    session.flush()
    session.refresh(rule)

    assert rule.publish_idempotency_key == "task6-publish-replay"
    assert isinstance(rule.publish_request_hash, str)
    assert len(rule.publish_request_hash) == 64
    expected_snapshot = {
        "rule_id": rule.id,
        "status": "PUBLISHED",
        "version": rule.version,
        "version_number": rule.version_number,
    }
    assert rule.publish_response_snapshot_json == expected_snapshot
    assert first.id == rule.id
    assert first.status == "PUBLISHED"

    replay = service.publish_prevalidated(
        session,
        actor_admin,
        rule.id,
        command=command,
        idempotency_key="task6-publish-replay",
    )
    assert replay.id == rule.id
    assert replay.status == "PUBLISHED"
    assert replay.version == rule.version


def test_task6_rule_publish_same_key_changed_hash_is_rejected_before_state(
    session,
    actor_admin,
) -> None:
    schema_api, service_api = _task6_publish_contract()
    service = service_api.AllocationRuleService()
    rule = _stored_rule(session, lineage_id="task6-key-reuse", status="SIMULATED")
    first_command = schema_api.AllocationRulePublishCommand(expected_version=rule.version)
    service.publish_prevalidated(
        session,
        actor_admin,
        rule.id,
        command=first_command,
        idempotency_key="task6-publish-reused",
    )

    with pytest.raises(AppException) as raised:
        service.publish_prevalidated(
            session,
            actor_admin,
            rule.id,
            command=schema_api.AllocationRulePublishCommand(expected_version=999),
            idempotency_key="task6-publish-reused",
        )
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert raised.value.details["retryable"] is False


def test_task6_rule_publish_missing_stored_response_is_not_reconstructed(
    session,
    actor_admin,
) -> None:
    schema_api, service_api = _task6_publish_contract()
    service = service_api.AllocationRuleService()
    rule = _stored_rule(session, lineage_id="task6-missing-response", status="SIMULATED")
    command = schema_api.AllocationRulePublishCommand(expected_version=rule.version)
    service.publish_prevalidated(
        session,
        actor_admin,
        rule.id,
        command=command,
        idempotency_key="task6-publish-missing-response",
    )
    rule.publish_response_snapshot_json = None
    session.flush()

    with pytest.raises(AppException) as raised:
        service.publish_prevalidated(
            session,
            actor_admin,
            rule.id,
            command=command,
            idempotency_key="task6-publish-missing-response",
        )
    assert raised.value.code == "IDEMPOTENT_RESPONSE_UNAVAILABLE"
    assert raised.value.details["retryable"] is False
