from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from app.security.actor import MaintenanceRole

# PLAN05_4D_TASK6_RED_CONTRACTS
TASK6_FEATURE_MISSING = "PLAN05_4D_TASK6_FEATURE_MISSING"

EXPECTED_OPERATIONS = {
    ("get", "/api/v1/allocations/rules"),
    ("post", "/api/v1/allocations/rules"),
    ("post", "/api/v1/allocations/rules/{rule_id}/simulate"),
    ("post", "/api/v1/allocations/rules/{rule_id}/publish"),
    ("post", "/api/v1/allocations/rules/{rule_id}/retire"),
    ("get", "/api/v1/allocations/plans"),
    ("post", "/api/v1/allocations/plans"),
    ("get", "/api/v1/allocations/plans/{plan_id}"),
    ("post", "/api/v1/allocations/plans/{plan_id}/preview"),
    ("put", "/api/v1/allocations/plans/{plan_id}/lines/{line_id}"),
    ("post", "/api/v1/allocations/plans/{plan_id}/confirm"),
    ("post", "/api/v1/allocations/plans/{plan_id}/execute"),
    ("post", "/api/v1/allocations/plans/{plan_id}/void"),
    ("post", "/api/v1/allocations/plans/{plan_id}/regenerate"),
}
STRICT_IDEMPOTENCY = {
    ("post", "/api/v1/allocations/rules/{rule_id}/simulate"),
    ("post", "/api/v1/allocations/rules/{rule_id}/publish"),
    ("post", "/api/v1/allocations/plans"),
    ("post", "/api/v1/allocations/plans/{plan_id}/confirm"),
    ("post", "/api/v1/allocations/plans/{plan_id}/execute"),
    ("post", "/api/v1/allocations/plans/{plan_id}/regenerate"),
}


def _schema() -> dict[str, Any]:
    from app.main import create_app

    schema = create_app().openapi()
    actual = {
        (method, path)
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/allocations")
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    if actual != EXPECTED_OPERATIONS:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: allocation route inventory mismatch; "
            f"expected={sorted(EXPECTED_OPERATIONS)}, actual={sorted(actual)}",
            pytrace=False,
        )
    return schema


def _operation(schema: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    return schema["paths"][path][method]


def _deref(schema: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    current = value
    seen: set[str] = set()
    while "$ref" in current:
        ref = current["$ref"]
        if ref in seen:
            raise AssertionError(f"cyclic OpenAPI ref: {ref}")
        seen.add(ref)
        name = ref.rsplit("/", 1)[-1]
        current = schema["components"]["schemas"][name]
    return current


def _request_properties(
    schema: dict[str, Any],
    method: str,
    path: str,
) -> set[str]:
    operation = _operation(schema, method, path)
    body = operation.get("requestBody")
    if body is None:
        return set()
    media = body["content"]["application/json"]["schema"]
    resolved = _deref(schema, media)
    return set(resolved.get("properties", {}))


def test_task6_allocations_openapi_exposes_exact_14_routes() -> None:
    schema = _schema()
    assert not any(
        path.startswith("/api/v1/allocations") and "stream" in path
        for path in schema["paths"]
    )


def test_task6_allocation_list_routes_use_envelope_and_reject_tenant_override(
    client,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _schema()
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        role=MaintenanceRole.VIEWER,
        request_id="task6-list-read",
    )
    for path in ("/api/v1/allocations/rules", "/api/v1/allocations/plans"):
        response = client.get(path, headers=headers, params={"page": 1, "page_size": 20})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert payload["meta"]["tenant_id"] == "tenant-a"
        assert payload["meta"]["request_id"] == "task6-list-read"
        assert payload["data"]["items"] == []
        assert payload["data"]["page"] == 1
        assert payload["data"]["page_size"] == 20
        assert payload["data"]["total"] == 0

        override = client.get(
            path,
            headers=headers,
            params={"tenant_id": "tenant-b"},
        )
        assert override.status_code == 422

    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="task6-body-tenant-override",
    )
    body_override = client.post(
        "/api/v1/allocations/rules",
        headers=contributor_headers,
        json={
            "lineage_id": "task6-tenant-override",
            "change_reason": "tenant override must be rejected",
            "scope": {},
            "effective_from": None,
            "effective_to": None,
            "hard_rules": {},
            "weights": {"availability": "1.000000"},
            "normalization": {},
            "tenant_id": "tenant-b",
        },
    )
    assert body_override.status_code == 422


# PLAN05_4D_TASK6_GREEN_D_TEST_CONTRACT
def test_task6_action_specific_idempotency_and_progress_openapi_contract() -> None:
    schema = _schema()
    for method, path in EXPECTED_OPERATIONS:
        operation = _operation(schema, method, path)
        header = [
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
            and parameter.get("name") == "Idempotency-Key"
        ]
        if (method, path) in STRICT_IDEMPOTENCY:
            assert len(header) == 1
            assert header[0].get("required") is True
        else:
            assert header == []

        assert all(
            not (
                parameter.get("in") in {"query", "path"}
                and parameter.get("name") == "tenant_id"
            )
            for parameter in operation.get("parameters", [])
        )
        assert "tenant_id" not in _request_properties(schema, method, path)

    assert "expected_rule_version" in _request_properties(
        schema,
        "post",
        "/api/v1/allocations/rules/{rule_id}/simulate",
    )
    assert "expected_source_version" in _request_properties(
        schema,
        "post",
        "/api/v1/allocations/plans",
    )
    assert "expected_version" in _request_properties(
        schema,
        "post",
        "/api/v1/allocations/plans/{plan_id}/regenerate",
    )

    components = schema.get("components", {}).get("schemas", {})
    progress = components.get("AllocationSimulationProgressRead")
    summary = components.get("AllocationSimulationSummaryRead")
    results = components.get("AllocationSimulationResultsSummaryRead")
    if progress is None or summary is None or results is None:
        pytest.fail(
            f"{TASK6_FEATURE_MISSING}: simulation progress/summary OpenAPI schemas missing",
            pytrace=False,
        )
    assert set(progress.get("properties", {})) == {"phase", "percent"}
    assert {
        "id",
        "status",
        "version",
        "progress",
        "blockers",
        "results_summary",
    } <= set(summary.get("properties", {}))
    assert {
        "total_rows",
        "demand_item_count",
        "high_priority_regression",
    } <= set(results.get("properties", {}))
