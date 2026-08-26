from __future__ import annotations

import importlib

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy import Enum as SAEnum

FEATURE_MISSING = "PLAN05_4D_TASK1_FEATURE_MISSING"

ALLOCATION_TABLES = {
    "allocation_rule_versions",
    "allocation_simulations",
    "allocation_simulation_results",
    "allocation_plans",
    "allocation_plan_lines",
    "allocation_plan_events",
}

RULE_STATUSES = ("DRAFT", "SIMULATED", "PUBLISHED", "RETIRED")
SIMULATION_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
PLAN_STATUSES = (
    "DRAFT",
    "PREVIEWED",
    "CONFIRMED",
    "EXECUTING",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "VOIDED",
)

AMENDMENT_REQUIRED = "PLAN05_4D_TASK4_AMENDMENT_REQUIRED"


def _feature_missing(message: str) -> None:
    pytest.fail(f"{FEATURE_MISSING}: {message}", pytrace=False)


def _allocation_module():
    try:
        return importlib.import_module("app.models.allocation")
    except ModuleNotFoundError as exc:
        if exc.name == "app.models.allocation":
            _feature_missing("app.models.allocation does not exist")
        raise


def _allocation_classes():
    module = _allocation_module()
    names = (
        "AllocationRuleVersion",
        "AllocationSimulation",
        "AllocationSimulationResult",
        "AllocationPlan",
        "AllocationPlanLine",
        "AllocationPlanEvent",
    )
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        _feature_missing("allocation model classes are absent: " + ", ".join(missing))
    return tuple(getattr(module, name) for name in names)


def _table(model):
    table = getattr(model, "__table__", None)
    if table is None:
        _feature_missing(f"{model.__name__} has no SQLAlchemy table")
    return table


def _unique_column_sets(table) -> set[tuple[str, ...]]:
    result = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    result.update(
        tuple(index.columns.keys())
        for index in table.indexes
        if isinstance(index, Index) and index.unique
    )
    return result


