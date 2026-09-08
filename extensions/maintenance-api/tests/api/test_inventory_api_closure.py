from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient

INVENTORY_PREFIX = "/api/v1/inventory"

READ_ROUTES = {
    ("get", f"{INVENTORY_PREFIX}/balances"),
    ("get", f"{INVENTORY_PREFIX}/balances/{{identifier}}"),
    ("get", f"{INVENTORY_PREFIX}/transactions"),
    ("get", f"{INVENTORY_PREFIX}/transactions/{{identifier}}"),
    ("get", f"{INVENTORY_PREFIX}/reservations"),
    ("get", f"{INVENTORY_PREFIX}/reservations/{{identifier}}"),
    ("get", f"{INVENTORY_PREFIX}/transfers"),
    ("get", f"{INVENTORY_PREFIX}/transfers/{{identifier}}"),
    ("get", f"{INVENTORY_PREFIX}/stocktakes"),
    ("get", f"{INVENTORY_PREFIX}/stocktakes/{{identifier}}"),
}

WRITE_ROUTES = {
    "reservation_create": (
        "post",
        f"{INVENTORY_PREFIX}/reservations",
    ),
    "reservation_issue": (
        "post",
        f"{INVENTORY_PREFIX}/reservations/{{reservation_id}}/issue",
    ),
    "reservation_release": (
        "post",
        f"{INVENTORY_PREFIX}/reservations/{{reservation_id}}/release",
    ),
    "reservation_return": (
        "post",
        f"{INVENTORY_PREFIX}/reservations/{{reservation_id}}/return",
    ),
    "reservation_cancel": (
        "post",
        f"{INVENTORY_PREFIX}/reservations/{{reservation_id}}/cancel",
    ),
    "operation_preview": (
        "post",
        f"{INVENTORY_PREFIX}/operations/preview",
    ),
    "operation_execute": (
        "post",
        f"{INVENTORY_PREFIX}/operations/{{transaction_id}}/execute",
    ),
    "operation_reverse_preview": (
        "post",
        f"{INVENTORY_PREFIX}/operations/{{transaction_id}}/reverse/preview",
    ),
    "operation_reverse_execute": (
        "post",
        f"{INVENTORY_PREFIX}/operations/{{transaction_id}}/reverse/execute",
    ),
    "transfer_create": (
        "post",
        f"{INVENTORY_PREFIX}/transfers",
    ),
    "transfer_dispatch_preview": (
        "post",
        f"{INVENTORY_PREFIX}/transfers/{{transfer_id}}/dispatch/preview",
    ),
    "transfer_dispatch_execute": (
        "post",
        f"{INVENTORY_PREFIX}/transfers/{{transfer_id}}/dispatch/execute",
    ),
    "transfer_receive_preview": (
        "post",
        f"{INVENTORY_PREFIX}/transfers/{{transfer_id}}/receive/preview",
    ),
    "transfer_receive_execute": (
        "post",
        f"{INVENTORY_PREFIX}/transfers/{{transfer_id}}/receive/execute",
    ),
    "transfer_cancel": (
        "post",
        f"{INVENTORY_PREFIX}/transfers/{{transfer_id}}/cancel",
    ),
    "stocktake_create": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes",
    ),
    "stocktake_start": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/start",
    ),
    "stocktake_update_line": (
        "patch",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/lines/{{line_id}}",
    ),
    "stocktake_review": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/review",
    ),
    "stocktake_confirm_preview": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/confirm/preview",
    ),
    "stocktake_confirm_execute": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/confirm/execute",
    ),
    "stocktake_rebase": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/rebase",
    ),
    "stocktake_cancel": (
        "post",
        f"{INVENTORY_PREFIX}/stocktakes/{{stocktake_id}}/cancel",
    ),
}

EXPECTED_SURFACE = READ_ROUTES | set(WRITE_ROUTES.values())
WRITE_METHODS = {"post", "put", "patch", "delete"}

API_SOURCE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "inventory"
)
ROUTE_SOURCE_FILES = (
    API_SOURCE_ROOT / "queries.py",
    API_SOURCE_ROOT / "reservations.py",
    API_SOURCE_ROOT / "operations.py",
    API_SOURCE_ROOT / "transfers.py",
    API_SOURCE_ROOT / "stocktakes.py",
)

PRIVATE_API_FIELDS = {
    "_extensions",
    "preview_command",
    "confirmation_token_hash",
    "response_snapshot_json",
}


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    request_id: str,
    tenant_id: str = "tenant-a",
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = internal_auth_headers(
        tenant_id=tenant_id,
        user_id=f"admin-{tenant_id}",
        role=MaintenanceRole.ADMIN,
        request_id=request_id,
    )
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _concrete_path(path: str) -> str:
    return (
        path.replace("{identifier}", "1")
        .replace("{reservation_id}", "1")
        .replace("{transaction_id}", "1")
        .replace("{transfer_id}", "1")
        .replace("{stocktake_id}", "1")
        .replace("{line_id}", "1")
    )


