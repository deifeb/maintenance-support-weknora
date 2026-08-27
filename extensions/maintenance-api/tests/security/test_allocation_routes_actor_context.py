from __future__ import annotations

import ast
from pathlib import Path

import pytest

# PLAN05_4D_TASK6_RED_CONTRACTS
# PLAN05_4D_TASK6_GREEN_D_TEST_CONTRACT
TASK6_FEATURE_MISSING = "PLAN05_4D_TASK6_FEATURE_MISSING"

API_DIR = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "allocations"
)
EXPECTED_FUNCTIONS = {
    "list_rules": "get",
    "create_rule": "post",
    "simulate_rule": "post",
    "publish_rule": "post",
    "retire_rule": "post",
    "list_plans": "get",
    "create_plan": "post",
    "get_plan": "get",
    "preview_plan": "post",
    "edit_plan_line": "put",
    "confirm_plan": "post",
    "execute_plan": "post",
    "void_plan": "post",
    "regenerate_plan": "post",
}


def _route_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods = {
            decorator.func.attr
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "router"
            and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
        }
        if methods:
            assert len(methods) == 1
            functions.append((node, next(iter(methods))))
    return tree, functions


def _session_calls(function, names: set[str]) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "session"
        and node.func.attr in names
    ]


def test_task6_allocation_routes_are_thin_actor_scoped_outer_transaction_adapters() -> None:
    required_files = {
        "__init__.py",
        "common.py",
        "router.py",
        "rules.py",
        "plans.py",
    }
    actual_files = {path.name for path in API_DIR.glob("*.py")} if API_DIR.exists() else set()
    missing_files = required_files - actual_files
    if missing_files:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: missing allocations API files: "
            f"{sorted(missing_files)}",
            pytrace=False,
        )

    found: dict[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, str, Path]] = {}
    for path in (API_DIR / "rules.py", API_DIR / "plans.py"):
        tree, functions = _route_functions(path)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.models")
                assert not node.module.startswith("app.repositories")
        for function, method in functions:
            found[function.name] = (function, method, path)

    if set(found) != set(EXPECTED_FUNCTIONS):
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: allocation route functions mismatch; "
            f"expected={sorted(EXPECTED_FUNCTIONS)}, actual={sorted(found)}",
            pytrace=False,
        )

    for name, expected_method in EXPECTED_FUNCTIONS.items():
        function, method, path = found[name]
        assert method == expected_method, f"{path.name}:{name}"
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]
        assert all(argument.arg != "tenant_id" for argument in arguments)
        assert any(
            argument.arg == "_tenant_guard"
            for argument in arguments
        ), f"{path.name}:{name} missing tenant override guard"

        forbidden_reads = _session_calls(
            function,
            {"get", "execute", "scalar", "scalars", "flush", "rollback"},
        )
        assert forbidden_reads == [], f"{path.name}:{name} uses direct session persistence API"

        commits = _session_calls(function, {"commit"})
        if method == "get":
            assert commits == [], f"{path.name}:{name} GET must not commit"
        else:
            assert len(commits) == 1, f"{path.name}:{name} must have one outer commit"

        success_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "success_response"
        ]
        assert success_calls, f"{path.name}:{name} missing success_response"
        for call in success_calls:
            assert any(
                keyword.arg == "actor"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "actor"
                for keyword in call.keywords
            ), f"{path.name}:{name} success_response missing actor=actor"

    simulate, _, _ = found["simulate_rule"]
    commit_lines = [node.lineno for node in _session_calls(simulate, {"commit"})]
    executor_submit_lines = [
        node.lineno
        for node in ast.walk(simulate)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "submit"
        and isinstance(node.func.value, ast.Name)
        and "executor" in node.func.value.id.lower()
    ]
    assert len(commit_lines) == 1
    assert executor_submit_lines, "simulate_rule must enqueue through allocation executor"
    assert commit_lines[0] < min(executor_submit_lines), (
        "simulate_rule must commit durable PENDING before executor enqueue"
    )

    fail_safely_calls = [
        node
        for node in ast.walk(simulate)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fail_safely"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "allocation_simulation_service"
    ]
    assert len(fail_safely_calls) == 1, (
        "simulate_rule must persist FAILED when executor submission raises"
    )

    recovery_handlers = []
    for node in ast.walk(simulate):
        if not isinstance(node, ast.ExceptHandler):
            continue
        has_recovery = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "fail_safely"
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "allocation_simulation_service"
            for child in ast.walk(node)
        )
        re_raises = any(
            isinstance(child, ast.Raise)
            for child in ast.walk(node)
        )
        if has_recovery and re_raises:
            recovery_handlers.append(node)
    assert len(recovery_handlers) == 1, (
        "simulate_rule executor failure handler must fail_safely then raise"
    )
