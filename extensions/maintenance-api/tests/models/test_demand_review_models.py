from __future__ import annotations

import importlib
from enum import Enum as PyEnum

import pytest
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)

FEATURE_MISSING = "PLAN05_4C_TASK1_FEATURE_MISSING"

REVIEW_TABLES = {
    "demand_list_reviews",
    "demand_list_review_findings",
    "demand_list_review_decisions",
    "demand_list_review_events",
}

EXPECTED_ENUMS = {
    "DemandReviewStatus": (
        "CREATED",
        "RUNNING",
        "OPEN",
        "READY_TO_DERIVE",
        "DERIVED",
        "FAILED",
        "VOIDED",
    ),
    "DemandReviewSeverity": (
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ),
    "DemandReviewDecisionStatus": (
        "PENDING",
        "ACCEPTED",
        "REJECTED",
        "EDIT_ACCEPTED",
    ),
    "DemandReviewCommandType": (
        "RUN",
        "DECIDE_FINDING",
        "BATCH_DECIDE",
        "DERIVE",
        "VOID",
    ),
    "DemandReviewEventType": (
        "CREATED",
        "RUNNING",
        "OPENED",
        "FAILED",
        "DECIDED",
        "BATCH_DECIDED",
        "READY_TO_DERIVE",
        "DERIVED",
        "VOIDED",
    ),
}


def _feature_missing(message: str) -> None:
    pytest.fail(f"{FEATURE_MISSING}: {message}", pytrace=False)


def _enum_module():
    module = importlib.import_module("app.models.enums")
    missing = [name for name in EXPECTED_ENUMS if not hasattr(module, name)]
    if missing:
        _feature_missing(
            "formal Demand Review enums are absent: " + ", ".join(sorted(missing))
        )
    return module


def _formal_module():
    try:
        return importlib.import_module("app.models.demand_review")
    except ModuleNotFoundError as exc:
        if exc.name == "app.models.demand_review":
            _feature_missing("app.models.demand_review does not exist")
        raise


def _formal_classes():
    module = _formal_module()
    names = (
        "DemandReview",
        "DemandReviewFinding",
        "DemandReviewDecision",
        "DemandReviewEvent",
    )
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        _feature_missing("formal Demand Review models are absent: " + ", ".join(missing))
    return tuple(getattr(module, name) for name in names)


def _table(model):
    table = getattr(model, "__table__", None)
    if table is None:
        _feature_missing(f"{model.__name__} has no SQLAlchemy table")
    return table


def _unique_column_sets(table) -> set[tuple[str, ...]]:
    unique_sets = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    unique_sets.update(
        tuple(index.columns.keys())
        for index in table.indexes
        if isinstance(index, Index) and index.unique
    )
    return unique_sets


def _foreign_key_sets(
    table,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    result: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        local_columns = tuple(constraint.columns.keys())
        referred_tables = {element.column.table.name for element in constraint.elements}
        if len(referred_tables) != 1:
            continue
        remote_columns = tuple(element.column.name for element in constraint.elements)
        result.add((local_columns, referred_tables.pop(), remote_columns))
    return result


def _normalized_sql(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).upper().split())