def _payload(operation: str) -> dict[str, Any]:
    if operation == "reservation_create":
        return {
            "owner_type": "MANUAL",
            "owner_id": "slice9f-minimal",
            "spare_part_id": 1,
            "warehouse_id": 1,
            "requested_quantity": "1.0000",
            "allow_partial": False,
            "expected_balance_versions": {"1": 1},
            "as_of": "2026-08-15",
        }
    if operation == "reservation_issue":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "reservation_line_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }
    if operation == "reservation_release":
        return {
            "expected_version": 1,
            "lines": [],
        }
    if operation == "reservation_return":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "reservation_line_id": 1,
                    "issue_transaction_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }
    if operation == "reservation_cancel":
        return {"expected_version": 1}

    if operation == "operation_preview":
        return {
            "operation_type": "ADJUST",
            "balance_id": 1,
            "expected_balance_version": 1,
            "reason": "slice9f adjustment",
            "deltas": {
                "on_hand": "1.0000",
                "reserved": "0.0000",
                "damaged": "0.0000",
                "quarantined": "0.0000",
                "in_transit": "0.0000",
            },
        }
    if operation in {
        "operation_execute",
        "operation_reverse_execute",
    }:
        return {
            "expected_transaction_version": 1,
            "confirmation_token": "slice9f-token",
        }
    if operation == "operation_reverse_preview":
        return {
            "expected_transaction_version": 1,
            "reason": "slice9f reverse",
        }

    if operation == "transfer_create":
        return {
            "source_warehouse_id": 1,
            "source_location_id": 1,
            "target_warehouse_id": 1,
            "target_location_id": 2,
            "reference_type": "work_order",
            "reference_id": "WO-SLICE9F",
            "reason": "slice9f transfer",
            "lines": [
                {
                    "spare_part_id": 1,
                    "source_balance_id": 1,
                    "lot_id": None,
                    "serial_item_id": None,
                    "quantity": "1.0000",
                    "expected_source_version": 1,
                }
            ],
        }
    if operation in {
        "transfer_dispatch_preview",
        "transfer_cancel",
    }:
        return {"expected_version": 1}
    if operation in {
        "transfer_dispatch_execute",
        "transfer_receive_execute",
    }:
        return {
            "transaction_id": 1,
            "expected_transaction_version": 1,
            "confirmation_token": "slice9f-token",
        }
    if operation == "transfer_receive_preview":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "transfer_line_id": 1,
                    "quantity": "1.0000",
                }
            ],
        }

    if operation == "stocktake_create":
        return {
            "warehouse_id": 1,
            "location_id": 1,
        }
    if operation in {
        "stocktake_start",
        "stocktake_review",
        "stocktake_cancel",
        "stocktake_confirm_preview",
    }:
        return {"expected_version": 1}
    if operation == "stocktake_update_line":
        return {
            "expected_version": 1,
            "expected_line_version": 1,
            "counted_quantity": "1.0000",
        }
    if operation == "stocktake_confirm_execute":
        return {
            "transaction_id": 1,
            "expected_transaction_version": 1,
            "confirmation_token": "slice9f-token",
        }
    if operation == "stocktake_rebase":
        return {
            "expected_version": 1,
            "lines": [
                {
                    "line_id": 1,
                    "action": "RECOUNT",
                }
            ],
        }

    raise AssertionError(f"unsupported operation: {operation}")


def _request(
    client: TestClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
):
    if method == "get":
        return client.get(
            path,
            headers=headers,
        )
    if method == "patch":
        return client.patch(
            path,
            headers=headers,
            json=payload,
        )
    if method == "post":
        return client.post(
            path,
            headers=headers,
            json=payload,
        )
    raise AssertionError(f"unsupported method: {method}")


def _inventory_operations(
    client: TestClient,
) -> set[tuple[str, str]]:
    openapi = client.app.openapi()
    found: set[tuple[str, str]] = set()
    for path, row in openapi["paths"].items():
        if not path.startswith(INVENTORY_PREFIX):
            continue
        for method in row:
            normalized = method.lower()
            if normalized in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
            }:
                found.add((normalized, path))
    return found


def test_inventory_openapi_surface_is_exact_and_unique(
    client: TestClient,
) -> None:
    actual = _inventory_operations(client)
    assert actual == EXPECTED_SURFACE
    assert len(actual) == 33


def test_inventory_openapi_operation_ids_are_unique(
    client: TestClient,
) -> None:
    openapi = client.app.openapi()
    operation_ids: list[str] = []
    for method, path in sorted(EXPECTED_SURFACE):
        operation = openapi["paths"][path][method]
        operation_id = operation.get("operationId")
        assert isinstance(operation_id, str)
        assert operation_id
        operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))


