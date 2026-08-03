from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.models.enums import (
    CalculationDecisionType,
    DemandExecutionMode,
    DemandListStatus,
    ReliabilityModelType,
)
from app.schemas.common import PageData
from app.schemas.demand_list import (
    DemandListItemRead,
    DemandListRead,
    DemandListSummaryRead,
)
from app.security.dependencies import get_actor
from app.services.demand_list_service import (
    demand_list_service,
)

_ROUTE_PREFIX = "/api/v1/demand/demand-lists"


def _use_actor(client, actor) -> None:
    client.app.dependency_overrides[get_actor] = (
        lambda: actor
    )


def test_demand_list_route_inventory_is_exact(
    client,
) -> None:
    openapi = client.app.openapi()
    actual = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        if path.startswith(_ROUTE_PREFIX)
        for method in operations
        if method in {"get", "post", "put"}
    }

    assert actual == {
        ("POST", _ROUTE_PREFIX),
        ("GET", _ROUTE_PREFIX),
        (
            "GET",
            f"{_ROUTE_PREFIX}/{{demand_list_id}}",
        ),
        (
            "PUT",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/items/{item_id}"
            ),
        ),
        (
            "POST",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/submit"
            ),
        ),
        (
            "POST",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/confirm"
            ),
        ),
        (
            "POST",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/publish"
            ),
        ),
        (
            "POST",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/derive"
            ),
        ),
        (
            "POST",
            (
                f"{_ROUTE_PREFIX}/{{demand_list_id}}"
                "/void"
            ),
        ),
    }


def test_demand_list_routes_require_internal_actor(
    client,
) -> None:
    response = client.get(_ROUTE_PREFIX)

    assert response.status_code == 401
    assert (
        response.json()["detail"]["code"]
        == "INTERNAL_TOKEN_INVALID"
    )


def test_viewer_can_list_demand_lists(
    client,
    actor_viewer,
) -> None:
    _use_actor(client, actor_viewer)

    response = client.get(_ROUTE_PREFIX)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["meta"]["tenant_id"] == (
        actor_viewer.tenant_id
    )
    assert body["meta"]["version"] is None