def _foreign_key_sets(
    table,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    result: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        local_columns = tuple(constraint.columns.keys())
        remote_tables = {
            element.column.table.name
            for element in constraint.elements
        }
        if len(remote_tables) != 1:
            continue
        remote_columns = tuple(
            element.column.name
            for element in constraint.elements
        )
        result.add((local_columns, remote_tables.pop(), remote_columns))
    return result


def _normalized_sql(value) -> str:
    return " ".join(str(value).upper().split())


def _check_sql(table) -> tuple[str, ...]:
    return tuple(
        _normalized_sql(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )


def _assert_columns(table, expected: set[str]) -> None:
    missing = expected - set(table.c.keys())
    assert not missing, f"{table.name} missing columns: {sorted(missing)}"


def _assert_allowed_values(
    table,
    column_name: str,
    expected: tuple[str, ...],
) -> None:
    column_type = table.c[column_name].type
    if isinstance(column_type, SAEnum):
        assert tuple(column_type.enums) == expected
        assert column_type.native_enum is False
        assert column_type.create_constraint is True
        return

    checks = _check_sql(table)
    matching = [
        sql
        for sql in checks
        if column_name.upper() in sql
        and all(
            f"'{value}'" in sql or f'"{value}"' in sql
            for value in expected
        )
    ]
    assert matching, (
        f"{table.name}.{column_name} must have a database allowlist "
        f"for {expected}"
    )


def _assert_version_check(table) -> None:
    checks = _check_sql(table)
    assert any(
        "VERSION >= 1" in sql or "VERSION>=1" in sql
        for sql in checks
    ), f"{table.name} must enforce version >= 1"


def test_allocation_models_have_exact_table_names_and_public_exports() -> None:
    classes = _allocation_classes()
    tables = {_table(model).name for model in classes}
    assert tables == ALLOCATION_TABLES

    models_package = importlib.import_module("app.models")
    for model in classes:
        assert getattr(models_package, model.__name__, None) is model


def test_allocation_rule_metadata_enforces_versioned_status_contract() -> None:
    AllocationRuleVersion, *_ = _allocation_classes()
    rule = _table(AllocationRuleVersion)

    _assert_columns(
        rule,
        {
            "id",
            "tenant_id",
            "lineage_id",
            "version_number",
            "status",
            "scope_json",
            "effective_from",
            "effective_to",
            "hard_rules_json",
            "weights_json",
            "normalization_json",
            "change_reason",
            "version",
        },
    )

    unique_sets = _unique_column_sets(rule)
    assert ("tenant_id", "id") in unique_sets
    assert ("tenant_id", "lineage_id", "version_number") in unique_sets

    _assert_allowed_values(rule, "status", RULE_STATUSES)
    _assert_version_check(rule)


def test_allocation_simulation_metadata_is_tenant_safe_and_idempotent() -> None:
    (
        AllocationRuleVersion,
        AllocationSimulation,
        AllocationSimulationResult,
        _,
        _,
        _,
    ) = _allocation_classes()

    rule = _table(AllocationRuleVersion)
    simulation = _table(AllocationSimulation)
    result = _table(AllocationSimulationResult)

    _assert_columns(
        simulation,
        {
            "id",
            "tenant_id",
            "candidate_rule_id",
            "baseline_rule_id",
            "source_demand_list_id",
            "input_snapshot_json",
            "inventory_fingerprint",
            "status",
            "blockers_json",
            "idempotency_key",
            "request_hash",
            "version",
        },
    )
    _assert_columns(
        result,
        {
            "id",
            "tenant_id",
            "simulation_id",
            "demand_list_item_id",
            "candidate_balance_id",
            "baseline_rank",
            "candidate_rank",
            "baseline_score",
            "candidate_score",
            "score_delta",
            "reasons_json",
        },
    )

    assert ("tenant_id", "id") in _unique_column_sets(rule)
    simulation_unique = _unique_column_sets(simulation)
    assert ("tenant_id", "id") in simulation_unique
    assert ("tenant_id", "idempotency_key") in simulation_unique

    _assert_allowed_values(simulation, "status", SIMULATION_STATUSES)
    _assert_version_check(simulation)

    simulation_fks = _foreign_key_sets(simulation)
    assert (
        ("tenant_id", "candidate_rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in simulation_fks
    assert (
        ("tenant_id", "baseline_rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in simulation_fks
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in simulation_fks

    result_fks = _foreign_key_sets(result)
    assert (
        ("tenant_id", "simulation_id"),
        "allocation_simulations",
        ("tenant_id", "id"),
    ) in result_fks
    assert (
        ("tenant_id", "demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in result_fks
    assert (
        ("tenant_id", "candidate_balance_id"),
        "inventory_balances",
        ("tenant_id", "id"),
    ) in result_fks


def test_allocation_plan_metadata_is_tenant_safe_auditable_and_idempotent() -> None:
    (
        _,
        _,
        _,
        AllocationPlan,
        AllocationPlanLine,
        AllocationPlanEvent,
    ) = _allocation_classes()

    plan = _table(AllocationPlan)
    line = _table(AllocationPlanLine)
    event = _table(AllocationPlanEvent)

    _assert_columns(
        plan,
        {
            "id",
            "tenant_id",
            "source_demand_list_id",
            "source_demand_list_version",
            "rule_id",
            "inventory_fingerprint",
            "status",
            "idempotency_key",
            "request_hash",
            "version",
        },
    )
    _assert_columns(
        line,
        {
            "id",
            "tenant_id",
            "plan_id",
            "demand_list_item_id",
            "spare_part_id",
            "recommended_balance_id",
            "recommended_lot_id",
            "recommended_serial_item_id",
            "demand_quantity",
            "allocated_quantity",
            "gap_quantity",
            "risks_json",
            "manual_override_json",
            "expected_balance_version",
            "reservation_id",
            "result_json",
            "version",
        },
    )
    _assert_columns(
        event,
        {
            "id",
            "tenant_id",
            "plan_id",
            "event_type",
            "actor_user_id",
            "actor_roles_json",
            "request_id",
            "idempotency_key",
            "request_hash",
            "before_snapshot_json",
            "after_snapshot_json",
            "response_snapshot_json",
            "error_code",
            "occurred_at",
        },
    )

    plan_unique = _unique_column_sets(plan)
    assert ("tenant_id", "id") in plan_unique
    assert ("tenant_id", "idempotency_key") in plan_unique

    _assert_allowed_values(plan, "status", PLAN_STATUSES)
    _assert_version_check(plan)
    _assert_version_check(line)

    assert line.c.expected_balance_version.nullable is True, (
        f"{AMENDMENT_REQUIRED}: gap-only lines require nullable "
        "expected_balance_version"
    )
    line_checks = _check_sql(line)
    assert any(
        "EXPECTED_BALANCE_VERSION >= 1" in sql
        or "EXPECTED_BALANCE_VERSION>=1" in sql
        for sql in line_checks
    ), (
        f"{AMENDMENT_REQUIRED}: non-null expected balance versions "
        "must remain >= 1"
    )
    assert any(
        "RECOMMENDED_BALANCE_ID IS NULL" in sql
        and "EXPECTED_BALANCE_VERSION IS NULL" in sql
        and "RECOMMENDED_BALANCE_ID IS NOT NULL" in sql
        and "EXPECTED_BALANCE_VERSION IS NOT NULL" in sql
        for sql in line_checks
    ), (
        f"{AMENDMENT_REQUIRED}: recommended balance and expected "
        "balance version must be null/non-null together"
    )

    plan_fks = _foreign_key_sets(plan)
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in plan_fks
    assert (
        ("tenant_id", "rule_id"),
        "allocation_rule_versions",
        ("tenant_id", "id"),
    ) in plan_fks

    line_fks = _foreign_key_sets(line)
    assert (
        ("tenant_id", "plan_id"),
        "allocation_plans",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "recommended_balance_id"),
        "inventory_balances",
        ("tenant_id", "id"),
    ) in line_fks
    assert (
        ("tenant_id", "reservation_id"),
        "inventory_reservations",
        ("tenant_id", "id"),
    ) in line_fks

    event_fks = _foreign_key_sets(event)
    assert (
        ("tenant_id", "plan_id"),
        "allocation_plans",
        ("tenant_id", "id"),
    ) in event_fks
