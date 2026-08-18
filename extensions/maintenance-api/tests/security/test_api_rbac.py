from __future__ import annotations

import ast
from pathlib import Path

API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
)

ROLE_DEPENDENCIES = {
    "require_viewer",
    "require_contributor",
    "require_admin",
}
ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
}
EXCLUDED = {
    "__init__.py",
    "common.py",
    "router.py",
}
EXPECTED_COUNTS = {
    "master_data": 67,
    "demand": 64,
    "ai": 26,
    "inventory": 33,
    "reviews": 7,
}
MASTER_ROLE_BY_METHOD = {
    "get": "require_viewer",
    "post": "require_contributor",
    "put": "require_contributor",
    "patch": "require_contributor",
    "delete": "require_admin",
}
MASTER_ROLE_BY_FUNCTION = {
    "read_import_task": "require_contributor",
    "download_import_errors": "require_contributor",
    "create_inventory": "require_admin",
    "update_inventory": "require_admin",
    "adjust_inventory": "require_admin",
    "execute_import": "require_admin",
    "execute_import_task": "require_admin",
}
DEMAND_ROLE_BY_FUNCTION = {
    "create_draft": "require_contributor",
    "get_draft": "require_viewer",
    "save_draft": "require_contributor",
    "validate_draft": "require_contributor",
    "materialize_draft": "require_contributor",
    "list_scenarios": "require_viewer",
    "get_scenario": "require_viewer",
    "list_versions": "require_viewer",
    "get_version": "require_viewer",
    "full_version": "require_viewer",
    "create_scenario": "require_contributor",
    "update_scenario": "require_contributor",
    "create_version": "require_contributor",
    "update_version": "require_contributor",
    "validate_version": "require_contributor",
    "clone_version": "require_contributor",
    "add_stage": "require_contributor",
    "add_fleet_group": "require_contributor",
    "add_age_group": "require_contributor",
    "add_fleet_usage": "require_contributor",
    "add_override": "require_contributor",
    "add_shock": "require_contributor",
    "delete_scenario": "require_admin",
    "publish_version": "require_admin",
    "retire_version": "require_admin",
    "compare": "require_viewer",
    "list_calculations": "require_viewer",
    "get_calculation": "require_viewer",
    "get_status": "require_viewer",
    "result_items": "require_viewer",
    "runs": "require_viewer",
    "comparison": "require_viewer",
    "export": "require_viewer",
    "preview": "require_contributor",
    "submit": "require_contributor",
    "cancel": "require_contributor",
    "retry": "require_contributor",
    "replay": "require_contributor",
    "rerun_latest": "require_contributor",
    "list_profiles": "require_viewer",
    "get_profile": "require_viewer",
    "create_profile": "require_contributor",
    "update_profile": "require_contributor",
    "set_active": "require_contributor",
    "delete_profile": "require_admin",
    "cancel_running": "require_contributor",
    "compare_group": "require_viewer",
    "create_group": "require_contributor",
    "get_group": "require_viewer",
    "list_events": "require_viewer",
    "list_groups": "require_viewer",
    "recommend_models": "require_contributor",
    "retry_failed": "require_contributor",
    "save_item_decision": "require_contributor",
    "stream_events": "require_viewer",
    "create_demand_list": "require_contributor",
    "list_demand_lists": "require_viewer",
    "get_demand_list": "require_viewer",
    "update_demand_list_item": "require_contributor",
    "submit_demand_list": "require_contributor",
    "confirm_demand_list": "require_admin",
    "publish_demand_list": "require_admin",
    "derive_demand_list": "require_admin",
    "void_demand_list": "require_admin",
}

REVIEW_ROLE_BY_FUNCTION = {
    "list_demand_list_reviews": "require_viewer",
    "run_demand_list_review": "require_contributor",
    "get_demand_list_review": "require_viewer",
    "decide_demand_review_finding": "require_contributor",
    "batch_decide_demand_review_findings": "require_contributor",
    "derive_demand_list_from_review": "require_admin",
    "void_demand_list_review": "require_admin",
}

INVENTORY_ROLE_BY_FUNCTION = {
    "list_balances": "require_viewer",
    "get_balance": "require_viewer",
    "list_transactions": "require_viewer",
    "get_transaction": "require_viewer",
    "list_reservations": "require_viewer",
    "get_reservation": "require_viewer",
    "list_transfers": "require_viewer",
    "get_transfer": "require_viewer",
    "list_stocktakes": "require_viewer",
    "get_stocktake": "require_viewer",
    "create_reservation": "require_contributor",
    "issue_reservation": "require_contributor",
    "release_reservation": "require_contributor",
    "return_reservation": "require_contributor",
    "cancel_reservation": "require_contributor",
    "preview_operation": "require_admin",
    "execute_operation": "require_admin",
    "preview_reverse_operation": "require_admin",
    "execute_reverse_operation": "require_admin",
    "create_transfer": "require_admin",
    "preview_transfer_dispatch": "require_admin",
    "execute_transfer_dispatch": "require_admin",
    "preview_transfer_receive": "require_admin",
    "execute_transfer_receive": "require_admin",
    "cancel_transfer": "require_admin",
    "create_stocktake": "require_contributor",
    "start_stocktake": "require_contributor",
    "update_stocktake_line": "require_contributor",
    "review_stocktake": "require_contributor",
    "preview_stocktake_confirm": "require_admin",
    "execute_stocktake_confirm": "require_admin",
    "rebase_stocktake": "require_contributor",
    "cancel_stocktake": "require_contributor",
}

