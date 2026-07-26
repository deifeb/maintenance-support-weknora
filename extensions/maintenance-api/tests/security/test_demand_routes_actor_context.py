from __future__ import annotations

import ast
from pathlib import Path

import pytest
from app.models import (
    DemandCalculation,
    RepairProfile,
    SparePart,
)
from app.security.dependencies import get_actor
from sqlalchemy import select

_API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "demand"
)

_ROUTE_FUNCTIONS = {
    "calculations.py": {
        "preview",
        "submit",
        "list_calculations",
        "get_calculation",
        "get_status",
        "cancel",
        "retry",
        "replay",
        "rerun_latest",
        "result_items",
        "runs",
        "comparison",
        "export",
    },
    "repair_profiles.py": {
        "create_profile",
        "list_profiles",
        "get_profile",
        "update_profile",
        "set_active",
        "delete_profile",
    },
}

_SERVICE_NAMES = {
    "calculations.py": "calculation_service",
    "repair_profiles.py": "repair_service",
}

_DIRECT_CALCULATION_QUERIES = {
    "list_calculations",
    "result_items",
    "export",
}


def _tree(filename: str) -> ast.Module:
    return ast.parse(
        (_API_ROOT / filename).read_text(encoding="utf-8"),
        filename=filename,
    )


def _functions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _has_actor_parameter(
    function: ast.FunctionDef,
) -> bool:
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    return any(
        argument.arg == "actor"
        and argument.annotation is not None
        and ast.unparse(argument.annotation) == "ActorDep"
        for argument in arguments
    )


def _service_calls(
    function: ast.FunctionDef,
    service_name: str,
) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == service_name
    ]


def _forwards_actor(call: ast.Call) -> bool:
    return (
        len(call.args) >= 2
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "session"
        and isinstance(call.args[1], ast.Name)
        and call.args[1].id == "actor"
    )


@pytest.mark.parametrize(
    ("filename", "expected_functions"),
    _ROUTE_FUNCTIONS.items(),
)
def test_demand_routes_require_actor_dependency(
    filename: str,
    expected_functions: set[str],
) -> None:
    functions = _functions(_tree(filename))
    missing = sorted(
        name
        for name in expected_functions
        if (
            name not in functions
            or not _has_actor_parameter(functions[name])
        )
    )
    assert missing == []


@pytest.mark.parametrize(
    ("filename", "service_name"),
    _SERVICE_NAMES.items(),
)
def test_tenant_aware_service_calls_forward_actor(
    filename: str,
    service_name: str,
) -> None:
    failures: list[str] = []
    for function in _functions(_tree(filename)).values():
        for call in _service_calls(
            function,
            service_name,
        ):
            if not _forwards_actor(call):
                failures.append(
                    f"{filename}:{function.name}:"
                    f"{ast.unparse(call)}"
                )
    assert failures == []


def test_direct_calculation_queries_include_tenant_predicate(
) -> None:
    functions = _functions(_tree("calculations.py"))
    expected = (
        "DemandCalculation.tenant_id == actor.tenant_id"
    )
    failures = []
    for name in sorted(_DIRECT_CALCULATION_QUERIES):
        comparisons = {
            ast.unparse(node)
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Compare)
        }
        if expected not in comparisons:
            failures.append(name)
    assert failures == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/demand/calculations",
        "/api/v1/demand/repair-profiles",
    ],
)
def test_demand_routes_reject_missing_internal_actor(
    client,
    path: str,
) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert (
        response.json()["detail"]["code"]
        == "INTERNAL_TOKEN_INVALID"
    )

def _use_actor(client, actor) -> None:
    def override_actor():
        return actor

    client.app.dependency_overrides[
        get_actor
    ] = override_actor


def _calculation_payload(
    spare: SparePart,
) -> dict:
    return {
        "tenant_id": "tenant-b",
        "calculation_name": (
            "tenant boundary calculation"
        ),
        "requested_mode": "ANALYTICAL",
        "execution_preference": "SYNC",
        "temporary_scenario": {
            "calculation_code": "TENANT-BOUNDARY",
            "stages": [
                {
                    "code": "S1",
                    "name": "stage",
                    "order": 1,
                    "duration_hours": "100",
                    "utilization_rate": "1",
                }
            ],
            "items": [
                {
                    "spare_part_id": spare.id,
                    "spare_part_code": spare.code,
                    "spare_part_name": spare.name,
                    "installed_positions": "10",
                    "replacement_ratio": "1",
                    "is_repairable": False,
                    "failure_process_mode": (
                        "SINGLE_FAILURE"
                    ),
                    "target_service_level": "0.95",
                    "reliability": {
                        "model_type": "EXPONENTIAL",
                        "failure_rate": "0.001",
                    },
                    "inventory": {},
                }
            ],
            "simulation": {
                "min_runs": 100,
                "max_runs": 200,
                "batch_size": 100,
                "quantiles": ["0.5", "0.95"],
            },
        },
    }


