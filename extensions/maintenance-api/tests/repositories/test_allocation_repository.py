from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import ModuleType

import pytest
from app.models import AllocationRuleVersion


def _repository_api() -> ModuleType:
    try:
        return importlib.import_module("app.repositories.allocation_repository")
    except ModuleNotFoundError as exc:
        if exc.name == "app.repositories.allocation_repository":
            pytest.fail(
                "Task 2 RED requires app.repositories.allocation_repository"
            )
        raise


def _rule(
    session,
    *,
    tenant_id: str,
    lineage_id: str,
    version_number: int,
    status: str = "DRAFT",
    warehouse_ids: tuple[int, ...] = (1,),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> AllocationRuleVersion:
    rule = AllocationRuleVersion(
        tenant_id=tenant_id,
        lineage_id=lineage_id,
        version_number=version_number,
        status=status,
        scope_json={"warehouse_ids": list(warehouse_ids)},
        effective_from=effective_from,
        effective_to=effective_to,
        hard_rules_json={"exclude_frozen": True},
        weights_json={"criticality": "1.000000"},
        normalization_json={"criticality": {"min": "0", "max": "1"}},
        change_reason=f"{lineage_id}-v{version_number}",
        version=1,
    )
    session.add(rule)
    session.flush()
    return rule


def test_repository_get_rule_is_tenant_scoped(session) -> None:
    repository = _repository_api().AllocationRepository()
    tenant_a = _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-a",
        version_number=1,
    )
    tenant_b = _rule(
        session,
        tenant_id="tenant-b",
        lineage_id="lineage-b",
        version_number=1,
    )

    assert repository.get_rule(session, "tenant-a", tenant_a.id).id == tenant_a.id
    assert repository.get_rule(session, "tenant-b", tenant_a.id) is None
    assert repository.get_rule(session, "tenant-a", tenant_b.id) is None


def test_repository_list_rules_never_leaks_other_tenants(session) -> None:
    repository = _repository_api().AllocationRepository()
    _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-a",
        version_number=1,
    )
    _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-c",
        version_number=1,
    )
    _rule(
        session,
        tenant_id="tenant-b",
        lineage_id="lineage-b",
        version_number=1,
    )

    rules = repository.list_rules(session, "tenant-a")

    assert {rule.tenant_id for rule in rules} == {"tenant-a"}
    assert {rule.lineage_id for rule in rules} == {"lineage-a", "lineage-c"}


def test_repository_overlap_query_respects_scope_and_effective_window(session) -> None:
    repository = _repository_api().AllocationRepository()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    matching = _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-match",
        version_number=1,
        status="PUBLISHED",
        warehouse_ids=(10,),
        effective_from=start,
        effective_to=start + timedelta(days=30),
    )
    _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-other-scope",
        version_number=1,
        status="PUBLISHED",
        warehouse_ids=(20,),
        effective_from=start,
        effective_to=start + timedelta(days=30),
    )
    _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-retired",
        version_number=1,
        status="RETIRED",
        warehouse_ids=(10,),
        effective_from=start,
        effective_to=start + timedelta(days=30),
    )
    _rule(
        session,
        tenant_id="tenant-b",
        lineage_id="lineage-other-tenant",
        version_number=1,
        status="PUBLISHED",
        warehouse_ids=(10,),
        effective_from=start,
        effective_to=start + timedelta(days=30),
    )

    overlaps = repository.find_overlapping_published_rules(
        session,
        tenant_id="tenant-a",
        scope_json={"warehouse_ids": [10]},
        effective_from=start + timedelta(days=5),
        effective_to=start + timedelta(days=10),
        exclude_rule_id=None,
    )

    assert [rule.id for rule in overlaps] == [matching.id]


def test_repository_overlap_query_treats_open_ended_ranges_as_overlapping(
    session,
) -> None:
    repository = _repository_api().AllocationRepository()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    open_ended = _rule(
        session,
        tenant_id="tenant-a",
        lineage_id="lineage-open",
        version_number=1,
        status="PUBLISHED",
        warehouse_ids=(10,),
        effective_from=start,
        effective_to=None,
    )

    overlaps = repository.find_overlapping_published_rules(
        session,
        tenant_id="tenant-a",
        scope_json={"warehouse_ids": [10]},
        effective_from=start + timedelta(days=365),
        effective_to=None,
        exclude_rule_id=None,
    )

    assert [rule.id for rule in overlaps] == [open_ended.id]

# PLAN05_4D_TASK6_RED_CONTRACTS
TASK6_FEATURE_MISSING = "PLAN05_4D_TASK6_FEATURE_MISSING"


def test_task6_repository_query_surface_is_explicit() -> None:
    from inspect import signature

    repository = _repository_api().AllocationRepository()
    required = {
        "list_rules_page": {"session", "tenant_id", "page", "page_size", "status", "lineage_id"},
        "get_rule_by_publish_idempotency_key": {
            "session",
            "tenant_id",
            "idempotency_key",
        },
        "get_plan": {"session", "tenant_id", "plan_id"},
        "list_plans_page": {
            "session",
            "tenant_id",
            "page",
            "page_size",
            "status",
            "source_demand_list_id",
            "rule_id",
        },
    }
    missing_methods = [name for name in required if not hasattr(repository, name)]
    if missing_methods:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: missing allocation repository API: "
            f"{', '.join(sorted(missing_methods))}",
            pytrace=False,
        )

    for name, parameters in required.items():
        actual = set(signature(getattr(repository, name)).parameters)
        assert parameters <= actual, (
            f"{TASK6_FEATURE_MISSING}: {name} parameters missing "
            f"{sorted(parameters - actual)}"
        )
