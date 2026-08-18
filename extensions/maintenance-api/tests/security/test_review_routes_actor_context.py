from __future__ import annotations

import ast
from pathlib import Path

import pytest

FEATURE_MARKER = "PLAN05_4C_TASK5_ACTOR_ROUTE_MISSING"

API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
)
ROUTE_FILE = API_ROOT / "reviews" / "demand_lists.py"
ROLE_ALIASES = {"ViewerDep", "ContributorDep", "AdminDep"}
ROUTE_METHODS = {"get", "post", "put"}


def _tree() -> ast.Module:
    if not ROUTE_FILE.exists():
        pytest.fail(
            f"{FEATURE_MARKER}: {ROUTE_FILE}",
            pytrace=False,
        )
    return ast.parse(
        ROUTE_FILE.read_text(encoding="utf-8"),
        filename=str(ROUTE_FILE),
    )


def _routes(tree: ast.Module):
    rows = []
    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        methods = {
            decorator.func.attr
            for decorator in node.decorator_list
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in ROUTE_METHODS
            )
        }
        if methods:
            rows.append(node)
    return rows


def test_formal_review_routes_never_accept_tenant_id_argument() -> None:
    tree = _tree()
    failures = []
    for function in _routes(tree):
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]
        if any(argument.arg == "tenant_id" for argument in arguments):
            failures.append(function.name)

    assert failures == []


def test_formal_review_routes_do_not_access_repository_or_orm() -> None:
    tree = _tree()
    imported_modules = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        module is not None
        and (
            module.startswith("app.repositories")
            or module.startswith("app.models")
        )
        for module in imported_modules
    )

    for function in _routes(tree):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "session"
                and node.func.attr in {"get", "execute", "scalar", "scalars"}
            ):
                pytest.fail(
                    f"route directly accesses session: {function.name}",
                    pytrace=False,
                )


def test_formal_review_routes_leave_transactions_to_service() -> None:
    tree = _tree()

    for function in _routes(tree):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "session"
                and node.func.attr in {"commit", "rollback", "flush"}
            ):
                pytest.fail(
                    f"route owns transaction: {function.name}",
                    pytrace=False,
                )


def test_formal_review_routes_use_named_role_aliases_and_actor_metadata(
) -> None:
    tree = _tree()
    aliases = {
        node.target.id
        for node in tree.body
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in ROLE_ALIASES
        )
    }
    assert aliases == ROLE_ALIASES

    for function in _routes(tree):
        annotations = [
            argument.annotation
            for argument in [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]
            if argument.annotation is not None
        ]
        names = {
            node.id
            for annotation in annotations
            for node in ast.walk(annotation)
            if isinstance(node, ast.Name)
        }
        assert names & ROLE_ALIASES

        success_calls = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "success_response"
            )
        ]
        assert success_calls
        assert all(
            any(
                keyword.arg == "actor"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "actor"
                for keyword in call.keywords
            )
            for call in success_calls
        )