def test_calculation_routes_ignore_untrusted_tenant_and_hide_other_tenant(
    authenticated_client,
    session,
    actor_context,
) -> None:
    actor_a = actor_context(
        tenant_id="tenant-a",
        user_id="user-a",
    )
    actor_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
    )
    spare = SparePart(
        code="SP-TENANT-CALC",
        name="tenant calculation spare",
        unit="piece",
        is_repairable=False,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)

    _use_actor(
        authenticated_client,
        actor_a,
    )
    created = authenticated_client.post(
        (
            "/api/v1/demand/calculations"
            "?tenant_id=tenant-b"
        ),
        headers={
            "X-Tenant-ID": "tenant-b",
        },
        json=_calculation_payload(spare),
    )
    assert created.status_code == 200, created.text
    calculation_id = created.json()["data"]["id"]

    session.expire_all()
    calculation = session.scalar(
        select(DemandCalculation).where(
            DemandCalculation.id
            == calculation_id
        )
    )
    assert calculation is not None
    assert calculation.tenant_id == "tenant-a"

    _use_actor(
        authenticated_client,
        actor_b,
    )
    for path in (
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}"
        ),
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}/status"
        ),
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}/results/items"
        ),
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}/runs"
        ),
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}/comparison"
        ),
        (
            "/api/v1/demand/calculations/"
            f"{calculation_id}/export"
            "?format=json"
        ),
    ):
        response = authenticated_client.get(path)
        assert response.status_code == 404, (
            path,
            response.text,
        )

    listed = authenticated_client.get(
        "/api/v1/demand/calculations"
    )
    assert listed.status_code == 200
    assert calculation_id not in {
        row["id"]
        for row in listed.json()["data"]["items"]
    }


def test_repair_routes_ignore_untrusted_tenant_and_hide_other_tenant(
    authenticated_client,
    session,
    actor_context,
) -> None:
    actor_a = actor_context(
        tenant_id="tenant-a",
        user_id="user-a",
    )
    actor_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
    )
    spare = SparePart(
        code="SP-TENANT-REPAIR",
        name="tenant repair spare",
        unit="piece",
        is_repairable=True,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)

    _use_actor(
        authenticated_client,
        actor_a,
    )
    created = authenticated_client.post(
        (
            "/api/v1/demand/repair-profiles"
            "?tenant_id=tenant-b"
        ),
        headers={
            "X-Tenant-ID": "tenant-b",
        },
        json={
            "tenant_id": "tenant-b",
            "profile_code": "RP-TENANT",
            "profile_name": (
                "tenant repair profile"
            ),
            "spare_part_id": spare.id,
            "repair_success_rate": "0.85",
            "condemnation_rate": "0.10",
            "repair_turnaround_hours": "72",
            "data_source_type": (
                "MAINTENANCE_RECORD"
            ),
        },
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["data"]["id"]

    session.expire_all()
    profile = session.scalar(
        select(RepairProfile).where(
            RepairProfile.id == profile_id
        )
    )
    assert profile is not None
    assert profile.tenant_id == "tenant-a"

    _use_actor(
        authenticated_client,
        actor_b,
    )
    fetched = authenticated_client.get(
        (
            "/api/v1/demand/repair-profiles/"
            f"{profile_id}"
        )
    )
    assert fetched.status_code == 404

    listed = authenticated_client.get(
        "/api/v1/demand/repair-profiles"
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 0

    updated = authenticated_client.put(
        (
            "/api/v1/demand/repair-profiles/"
            f"{profile_id}"
        ),
        json={
            "repair_turnaround_hours": "48",
        },
    )
    assert updated.status_code == 404

    activated = authenticated_client.patch(
        (
            "/api/v1/demand/repair-profiles/"
            f"{profile_id}/active"
        ),
        json={
            "is_active": False,
        },
    )
    assert activated.status_code == 404

    deleted = authenticated_client.delete(
        (
            "/api/v1/demand/repair-profiles/"
            f"{profile_id}"
        )
    )
    assert deleted.status_code == 404
