from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from app.models import AISession
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

ROLE_DEPENDENCY_NAMES = {
    "require_viewer",
    "require_contributor",
    "require_admin",
}

AI_ROUTE_FILES = (
    Path("app/api/v1/ai/sessions.py"),
    Path("app/api/v1/ai/confirmations.py"),
    Path("app/api/v1/ai/models.py"),
    Path("app/api/v1/ai/reviews.py"),
    Path("app/api/v1/ai/reports.py"),
)

ROUTER_METHOD_NAMES = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
}


def _is_router_endpoint(
    decorator: ast.expr,
) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(
            decorator.func,
            ast.Attribute,
        )
        and isinstance(
            decorator.func.value,
            ast.Name,
        )
        and decorator.func.value.id == "router"
        and decorator.func.attr
        in ROUTER_METHOD_NAMES
    )


def _role_dependencies(
    function: ast.FunctionDef
    | ast.AsyncFunctionDef,
) -> list[str]:
    role_dependencies: list[str] = []
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    for argument in arguments:
        if argument.annotation is None:
            continue
        for node in ast.walk(
            argument.annotation
        ):
            if (
                isinstance(node, ast.Call)
                and isinstance(
                    node.func,
                    ast.Name,
                )
                and node.func.id == "Depends"
                and node.args
                and isinstance(
                    node.args[0],
                    ast.Name,
                )
                and node.args[0].id
                in ROLE_DEPENDENCY_NAMES
            ):
                role_dependencies.append(
                    node.args[0].id
                )
    return role_dependencies


def test_every_ai_route_declares_one_role_dependency() -> None:
    endpoint_count = 0

    for path in AI_ROUTE_FILES:
        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            ),
            filename=str(path),
        )
        for node in tree.body:
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue
            if not any(
                _is_router_endpoint(decorator)
                for decorator
                in node.decorator_list
            ):
                continue

            endpoint_count += 1
            role_dependencies = (
                _role_dependencies(node)
            )
            assert len(role_dependencies) == 1, (
                str(path),
                node.name,
                role_dependencies,
            )

    assert endpoint_count == 26


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        (
            "GET",
            "/api/v1/ai/model-routes",
            None,
        ),
        (
            "POST",
            "/api/v1/ai/sessions",
            {"title": "no token"},
        ),
        (
            "POST",
            (
                "/api/v1/ai/confirmations/"
                "1/reject"
            ),
            {"comment": "no token"},
        ),
        (
            "GET",
            "/api/v1/ai/reviews/1",
            None,
        ),
        (
            "GET",
            "/api/v1/ai/reports/1",
            None,
        ),
    ],
)
def test_ai_routes_reject_missing_internal_token(
    client: TestClient,
    method: str,
    path: str,
    json_body: dict | None,
) -> None:
    response = client.request(
        method,
        path,
        json=json_body,
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"]["code"]
        == "INTERNAL_TOKEN_INVALID"
    )


def test_viewer_cannot_create_ai_session(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    response = client.post(
        "/api/v1/ai/sessions",
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER
        ),
        json={"title": "read only"},
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_contributor_cannot_resolve_confirmation_or_finalize_report(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    headers = internal_auth_headers(
        role=MaintenanceRole.CONTRIBUTOR
    )

    rejected = client.post(
        (
            "/api/v1/ai/confirmations/"
            "1/reject"
        ),
        headers=headers,
        json={"comment": "not allowed"},
    )
    finalized = client.post(
        "/api/v1/ai/reports/1/finalize",
        headers=headers,
        json={},
    )

    assert rejected.status_code == 403
    assert finalized.status_code == 403


def test_session_creator_and_response_meta_come_from_actor(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-http",
        user_id="user-http",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-http",
    )

    response = client.post(
        "/api/v1/ai/sessions",
        headers=headers,
        json={"title": "actor route"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {
        "request_id": "request-http",
        "tenant_id": "tenant-http",
        "version": None,
    }
    row = session.scalar(
        select(AISession).where(
            AISession.id
            == body["data"]["id"]
        )
    )
    assert row is not None
    assert row.tenant_id == "tenant-http"
    assert row.created_by == "user-http"


def test_ai_routes_contain_no_legacy_identity_or_permissions() -> None:
    for path in AI_ROUTE_FILES:
        source = path.read_text(
            encoding="utf-8"
        )
        assert '"api-user"' not in source
        assert "'api-user'" not in source
        assert "permissions={" not in source
        assert "resolved_by=" not in source
        assert "created_by=" not in source
        assert "payload.actor" not in source


def test_ai_routers_do_not_directly_load_tenant_rows() -> None:
    for path in (
        Path("app/api/v1/ai/sessions.py"),
        Path("app/api/v1/ai/reviews.py"),
        Path("app/api/v1/ai/reports.py"),
    ):
        source = path.read_text(
            encoding="utf-8"
        )
        assert "session.get(" not in source


def test_ai_success_responses_include_actor_metadata() -> None:
    failures: list[str] = []

    for path in AI_ROUTE_FILES:
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
            if not any(
                _is_router_endpoint(decorator)
                for decorator in function.decorator_list
            ):
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
