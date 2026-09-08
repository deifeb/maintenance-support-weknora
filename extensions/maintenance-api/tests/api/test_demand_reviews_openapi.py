from __future__ import annotations

import pytest

FEATURE_MARKER = "PLAN05_4C_TASK5_OPENAPI_ROUTES_MISSING"
PREFIX = "/api/v1/reviews/demand-lists"

EXPECTED = {
    ("get", PREFIX),
    ("post", f"{PREFIX}/{{demand_list_id}}/run"),
    ("get", f"{PREFIX}/{{review_id}}"),
    (
        "put",
        f"{PREFIX}/{{review_id}}/findings/{{finding_id}}/decision",
    ),
    ("post", f"{PREFIX}/{{review_id}}/batch-decisions"),
    ("post", f"{PREFIX}/{{review_id}}/derive"),
    ("post", f"{PREFIX}/{{review_id}}/void"),
}


def _schema(client) -> dict:
    return client.app.openapi()


def _require_formal_paths(schema: dict) -> None:
    actual = {
        (method, path)
        for path, operations in schema["paths"].items()
        if path.startswith(PREFIX)
        for method in operations
        if method in {"get", "post", "put"}
    }
    if actual != EXPECTED:
        pytest.fail(
            f"{FEATURE_MARKER}: expected={sorted(EXPECTED)}, "
            f"actual={sorted(actual)}",
            pytrace=False,
        )


def test_formal_review_openapi_path_inventory_is_exact(client) -> None:
    schema = _schema(client)
    _require_formal_paths(schema)


def test_formal_review_writes_require_idempotency_header_in_openapi(
    client,
) -> None:
    schema = _schema(client)
    _require_formal_paths(schema)

    operations = (
        schema["paths"][f"{PREFIX}/{{demand_list_id}}/run"]["post"],
        schema["paths"][
            f"{PREFIX}/{{review_id}}/findings/{{finding_id}}/decision"
        ]["put"],
        schema["paths"][f"{PREFIX}/{{review_id}}/batch-decisions"]["post"],
        schema["paths"][f"{PREFIX}/{{review_id}}/derive"]["post"],
        schema["paths"][f"{PREFIX}/{{review_id}}/void"]["post"],
    )

    for operation in operations:
        headers = {
            parameter["name"]: parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
        }
        assert headers["Idempotency-Key"]["required"] is True


def test_formal_review_list_openapi_has_server_query_contract(
    client,
) -> None:
    schema = _schema(client)
    _require_formal_paths(schema)

    operation = schema["paths"][PREFIX]["get"]
    query_names = {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "query"
    }

    assert query_names == {
        "page",
        "page_size",
        "status",
        "source_demand_list_id",
        "sort_by",
        "sort_order",
    }
    assert "tenant_id" not in query_names


def test_formal_review_public_schemas_exclude_private_replay_fields(
    client,
) -> None:
    schema = _schema(client)
    _require_formal_paths(schema)
    components = schema["components"]["schemas"]

    for name in (
        "DemandReviewSummaryRead",
        "DemandReviewPublicRead",
        "DemandReviewDecisionRead",
        "DemandReviewEventRead",
    ):
        assert name in components

    summary = components["DemandReviewSummaryRead"]["properties"]
    public = components["DemandReviewPublicRead"]["properties"]
    decision = components["DemandReviewDecisionRead"]["properties"]
    event = components["DemandReviewEventRead"]["properties"]

    assert "tenant_id" not in summary
    assert "tenant_id" not in public
    assert "request_hash" not in decision
    assert "request_hash" not in event
    assert "response_snapshot_json" not in event


def test_formal_review_openapi_is_separate_from_ai_review_api(
    client,
) -> None:
    schema = _schema(client)
    _require_formal_paths(schema)

    assert "/api/v1/ai/reviews/demand-lists" in schema["paths"]
    assert PREFIX in schema["paths"]
