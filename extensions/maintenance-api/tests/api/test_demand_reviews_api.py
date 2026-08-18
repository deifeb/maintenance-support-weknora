from __future__ import annotations

import pytest
from app.security.dependencies import get_actor

FEATURE_MARKER = "PLAN05_4C_TASK5_API_ROUTES_MISSING"
PREFIX = "/api/v1/reviews/demand-lists"

EXPECTED_ROUTES = {
    ("GET", PREFIX),
    ("POST", f"{PREFIX}/{{demand_list_id}}/run"),
    ("GET", f"{PREFIX}/{{review_id}}"),
    (
        "PUT",
        f"{PREFIX}/{{review_id}}/findings/{{finding_id}}/decision",
    ),
    ("POST", f"{PREFIX}/{{review_id}}/batch-decisions"),
    ("POST", f"{PREFIX}/{{review_id}}/derive"),
    ("POST", f"{PREFIX}/{{review_id}}/void"),
}


def _use_actor(client, actor) -> None:
    client.app.dependency_overrides[get_actor] = lambda: actor


def _actual_routes(client) -> set[tuple[str, str]]:
    openapi = client.app.openapi()
    return {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        if path.startswith(PREFIX)
        for method in operations
        if method in {"get", "post", "put"}
    }


def _require_routes(client) -> None:
    actual = _actual_routes(client)
    if actual != EXPECTED_ROUTES:
        pytest.fail(
            f"{FEATURE_MARKER}: expected={sorted(EXPECTED_ROUTES)}, "
            f"actual={sorted(actual)}",
            pytrace=False,
        )


def test_formal_review_route_inventory_is_exact(client) -> None:
    _require_routes(client)


def test_formal_review_routes_require_internal_actor(client) -> None:
    _require_routes(client)

    response = client.get(PREFIX)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INTERNAL_TOKEN_INVALID"


def test_viewer_can_list_formal_reviews(
    client,
    actor_viewer,
) -> None:
    _require_routes(client)
    _use_actor(client, actor_viewer)

    response = client.get(PREFIX)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["meta"]["tenant_id"] == actor_viewer.tenant_id
    assert body["meta"]["version"] is None


def test_viewer_cannot_run_or_decide_or_derive_or_void(
    client,
    actor_viewer,
) -> None:
    _require_routes(client)
    _use_actor(client, actor_viewer)
    headers = {"Idempotency-Key": "task5-viewer-forbidden"}

    requests = (
        (
            "post",
            f"{PREFIX}/41/run",
            {"expected_source_version": 1},
        ),
        (
            "put",
            f"{PREFIX}/51/findings/7/decision",
            {
                "expected_review_version": 1,
                "expected_finding_version": 1,
                "action": "REJECTED",
            },
        ),
        (
            "post",
            f"{PREFIX}/51/batch-decisions",
            {
                "expected_review_version": 1,
                "decisions": [
                    {
                        "finding_id": 7,
                        "expected_finding_version": 1,
                        "action": "REJECTED",
                    }
                ],
            },
        ),
        (
            "post",
            f"{PREFIX}/51/derive",
            {"expected_review_version": 1},
        ),
        (
            "post",
            f"{PREFIX}/51/void",
            {"expected_review_version": 1},
        ),
    )

    for method, path, payload in requests:
        response = getattr(client, method)(
            path,
            headers=headers,
            json=payload,
        )
        assert response.status_code == 403
        assert (
            response.json()["error"]["code"]
            == "INSUFFICIENT_MAINTENANCE_ROLE"
        )


def test_contributor_cannot_derive_or_void_formal_review(
    client,
    actor_contributor,
) -> None:
    _require_routes(client)
    _use_actor(client, actor_contributor)
    headers = {"Idempotency-Key": "task5-contributor-forbidden"}

    for action in ("derive", "void"):
        response = client.post(
            f"{PREFIX}/51/{action}",
            headers=headers,
            json={"expected_review_version": 1},
        )
        assert response.status_code == 403
        assert (
            response.json()["error"]["code"]
            == "INSUFFICIENT_MAINTENANCE_ROLE"
        )


def test_all_formal_review_writes_require_idempotency_key(
    client,
    actor_admin,
) -> None:
    _require_routes(client)
    _use_actor(client, actor_admin)

    requests = (
        (
            "post",
            f"{PREFIX}/41/run",
            {"expected_source_version": 1},
        ),
        (
            "put",
            f"{PREFIX}/51/findings/7/decision",
            {
                "expected_review_version": 1,
                "expected_finding_version": 1,
                "action": "REJECTED",
            },
        ),
        (
            "post",
            f"{PREFIX}/51/batch-decisions",
            {
                "expected_review_version": 1,
                "decisions": [
                    {
                        "finding_id": 7,
                        "expected_finding_version": 1,
                        "action": "REJECTED",
                    }
                ],
            },
        ),
        (
            "post",
            f"{PREFIX}/51/derive",
            {"expected_review_version": 1},
        ),
        (
            "post",
            f"{PREFIX}/51/void",
            {"expected_review_version": 1},
        ),
    )

    for method, path, payload in requests:
        response = getattr(client, method)(path, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_formal_review_write_body_rejects_untrusted_tenant_id(
    client,
    actor_admin,
) -> None:
    _require_routes(client)
    _use_actor(client, actor_admin)

    response = client.post(
        f"{PREFIX}/41/run",
        headers={"Idempotency-Key": "task5-untrusted-tenant"},
        json={
            "expected_source_version": 1,
            "tenant_id": "tenant-attacker",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_formal_and_ai_review_routes_are_distinct(client) -> None:
    _require_routes(client)
    paths = client.app.openapi()["paths"]

    assert PREFIX in paths
    assert "/api/v1/ai/reviews/demand-lists" in paths
    assert PREFIX != "/api/v1/ai/reviews/demand-lists"
