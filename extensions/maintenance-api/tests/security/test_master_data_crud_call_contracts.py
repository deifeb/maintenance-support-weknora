from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

MASTER_DATA_ROOT = Path("app/api/v1/master_data")
DIRECT_SERVICE_TEST = Path("tests/services/test_services.py")

NO_ACTOR_SERVICE_CALLS = {
    ("master_data_import_service", "template_bytes"),
    ("master_data_import_service", "validate"),
    ("master_data_import_service", "execute"),
}


@dataclass(frozen=True)
class ServiceCall:
    path: Path
    function: ast.FunctionDef | ast.AsyncFunctionDef
    receiver: str
    method: str
    call: ast.Call


class _ServiceCallVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.function_stack: list[
            ast.FunctionDef | ast.AsyncFunctionDef
        ] = []
        self.calls: list[ServiceCall] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self.function_stack.append(node)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if (
            self.function_stack
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id.endswith("_service")
        ):
            self.calls.append(
                ServiceCall(
                    path=self.path,
                    function=self.function_stack[-1],
                    receiver=node.func.value.id,
                    method=node.func.attr,
                    call=node,
                )
            )
        self.generic_visit(node)


def _service_calls(path: Path) -> list[ServiceCall]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    visitor = _ServiceCallVisitor(path)
    visitor.visit(tree)
    return visitor.calls


def _function_actor_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    names: set[str] = set()
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]

    for argument in arguments:
        annotation = (
            ast.unparse(argument.annotation)
            if argument.annotation is not None
            else ""
        )
        if (
            "actor" in argument.arg.lower()
            or "ActorContext" in annotation
        ):
            names.add(argument.arg)

    return names


def _supplied_actor_expression(call: ast.Call) -> str | None:
    if len(call.args) >= 2:
        return ast.unparse(call.args[1])

    for keyword in call.keywords:
        if keyword.arg in {
            "actor",
            "actor_context",
            "context",
        }:
            return ast.unparse(keyword.value)

    return None


def _format_failure(item: ServiceCall) -> str:
    return (
        f"{item.path}:{item.call.lineno}: "
        f"{ast.unparse(item.call)}"
    )


def test_master_data_service_calls_supply_route_actor() -> None:
    failures: list[str] = []
    observed_no_actor_calls: set[tuple[str, str]] = set()

    for path in sorted(MASTER_DATA_ROOT.rglob("*.py")):
        for item in _service_calls(path):
            call_key = (item.receiver, item.method)
            if call_key in NO_ACTOR_SERVICE_CALLS:
                observed_no_actor_calls.add(call_key)
                continue

            actor_names = _function_actor_names(item.function)
            actor_expression = _supplied_actor_expression(
                item.call
            )
            if (
                not actor_names
                or actor_expression not in actor_names
            ):
                failures.append(_format_failure(item))

    assert observed_no_actor_calls == NO_ACTOR_SERVICE_CALLS
    assert failures == [], (
        f"{len(failures)} actor-aware route service calls "
        "omit the authenticated ActorContext:\n"
        + "\n".join(failures)
    )


def test_direct_service_calls_supply_explicit_actor() -> None:
    failures: list[str] = []

    for item in _service_calls(DIRECT_SERVICE_TEST):
        actor_names = _function_actor_names(item.function)
        actor_expression = _supplied_actor_expression(item.call)

        if (
            not actor_names
            or actor_expression not in actor_names
        ):
            failures.append(_format_failure(item))

    assert failures == [], (
        f"{len(failures)} actor-aware direct service calls "
        "omit an explicit ActorContext:\n"
        + "\n".join(failures)
    )

HTTP_ROLE_DEPENDENCIES = {
    "get": "require_viewer",
    "post": "require_contributor",
    "put": "require_contributor",
    "patch": "require_contributor",
    "delete": "require_admin",
}


def _route_http_method(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    methods = {
        decorator.func.attr
        for decorator in function.decorator_list
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in HTTP_ROLE_DEPENDENCIES
        )
    }
    assert len(methods) <= 1, (
        f"{function.name} has multiple HTTP route decorators: "
        f"{sorted(methods)}"
    )
    return next(iter(methods), None)


def _route_actor_dependency(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    matches: list[str] = []

    for argument in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]:
        if argument.annotation is None:
            continue

        annotation = ast.unparse(argument.annotation)
        if (
            argument.arg == "actor"
            and "ActorContext" in annotation
        ):
            matches.append(annotation)

    assert len(matches) <= 1, (
        f"{function.name} has multiple ActorContext parameters"
    )
    if not matches:
        return None

    annotation = matches[0]
    for dependency in {
        "require_viewer",
        "require_contributor",
        "require_admin",
    }:
        if dependency in annotation:
            return dependency

    return "<missing-role-dependency>"


def test_master_data_routes_use_http_role_dependencies() -> None:
    failures: list[str] = []
    route_count = 0

    for path in sorted(MASTER_DATA_ROOT.rglob("*.py")):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for function in tree.body:
            if not isinstance(
                function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue

            http_method = _route_http_method(function)
            if http_method is None:
                continue

            route_count += 1
            expected = HTTP_ROLE_DEPENDENCIES[http_method]
            actual = _route_actor_dependency(function)
            if actual != expected:
                failures.append(
                    f"{path}:{function.lineno}: "
                    f"{http_method.upper()} {function.name} "
                    f"expected {expected}, found {actual}"
                )

    assert route_count == 61
    assert failures == [], (
        f"{len(failures)} master-data routes omit the "
        "required HTTP-role ActorContext dependency:\n"
        + "\n".join(failures)
    )


def test_master_data_success_responses_include_actor_metadata(
) -> None:
    failures: list[str] = []

    for path in sorted(MASTER_DATA_ROOT.rglob("*.py")):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for function in tree.body:
            if not isinstance(
                function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue
            if _route_http_method(function) is None:
                continue
            for call in ast.walk(function):
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "success_response"
                ):
                    continue
                has_actor = any(
                    keyword.arg == "actor"
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id == "actor"
                    for keyword in call.keywords
                )
                if not has_actor:
                    failures.append(
                        f"{path}:{function.name}:{call.lineno}"
                    )

    assert failures == [], "\n".join(failures)