@pytest.mark.parametrize(
    "path",
    [
        f"{_ROUTE_PREFIX}/41/confirm",
        f"{_ROUTE_PREFIX}/41/publish",
        f"{_ROUTE_PREFIX}/41/derive",
        f"{_ROUTE_PREFIX}/41/void",
    ],
)
def test_contributor_cannot_run_admin_lifecycle_actions(
    authenticated_client,
    path: str,
) -> None:
    body = {"expected_version": 1}
    if path.endswith("/confirm"):
        body["confirmation_note"] = "Approved"

    response = authenticated_client.post(
        path,
        headers={
            "Idempotency-Key": (
                "task4b-contributor-forbidden"
            )
        },
        json=body,
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_create_requires_idempotency_key(
    authenticated_client,
) -> None:
    response = authenticated_client.post(
        _ROUTE_PREFIX,
        json={
            "calculation_group_id": 9,
            "name": "Missing key",
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


@pytest.mark.parametrize(
    "action",
    [
        "submit",
        "confirm",
        "publish",
        "derive",
        "void",
    ],
)
def test_lifecycle_routes_require_idempotency_key(
    client,
    actor_admin,
    action: str,
) -> None:
    _use_actor(client, actor_admin)
    body = {"expected_version": 1}
    if action == "confirm":
        body["confirmation_note"] = "Approved"

    response = client.post(
        f"{_ROUTE_PREFIX}/41/{action}",
        json=body,
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


def test_confirm_requires_confirmation_note_not_note(
    client,
    actor_admin,
) -> None:
    _use_actor(client, actor_admin)

    response = client.post(
        f"{_ROUTE_PREFIX}/41/confirm",
        headers={
            "Idempotency-Key": (
                "task4b-confirm-old-field"
            )
        },
        json={
            "expected_version": 1,
            "note": "Outdated field",
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


def test_create_rejects_untrusted_tenant_body(
    authenticated_client,
) -> None:
    response = authenticated_client.post(
        _ROUTE_PREFIX,
        headers={
            "Idempotency-Key": (
                "task4b-tenant-injection"
            )
        },
        json={
            "calculation_group_id": 9,
            "name": "Tenant injection",
            "tenant_id": "tenant-b",
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=201",
        "status=NOT_A_STATUS",
    ],
)
def test_list_rejects_invalid_filters(
    client,
    actor_viewer,
    query: str,
) -> None:
    _use_actor(client, actor_viewer)

    response = client.get(
        f"{_ROUTE_PREFIX}?{query}"
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )
_FIXED_NOW = datetime(
    2026,
    8,
    1,
    12,
    0,
    tzinfo=timezone.utc,
)


def _demand_list_read(
    *,
    with_item: bool = False,
) -> DemandListRead:
    items: list[DemandListItemRead] = []
    if with_item:
        items.append(
            DemandListItemRead(
                id=501,
                demand_list_id=41,
                spare_part_id=7,
                spare_part_code_snapshot="SP-007",
                spare_part_name_snapshot="Hydraulic pump",
                spare_part_unit_snapshot="piece",
                criticality_level_snapshot="HIGH",
                source_calculation_group_id=9,
                source_group_child_id=11,
                source_calculation_id=13,
                source_calculation_run_id=17,
                source_result_id=19,
                reliability_model=(
                    ReliabilityModelType.EXPONENTIAL
                ),
                execution_mode=(
                    DemandExecutionMode.ANALYTICAL
                ),
                original_quantity=Decimal(
                    "10.250000"
                ),
                final_quantity=Decimal(
                    "12.500000"
                ),
                decision_type=(
                    CalculationDecisionType
                    .SYSTEM_RECOMMENDATION
                ),
                decision_reason="service level",
                decision_risk="LOW",
                requires_admin_confirmation=False,
                confirmed_by_admin=False,
                risk_rule_version="risk-v1",
                source_snapshot_json={
                    "source": "calculation",
                },
                decision_snapshot_json={
                    "decision": "recommend",
                },
                interval_snapshot_json=None,
                parameter_snapshot_json={
                    "service_level": "0.95",
                },
                warning_snapshot_json=[],
                inventory_snapshot_json={
                    "on_hand": "2",
                },
                version=1,
                created_at=_FIXED_NOW,
                updated_at=_FIXED_NOW,
            )
        )

    return DemandListRead(
        id=41,
        name="Demand list 41",
        description="API contract aggregate",
        lineage_id=(
            "11111111-2222-3333-4444-555555555555"
        ),
        version_number=1,
        derived_from_id=None,
        scenario_version_id=3,
        calculation_group_id=9,
        status=DemandListStatus.DRAFT,
        is_current=True,
        superseded_by_id=None,
        superseded_at=None,
        version=7,
        created_by_user_id="user-a",
        created_by_request_id="request-a",
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        submitted_by_user_id=None,
        submitted_by_request_id=None,
        submitted_at=None,
        confirmed_by_user_id=None,
        confirmed_by_request_id=None,
        confirmed_at=None,
        published_by_user_id=None,
        published_by_request_id=None,
        published_at=None,
        voided_by_user_id=None,
        voided_by_request_id=None,
        voided_at=None,
        items=items,
        events=[],
    )


def _empty_demand_list_page(
) -> PageData[DemandListSummaryRead]:
    return PageData[DemandListSummaryRead](
        items=[],
        page=1,
        page_size=20,
        total=0,
        pages=0,
    )


_AGGREGATE_ROUTE_CASES = [
    (
        "POST",
        _ROUTE_PREFIX,
        "create_from_group",
        {
            "calculation_group_id": 9,
            "name": "Aggregate metadata",
        },
        {
            "Idempotency-Key": (
                "task4d-create-metadata"
            ),
        },
        201,
    ),
    (
        "GET",
        f"{_ROUTE_PREFIX}/41",
        "get",
        None,
        None,
        200,
    ),
    (
        "PUT",
        f"{_ROUTE_PREFIX}/41/items/501",
        "update_item",
        {
            "expected_version": 7,
            "final_quantity": "12.500000",
            "adjustment_reason": "Approved",
        },
        None,
        200,
    ),
    (
        "POST",
        f"{_ROUTE_PREFIX}/41/submit",
        "submit",
        {"expected_version": 7},
        {
            "Idempotency-Key": (
                "task4d-submit-metadata"
            ),
        },
        200,
    ),
    (
        "POST",
        f"{_ROUTE_PREFIX}/41/confirm",
        "confirm",
        {
            "expected_version": 7,
            "confirmation_note": "Approved",
        },
        {
            "Idempotency-Key": (
                "task4d-confirm-metadata"
            ),
        },
        200,
    ),
    (
        "POST",
        f"{_ROUTE_PREFIX}/41/publish",
        "publish",
        {"expected_version": 7},
        {
            "Idempotency-Key": (
                "task4d-publish-metadata"
            ),
        },
        200,
    ),
    (
        "POST",
        f"{_ROUTE_PREFIX}/41/derive",
        "derive",
        {"expected_version": 7},
        {
            "Idempotency-Key": (
                "task4d-derive-metadata"
            ),
        },
        200,
    ),
    (
        "POST",
        f"{_ROUTE_PREFIX}/41/void",
        "void",
        {"expected_version": 7},
        {
            "Idempotency-Key": (
                "task4d-void-metadata"
            ),
        },
        200,
    ),
]


@pytest.mark.parametrize(
    (
        "http_method",
        "path",
        "service_method",
        "body",
        "headers",
        "expected_status",
    ),
    _AGGREGATE_ROUTE_CASES,
)
def test_single_aggregate_routes_include_actor_metadata(
    client,
    actor_admin,
    monkeypatch: pytest.MonkeyPatch,
    http_method: str,
    path: str,
    service_method: str,
    body: dict | None,
    headers: dict[str, str] | None,
    expected_status: int,
) -> None:
    _use_actor(client, actor_admin)
    aggregate = _demand_list_read()
    captured: dict[str, object] = {}

    def fake_service(
        *args,
        **kwargs,
    ):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return aggregate

    monkeypatch.setattr(
        demand_list_service,
        service_method,
        fake_service,
    )

    request_kwargs: dict[str, object] = {}
    if body is not None:
        request_kwargs["json"] = body
    if headers is not None:
        request_kwargs["headers"] = headers

    response = client.request(
        http_method,
        path,
        **request_kwargs,
    )

    assert response.status_code == expected_status
    payload = response.json()
    assert payload["data"]["version"] == 7
    assert payload["meta"]["version"] == (
        payload["data"]["version"]
    )
    assert payload["meta"]["tenant_id"] == (
        actor_admin.tenant_id
    )
    assert payload["meta"]["request_id"] == (
        actor_admin.request_id
    )
    assert captured["args"][1] is actor_admin


def test_list_response_metadata_is_actor_aware(
    client,
    actor_viewer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_actor(client, actor_viewer)

    monkeypatch.setattr(
        demand_list_service,
        "list",
        lambda *args, **kwargs: (
            _empty_demand_list_page()
        ),
    )

    response = client.get(_ROUTE_PREFIX)

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["version"] is None
    assert payload["meta"]["tenant_id"] == (
        actor_viewer.tenant_id
    )
    assert payload["meta"]["request_id"] == (
        actor_viewer.request_id
    )


def test_detail_serializes_decimal_quantities_as_strings(
    client,
    actor_viewer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_actor(client, actor_viewer)

    monkeypatch.setattr(
        demand_list_service,
        "get",
        lambda *args, **kwargs: (
            _demand_list_read(with_item=True)
        ),
    )

    response = client.get(
        f"{_ROUTE_PREFIX}/41"
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["original_quantity"] == "10.250000"
    assert item["final_quantity"] == "12.500000"
    assert not isinstance(
        item["final_quantity"],
        float,
    )


@pytest.mark.parametrize(
    ("service_method", "path"),
    [
        (
            "list",
            (
                f"{_ROUTE_PREFIX}"
                "?tenant_id=tenant-b"
            ),
        ),
        (
            "get",
            (
                f"{_ROUTE_PREFIX}/41"
                "?tenant_id=tenant-b"
            ),
        ),
    ],
)
def test_read_routes_ignore_untrusted_tenant_inputs(
    client,
    actor_viewer,
    monkeypatch: pytest.MonkeyPatch,
    service_method: str,
    path: str,
) -> None:
    _use_actor(client, actor_viewer)
    captured: dict[str, object] = {}

    def fake_service(
        *args,
        **kwargs,
    ):
        captured["actor"] = args[1]
        if service_method == "list":
            return _empty_demand_list_page()
        return _demand_list_read()

    monkeypatch.setattr(
        demand_list_service,
        service_method,
        fake_service,
    )

    response = client.get(
        path,
        headers={
            "X-Tenant-ID": "tenant-b",
        },
    )

    assert response.status_code == 200
    forwarded_actor = captured["actor"]
    assert forwarded_actor is actor_viewer
    assert forwarded_actor.tenant_id == "tenant-a"
    assert response.json()["meta"]["tenant_id"] == (
        "tenant-a"
    )


def test_conflict_details_are_preserved_by_global_handler(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_details = {
        "expected_version": 2,
        "actual_version": 3,
        "conflict_object": "demand_list",
        "retryable": False,
    }

    def raise_conflict(
        *args,
        **kwargs,
    ):
        raise ConflictError(
            "demand list version conflict",
            code="DEMAND_LIST_VERSION_CONFLICT",
            details=expected_details,
        )

    monkeypatch.setattr(
        demand_list_service,
        "update_item",
        raise_conflict,
    )

    response = authenticated_client.put(
        f"{_ROUTE_PREFIX}/41/items/501",
        json={
            "expected_version": 2,
            "final_quantity": "12.500000",
            "adjustment_reason": (
                "Concurrent update proof"
            ),
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert response.json()["error"]["details"] == (
        expected_details
    )