def _check_sql(table) -> tuple[str, ...]:
    return tuple(
        _normalized_sql(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )


def _assert_allowed_values(table, column_name: str, expected: tuple[str, ...]) -> None:
    column = table.c[column_name]
    column_type = column.type
    if isinstance(column_type, SAEnum):
        assert tuple(column_type.enums) == expected
        assert column_type.native_enum is False
        assert column_type.create_constraint is True
        return

    checks = _check_sql(table)
    matching = [
        sql for sql in checks
        if column_name.upper() in sql
        and all(f"'{value}'" in sql or f'"{value}"' in sql for value in expected)
    ]
    assert matching, (
        f"{table.name}.{column_name} must have a database allowlist "
        f"for {expected}"
    )


def _partial_unique_index(table, *columns: str):
    for index in table.indexes:
        if not index.unique:
            continue
        if tuple(index.columns.keys()) != tuple(columns):
            continue
        sqlite_where = index.dialect_options["sqlite"].get("where")
        postgresql_where = index.dialect_options["postgresql"].get("where")
        if sqlite_where is not None or postgresql_where is not None:
            return index
    return None


def test_formal_review_enums_are_exact_and_independent_from_ai_review() -> None:
    module = _enum_module()

    for name, expected in EXPECTED_ENUMS.items():
        enum_type = getattr(module, name)
        assert issubclass(enum_type, PyEnum)
        assert tuple(value.value for value in enum_type) == expected
        assert not name.startswith("AI")

    ai_review_names = {
        name for name in dir(module)
        if name.startswith("AIReview")
    }
    assert not (set(EXPECTED_ENUMS) & ai_review_names)


def test_formal_review_models_have_exact_table_names_and_public_exports() -> None:
    (
        DemandReview,
        DemandReviewFinding,
        DemandReviewDecision,
        DemandReviewEvent,
    ) = _formal_classes()

    assert DemandReview.__tablename__ == "demand_list_reviews"
    assert DemandReviewFinding.__tablename__ == "demand_list_review_findings"
    assert DemandReviewDecision.__tablename__ == "demand_list_review_decisions"
    assert DemandReviewEvent.__tablename__ == "demand_list_review_events"

    models_package = importlib.import_module("app.models")
    for model in (
        DemandReview,
        DemandReviewFinding,
        DemandReviewDecision,
        DemandReviewEvent,
    ):
        assert getattr(models_package, model.__name__, None) is model


def test_formal_review_metadata_enforces_tenant_safe_identity_and_constraints() -> None:
    _enum_module()
    (
        DemandReview,
        DemandReviewFinding,
        DemandReviewDecision,
        DemandReviewEvent,
    ) = _formal_classes()

    from app.models.demand_list import DemandList, DemandListItem

    demand_list = _table(DemandList)
    demand_item = _table(DemandListItem)
    review = _table(DemandReview)
    finding = _table(DemandReviewFinding)
    decision = _table(DemandReviewDecision)
    event = _table(DemandReviewEvent)

    assert REVIEW_TABLES <= {
        review.name,
        finding.name,
        decision.name,
        event.name,
    }

    assert ("tenant_id", "id") in _unique_column_sets(demand_list)
    assert ("tenant_id", "id") in _unique_column_sets(demand_item)
    assert ("tenant_id", "id") in _unique_column_sets(review)
    assert ("tenant_id", "id") in _unique_column_sets(finding)

    demand_list_parent_indexes = {
        index.name: tuple(index.columns.keys())
        for index in demand_list.indexes
        if index.unique
    }
    demand_item_parent_indexes = {
        index.name: tuple(index.columns.keys())
        for index in demand_item.indexes
        if index.unique
    }
    assert demand_list_parent_indexes["uq_demand_lists_tenant_id_id"] == (
        "tenant_id",
        "id",
    )
    assert demand_item_parent_indexes["uq_demand_list_items_tenant_id_id"] == (
        "tenant_id",
        "id",
    )

    review_fks = _foreign_key_sets(review)
    assert (
        ("tenant_id", "source_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in review_fks
    assert (
        ("tenant_id", "derived_demand_list_id"),
        "demand_lists",
        ("tenant_id", "id"),
    ) in review_fks

    finding_fks = _foreign_key_sets(finding)
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in finding_fks
    assert (
        ("tenant_id", "source_demand_list_item_id"),
        "demand_list_items",
        ("tenant_id", "id"),
    ) in finding_fks

    decision_fks = _foreign_key_sets(decision)
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in decision_fks
    assert (
        ("tenant_id", "finding_id"),
        "demand_list_review_findings",
        ("tenant_id", "id"),
    ) in decision_fks

    event_fks = _foreign_key_sets(event)
    assert (
        ("tenant_id", "review_id"),
        "demand_list_reviews",
        ("tenant_id", "id"),
    ) in event_fks

    assert ("tenant_id", "review_id", "finding_key") in _unique_column_sets(finding)

    effect_index = _partial_unique_index(
        finding,
        "tenant_id",
        "review_id",
        "effect_key",
    )
    assert effect_index is not None
    effect_where = " ".join(
        filter(
            None,
            (
                _normalized_sql(effect_index.dialect_options["sqlite"].get("where")),
                _normalized_sql(
                    effect_index.dialect_options["postgresql"].get("where")
                ),
            ),
        )
    )
    assert "EFFECT_KEY IS NOT NULL" in effect_where

    command_index = _partial_unique_index(
        event,
        "tenant_id",
        "command_type",
        "idempotency_key",
    )
    assert command_index is not None
    command_where = " ".join(
        filter(
            None,
            (
                _normalized_sql(command_index.dialect_options["sqlite"].get("where")),
                _normalized_sql(
                    command_index.dialect_options["postgresql"].get("where")
                ),
            ),
        )
    )
    assert "IDEMPOTENCY_KEY IS NOT NULL" in command_where

    _assert_allowed_values(
        review,
        "status",
        EXPECTED_ENUMS["DemandReviewStatus"],
    )
    _assert_allowed_values(
        finding,
        "severity",
        EXPECTED_ENUMS["DemandReviewSeverity"],
    )
    _assert_allowed_values(
        finding,
        "decision_status",
        EXPECTED_ENUMS["DemandReviewDecisionStatus"],
    )

    review_checks = _check_sql(review)
    finding_checks = _check_sql(finding)
    decision_checks = _check_sql(decision)

    assert any("VERSION >= 1" in sql for sql in review_checks)
    assert any("VERSION >= 1" in sql for sql in finding_checks)

    for column_name in ("suggested_quantity", "final_quantity"):
        assert any(
            column_name.upper() in sql
            and "IS NULL" in sql
            and ">= 0" in sql
            for sql in decision_checks
        ), f"missing nonnegative nullable check for {column_name}"


def test_decision_and_event_rows_are_immutable_history_shapes() -> None:
    (
        _DemandReview,
        _DemandReviewFinding,
        DemandReviewDecision,
        DemandReviewEvent,
    ) = _formal_classes()

    from app.models.mixins import VersionedMixin

    assert not issubclass(DemandReviewDecision, VersionedMixin)
    assert not issubclass(DemandReviewEvent, VersionedMixin)

    decision_columns = set(_table(DemandReviewDecision).c.keys())
    event_columns = set(_table(DemandReviewEvent).c.keys())

    assert "version" not in decision_columns
    assert "updated_at" not in decision_columns
    assert "occurred_at" in decision_columns

    assert "version" not in event_columns
    assert "updated_at" not in event_columns
    assert "occurred_at" in event_columns