def _files(domain: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted((API_ROOT / domain).glob("*.py"))
        if path.name not in EXCLUDED
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )


def _aliases(tree: ast.Module) -> dict[str, ast.expr]:
    aliases: dict[str, ast.expr] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            aliases[node.targets[0].id] = node.value
    return aliases


def _method(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    found = {
        decorator.func.attr
        for decorator in function.decorator_list
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "router"
            and decorator.func.attr in ROUTE_METHODS
        )
    }
    assert len(found) <= 1
    return next(iter(found), None)


def _endpoints(
    path: Path,
) -> tuple[
    tuple[
        ast.FunctionDef | ast.AsyncFunctionDef,
        str,
        dict[str, ast.expr],
    ],
    ...,
]:
    tree = _tree(path)
    aliases = _aliases(tree)
    result = []
    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        method = _method(node)
        if method is not None:
            result.append((node, method, aliases))
    return tuple(result)


def _dependencies(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    aliases: dict[str, ast.expr],
) -> list[str]:
    result: list[str] = []
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    for argument in arguments:
        if argument.annotation is None:
            continue
        roots: list[ast.AST] = [argument.annotation]
        if (
            isinstance(argument.annotation, ast.Name)
            and argument.annotation.id in aliases
        ):
            roots.append(aliases[argument.annotation.id])
        for root in roots:
            for node in ast.walk(root):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Depends"
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                ):
                    result.append(node.args[0].id)
    return result


def _expected_role(
    domain: str,
    function_name: str,
    method: str,
) -> str | None:
    if domain == "master_data":
        return MASTER_ROLE_BY_FUNCTION.get(
            function_name,
            MASTER_ROLE_BY_METHOD[method],
        )
    if domain == "demand":
        return DEMAND_ROLE_BY_FUNCTION.get(function_name)
    if domain == "inventory":
        return INVENTORY_ROLE_BY_FUNCTION.get(function_name)
    if domain == "reviews":
        return REVIEW_ROLE_BY_FUNCTION.get(function_name)
    return None


def _success_calls(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "success_response"
        )
    ]


def _has_actor(call: ast.Call) -> bool:
    return any(
        keyword.arg == "actor"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "actor"
        for keyword in call.keywords
    )


def _uses_session_get(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "session"
        for node in ast.walk(function)
    )


def test_business_route_inventory_is_exact() -> None:
    counts: dict[str, int] = {}
    demand_functions: set[str] = set()
    inventory_functions: set[str] = set()
    review_functions: set[str] = set()

    for domain in EXPECTED_COUNTS:
        count = 0
        for path in _files(domain):
            rows = _endpoints(path)
            count += len(rows)
            if domain == "demand":
                demand_functions.update(
                    function.name
                    for function, _, _ in rows
                )
            if domain == "inventory":
                inventory_functions.update(
                    function.name
                    for function, _, _ in rows
                )
            if domain == "reviews":
                review_functions.update(
                    function.name
                    for function, _, _ in rows
                )
        counts[domain] = count

    assert counts == EXPECTED_COUNTS
    assert sum(counts.values()) == 197
    assert demand_functions == set(
        DEMAND_ROLE_BY_FUNCTION
    )
    assert inventory_functions == set(
        INVENTORY_ROLE_BY_FUNCTION
    )
    assert review_functions == set(
        REVIEW_ROLE_BY_FUNCTION
    )


def test_every_business_route_has_exactly_one_named_role_dependency(
) -> None:
    failures: list[str] = []

    for domain in EXPECTED_COUNTS:
        for path in _files(domain):
            for function, method, aliases in _endpoints(path):
                dependencies = _dependencies(
                    function,
                    aliases,
                )
                named = [
                    name
                    for name in dependencies
                    if name in ROLE_DEPENDENCIES
                ]
                expected = _expected_role(
                    domain,
                    function.name,
                    method,
                )

                if (
                    len(named) != 1
                    or "get_actor" in dependencies
                ):
                    failures.append(
                        f"{path.name}:{function.name}: "
                        f"{dependencies}"
                    )
                elif (
                    expected is not None
                    and named != [expected]
                ):
                    failures.append(
                        f"{path.name}:{function.name}: "
                        f"expected={expected}, actual={named}"
                    )

    assert failures == [], "\n".join(failures)


def test_business_routes_do_not_use_session_get() -> None:
    failures: list[str] = []

    for domain in EXPECTED_COUNTS:
        for path in _files(domain):
            for function, _, _ in _endpoints(path):
                if _uses_session_get(function):
                    failures.append(
                        f"{path.name}:{function.name}"
                    )

    assert failures == []


def test_business_success_responses_include_actor_metadata(
) -> None:
    failures: list[str] = []

    for domain in EXPECTED_COUNTS:
        for path in _files(domain):
            for function, _, _ in _endpoints(path):
                for call in _success_calls(function):
                    if not _has_actor(call):
                        failures.append(
                            f"{path.name}:{function.name}:"
                            f"{call.lineno}"
                        )

    assert failures == [], "\n".join(failures)


def test_inventory_read_routes_do_not_accept_tenant_id_argument() -> None:
    failures: list[str] = []

    for path in _files("inventory"):
        for function, _, _ in _endpoints(path):
            arguments = [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]
            if any(
                argument.arg == "tenant_id"
                for argument in arguments
            ):
                failures.append(
                    f"{path.name}:{function.name}"
                )

    assert failures == []