def test_inventory_openapi_marks_every_write_idempotency_header_required(
    client: TestClient,
) -> None:
    openapi = client.app.openapi()
    failures: list[str] = []

    for operation, (method, path) in WRITE_ROUTES.items():
        parameters = openapi["paths"][path][method].get(
            "parameters",
            [],
        )
        header = next(
            (
                item
                for item in parameters
                if item.get("in") == "header"
                and str(item.get("name", "")).lower()
                == "idempotency-key"
            ),
            None,
        )
        if header is None:
            failures.append(
                f"{operation}: missing Idempotency-Key"
            )
            continue
        if header.get("required") is not True:
            failures.append(
                f"{operation}: optional Idempotency-Key"
            )

    assert failures == [], (
        "Task 9 Slice 9F OpenAPI must mark every "
        "inventory write Idempotency-Key required:\n"
        + "\n".join(failures)
    )


def test_inventory_missing_idempotency_error_contract_is_uniform(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[str] = []

    for operation, (method, path) in WRITE_ROUTES.items():
        request_id = f"slice9f-missing-key-{operation}"
        response = _request(
            client,
            method,
            _concrete_path(path),
            headers=_headers(
                internal_auth_headers,
                request_id=request_id,
            ),
            payload=_payload(operation),
        )
        body = response.json()
        error = body.get("error", {})

        if response.status_code != 422:
            failures.append(
                f"{operation}: status={response.status_code}"
            )
            continue
        if body.get("success") is not False:
            failures.append(
                f"{operation}: success envelope mismatch"
            )
        if error.get("code") != "IDEMPOTENCY_KEY_REQUIRED":
            failures.append(
                f"{operation}: code={error.get('code')}"
            )
        if error.get("request_id") != request_id:
            failures.append(
                f"{operation}: request_id={error.get('request_id')}"
            )
        details = error.get("details")
        if (
            not isinstance(details, dict)
            or details.get("retryable") is not False
        ):
            failures.append(
                f"{operation}: retryable details mismatch"
            )

    assert failures == [], "\n".join(failures)


def test_inventory_tenant_query_validation_preserves_request_id(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[str] = []

    for index, (method, path) in enumerate(
        sorted(EXPECTED_SURFACE)
    ):
        request_id = f"slice9f-tenant-query-{index}"
        concrete = _concrete_path(path)
        separator = "&" if "?" in concrete else "?"
        concrete = (
            f"{concrete}{separator}tenant_id=tenant-b"
        )
        payload = None
        if method in WRITE_METHODS:
            operation = next(
                key
                for key, value in WRITE_ROUTES.items()
                if value == (method, path)
            )
            payload = _payload(operation)

        response = _request(
            client,
            method,
            concrete,
            headers=_headers(
                internal_auth_headers,
                request_id=request_id,
                idempotency_key=(
                    f"slice9f-query-{request_id}"
                    if method in WRITE_METHODS
                    else None
                ),
            ),
            payload=payload,
        )
        body = response.json()
        error = body.get("error", {})

        if response.status_code != 422:
            failures.append(
                f"{method.upper()} {path}: "
                f"status={response.status_code}"
            )
            continue
        if body.get("success") is not False:
            failures.append(
                f"{method.upper()} {path}: "
                "success envelope mismatch"
            )
        if error.get("code") != "VALIDATION_ERROR":
            failures.append(
                f"{method.upper()} {path}: "
                f"code={error.get('code')}"
            )
        if error.get("request_id") != request_id:
            failures.append(
                f"{method.upper()} {path}: "
                "validation request_id missing"
            )

    assert failures == [], (
        "Task 9 Slice 9F validation errors must preserve "
        "authenticated request_id:\n"
        + "\n".join(failures)
    )


def test_inventory_tenant_body_validation_preserves_request_id(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    failures: list[str] = []

    for operation, (method, path) in WRITE_ROUTES.items():
        request_id = f"slice9f-tenant-body-{operation}"
        payload = {
            **_payload(operation),
            "tenant_id": "tenant-b",
        }
        response = _request(
            client,
            method,
            _concrete_path(path),
            headers=_headers(
                internal_auth_headers,
                request_id=request_id,
                idempotency_key=f"slice9f-body-{operation}",
            ),
            payload=payload,
        )
        body = response.json()
        error = body.get("error", {})

        if response.status_code != 422:
            failures.append(
                f"{operation}: status={response.status_code}"
            )
            continue
        if body.get("success") is not False:
            failures.append(
                f"{operation}: success envelope mismatch"
            )
        if error.get("code") != "VALIDATION_ERROR":
            failures.append(
                f"{operation}: code={error.get('code')}"
            )
        if error.get("request_id") != request_id:
            failures.append(
                f"{operation}: validation request_id missing"
            )

    assert failures == [], (
        "Task 9 Slice 9F body validation errors must preserve "
        "authenticated request_id:\n"
        + "\n".join(failures)
    )


def test_inventory_read_list_success_metadata_is_uniform(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    paths = (
        f"{INVENTORY_PREFIX}/balances",
        f"{INVENTORY_PREFIX}/transactions",
        f"{INVENTORY_PREFIX}/reservations",
        f"{INVENTORY_PREFIX}/transfers",
        f"{INVENTORY_PREFIX}/stocktakes",
    )
    failures: list[str] = []

    for index, path in enumerate(paths):
        request_id = f"slice9f-success-meta-{index}"
        response = client.get(
            path,
            headers=_headers(
                internal_auth_headers,
                request_id=request_id,
            ),
        )
        body = response.json()
        meta = body.get("meta", {})

        if response.status_code != 200:
            failures.append(
                f"{path}: status={response.status_code}"
            )
            continue
        if body.get("success") is not True:
            failures.append(
                f"{path}: success envelope mismatch"
            )
        if meta.get("request_id") != request_id:
            failures.append(
                f"{path}: request_id metadata mismatch"
            )
        if meta.get("tenant_id") != "tenant-a":
            failures.append(
                f"{path}: tenant_id metadata mismatch"
            )

    assert failures == [], "\n".join(failures)


def test_inventory_openapi_does_not_expose_private_transaction_fields(
    client: TestClient,
) -> None:
    openapi = client.app.openapi()
    schemas = (
        openapi.get("components", {})
        .get("schemas", {})
    )

    def schema_refs(value: Any) -> set[str]:
        refs: set[str] = set()
        if isinstance(value, dict):
            ref = value.get("$ref")
            if (
                isinstance(ref, str)
                and ref.startswith("#/components/schemas/")
            ):
                refs.add(ref.rsplit("/", 1)[-1])
            for child in value.values():
                refs.update(schema_refs(child))
        elif isinstance(value, list):
            for child in value:
                refs.update(schema_refs(child))
        return refs

    reachable: set[str] = set()
    pending: list[str] = []
    for method, path in sorted(EXPECTED_SURFACE):
        pending.extend(
            sorted(
                schema_refs(
                    openapi["paths"][path][method]
                )
            )
        )

    while pending:
        schema_name = pending.pop()
        if schema_name in reachable:
            continue
        reachable.add(schema_name)
        schema = schemas.get(schema_name)
        if schema is not None:
            pending.extend(
                sorted(schema_refs(schema))
            )

    leaked: list[str] = []
    for schema_name in sorted(reachable):
        schema = schemas.get(schema_name, {})
        properties = schema.get("properties", {})
        for field in PRIVATE_API_FIELDS:
            if field in properties:
                leaked.append(
                    f"{schema_name}.{field}"
                )

    assert leaked == []


def test_inventory_route_sources_use_tenant_guard_and_actor_metadata(
) -> None:
    failures: list[str] = []

    for path in ROUTE_SOURCE_FILES:
        assert path.exists(), path
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        aliases = {
            node.targets[0].id: node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }

        for node in tree.body:
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue

            route_decorators = [
                decorator
                for decorator in node.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(
                    decorator.func,
                    ast.Attribute,
                )
                and isinstance(
                    decorator.func.value,
                    ast.Name,
                )
                and decorator.func.value.id == "router"
                and decorator.func.attr in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                }
            ]
            if not route_decorators:
                continue

            arguments = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            names = {
                argument.arg
                for argument in arguments
            }
            if "tenant_id" in names:
                failures.append(
                    f"{path.name}:{node.name}: tenant_id arg"
                )
            if "_tenant_guard" not in names:
                failures.append(
                    f"{path.name}:{node.name}: "
                    "TenantGuardDep missing"
                )

            success_calls = [
                call
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "success_response"
            ]
            for call in success_calls:
                actor_keywords = [
                    keyword
                    for keyword in call.keywords
                    if keyword.arg == "actor"
                    and isinstance(
                        keyword.value,
                        ast.Name,
                    )
                    and keyword.value.id == "actor"
                ]
                if len(actor_keywords) != 1:
                    failures.append(
                        f"{path.name}:{node.name}: "
                        "success_response actor missing"
                    )

            guard_argument = next(
                (
                    argument
                    for argument in arguments
                    if argument.arg == "_tenant_guard"
                ),
                None,
            )
            if guard_argument is None:
                continue

            annotation = guard_argument.annotation
            if (
                isinstance(annotation, ast.Name)
                and annotation.id in aliases
            ):
                annotation = aliases[annotation.id]
            if annotation is None:
                failures.append(
                    f"{path.name}:{node.name}: "
                    "tenant guard annotation missing"
                )

    assert failures == [], "\n".join(failures)
