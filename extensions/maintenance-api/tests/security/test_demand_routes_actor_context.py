from __future__ import annotations

import ast
from pathlib import Path

import pytest
from app.models import (
    DemandCalculation,
    DemandScenarioTemplate,
    RepairProfile,
    SparePart,
)
from app.security.actor import MaintenanceRole
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
    "scenarios.py": {
        "create_scenario",
        "list_scenarios",
        "get_scenario",
        "update_scenario",
        "delete_scenario",
        "create_version",
        "list_versions",
        "get_version",
        "update_version",
        "validate_version",
        "publish_version",
        "clone_version",
        "retire_version",
        "full_version",
        "add_stage",
        "add_fleet_group",
        "add_age_group",
        "add_fleet_usage",
        "add_override",
        "add_shock",
    },
    "comparisons.py": {
        "compare",
    },
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
    "demand_lists.py": {
        "create_demand_list",
        "list_demand_lists",
        "get_demand_list",
        "update_demand_list_item",
        "submit_demand_list",
        "confirm_demand_list",
        "publish_demand_list",
        "derive_demand_list",
        "void_demand_list",
    },
}

_SERVICE_NAMES = {
    "scenarios.py": "scenario_service",
    "comparisons.py": "calculation_service",
    "calculations.py": "calculation_service",
    "repair_profiles.py": "repair_service",
    "demand_lists.py": "demand_list_service",
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
    accepted = {
        "ActorDep",
        "ViewerDep",
        "ContributorDep",
        "AdminDep",
    }
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    return any(
        argument.arg == "actor"
        and argument.annotation is not None
        and ast.unparse(argument.annotation)
        in accepted
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
        role=MaintenanceRole.ADMIN,
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


def test_demand_success_responses_include_actor_metadata(
) -> None:
    failures: list[str] = []

    for filename in _ROUTE_FUNCTIONS:
        functions = _functions(_tree(filename))
        for name in _ROUTE_FUNCTIONS[filename]:
            function = functions[name]
            calls = [
                node
                for node in ast.walk(function)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "success_response"
                )
            ]
            for call in calls:
                has_actor = any(
                    keyword.arg == "actor"
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id == "actor"
                    for keyword in call.keywords
                )
                if not has_actor:
                    failures.append(
                        f"{filename}:{name}:{call.lineno}"
                    )

    assert failures == [], "\n".join(failures)

_DEMAND_LIST_ROLES = {
    "create_demand_list": "ContributorDep",
    "list_demand_lists": "ViewerDep",
    "get_demand_list": "ViewerDep",
    "update_demand_list_item": "ContributorDep",
    "submit_demand_list": "ContributorDep",
    "confirm_demand_list": "AdminDep",
    "publish_demand_list": "AdminDep",
    "derive_demand_list": "AdminDep",
    "void_demand_list": "AdminDep",
}


def test_demand_list_routes_use_exact_role_aliases(
) -> None:
    functions = _functions(_tree("demand_lists.py"))
    failures: list[str] = []

    for name, expected_alias in (
        _DEMAND_LIST_ROLES.items()
    ):
        if name not in functions:
            failures.append(
                f"demand_lists.py:{name}: missing"
            )
            continue
        actual_alias = _actor_annotation(
            functions[name]
        )
        if actual_alias != expected_alias:
            failures.append(
                f"demand_lists.py:{name}: "
                f"expected={expected_alias}, "
                f"actual={actual_alias}"
            )

    assert failures == [], "\n".join(failures)


_SCENARIO_COMPARISON_ROLES = {
    "scenarios.py": {
        "list_scenarios": "ViewerDep",
        "get_scenario": "ViewerDep",
        "list_versions": "ViewerDep",
        "get_version": "ViewerDep",
        "full_version": "ViewerDep",
        "create_scenario": "ContributorDep",
        "update_scenario": "ContributorDep",
        "create_version": "ContributorDep",
        "update_version": "ContributorDep",
        "validate_version": "ContributorDep",
        "clone_version": "ContributorDep",
        "add_stage": "ContributorDep",
        "add_fleet_group": "ContributorDep",
        "add_age_group": "ContributorDep",
        "add_fleet_usage": "ContributorDep",
        "add_override": "ContributorDep",
        "add_shock": "ContributorDep",
        "delete_scenario": "AdminDep",
        "publish_version": "AdminDep",
        "retire_version": "AdminDep",
    },
    "comparisons.py": {
        "compare": "ViewerDep",
    },
}


def _actor_annotation(
    function: ast.FunctionDef,
) -> str | None:
    for argument in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]:
        if (
            argument.arg == "actor"
            and argument.annotation is not None
        ):
            return ast.unparse(argument.annotation)
    return None


def test_scenario_and_comparison_use_exact_role_aliases(
) -> None:
    failures: list[str] = []

    for filename, expected in (
        _SCENARIO_COMPARISON_ROLES.items()
    ):
        functions = _functions(_tree(filename))
        for name, alias in expected.items():
            actual = _actor_annotation(functions[name])
            if actual != alias:
                failures.append(
                    f"{filename}:{name}: "
                    f"expected={alias}, actual={actual}"
                )

    assert failures == [], "\n".join(failures)


def test_scenario_and_comparison_metadata_is_actor_aware(
) -> None:
    failures: list[str] = []

    for filename, expected in (
        _SCENARIO_COMPARISON_ROLES.items()
    ):
        functions = _functions(_tree(filename))
        for name in expected:
            calls = [
                node
                for node in ast.walk(functions[name])
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "success_response"
                )
            ]
            for call in calls:
                has_actor = any(
                    keyword.arg == "actor"
                    and isinstance(
                        keyword.value,
                        ast.Name,
                    )
                    and keyword.value.id == "actor"
                    for keyword in call.keywords
                )
                if not has_actor:
                    failures.append(
                        f"{filename}:{name}:{call.lineno}"
                    )

    assert failures == [], "\n".join(failures)


def test_scenario_route_roles_tenant_and_metadata(
    authenticated_client,
    session,
    actor_context,
) -> None:
    viewer = actor_context(
        tenant_id="tenant-a",
        user_id="viewer-a",
        role=MaintenanceRole.VIEWER,
        request_id="request-viewer-a",
    )
    _use_actor(authenticated_client, viewer)

    listed = authenticated_client.get(
        "/api/v1/demand/scenarios"
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["meta"] == {
        "request_id": "request-viewer-a",
        "tenant_id": "tenant-a",
        "version": None,
    }

    denied = authenticated_client.post(
        "/api/v1/demand/scenarios",
        json={
            "code": "SC-VIEWER",
            "name": "viewer cannot create",
        },
    )
    assert denied.status_code == 403

    contributor = actor_context(
        tenant_id="tenant-a",
        user_id="contributor-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-contributor-a",
    )
    _use_actor(authenticated_client, contributor)
    created = authenticated_client.post(
        "/api/v1/demand/scenarios?tenant_id=tenant-b",
        headers={
            "X-Tenant-ID": "tenant-b",
        },
        json={
            "tenant_id": "tenant-b",
            "code": "SC-TENANT",
            "name": "tenant scenario",
        },
    )
    assert created.status_code == 201, created.text
    scenario_id = created.json()["data"]["id"]
    assert created.json()["meta"]["tenant_id"] == "tenant-a"
    assert created.json()["meta"]["request_id"] == (
        "request-contributor-a"
    )

    session.expire_all()
    scenario = session.scalar(
        select(DemandScenarioTemplate).where(
            DemandScenarioTemplate.id == scenario_id
        )
    )
    assert scenario is not None
    assert scenario.tenant_id == "tenant-a"

    contributor_delete = authenticated_client.delete(
        f"/api/v1/demand/scenarios/{scenario_id}"
    )
    assert contributor_delete.status_code == 403

    other_tenant = actor_context(
        tenant_id="tenant-b",
        user_id="viewer-b",
        role=MaintenanceRole.VIEWER,
    )
    _use_actor(authenticated_client, other_tenant)
    hidden = authenticated_client.get(
        f"/api/v1/demand/scenarios/{scenario_id}"
    )
    assert hidden.status_code == 404

    admin = actor_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-a",
    )
    _use_actor(authenticated_client, admin)
    deleted = authenticated_client.delete(
        f"/api/v1/demand/scenarios/{scenario_id}"
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["meta"]["tenant_id"] == "tenant-a"


def test_comparison_route_hides_other_tenant(
    authenticated_client,
    session,
    actor_context,
) -> None:
    actor_a = actor_context(
        tenant_id="tenant-a",
        user_id="contributor-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-compare-a",
    )
    spare = SparePart(
        code="SP-COMPARE",
        name="comparison spare",
        unit="piece",
        is_repairable=False,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)

    _use_actor(authenticated_client, actor_a)
    first_payload = _calculation_payload(spare)
    second_payload = _calculation_payload(spare)
    first_payload["calculation_name"] = "comparison left"
    second_payload["calculation_name"] = "comparison right"

    first = authenticated_client.post(
        "/api/v1/demand/calculations",
        json=first_payload,
    )
    second = authenticated_client.post(
        "/api/v1/demand/calculations",
        json=second_payload,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    left_id = first.json()["data"]["id"]
    right_id = second.json()["data"]["id"]

    same_tenant = authenticated_client.post(
        "/api/v1/demand/comparisons",
        json={
            "left_calculation_id": left_id,
            "right_calculation_id": right_id,
        },
    )
    assert same_tenant.status_code == 200, same_tenant.text
    assert same_tenant.json()["meta"] == {
        "request_id": "request-compare-a",
        "tenant_id": "tenant-a",
        "version": None,
    }

    actor_b = actor_context(
        tenant_id="tenant-b",
        user_id="viewer-b",
        role=MaintenanceRole.VIEWER,
    )
    _use_actor(authenticated_client, actor_b)
    hidden = authenticated_client.post(
        "/api/v1/demand/comparisons",
        json={
            "left_calculation_id": left_id,
            "right_calculation_id": right_id,
        },
    )
    assert hidden.status_code == 404



_CALCULATION_REPAIR_ROLE_ALIASES = {
    "calculations.py": {
        "list_calculations": "ViewerDep",
        "get_calculation": "ViewerDep",
        "get_status": "ViewerDep",
        "result_items": "ViewerDep",
        "runs": "ViewerDep",
        "comparison": "ViewerDep",
        "export": "ViewerDep",
        "preview": "ContributorDep",
        "submit": "ContributorDep",
        "cancel": "ContributorDep",
        "retry": "ContributorDep",
        "replay": "ContributorDep",
        "rerun_latest": "ContributorDep",
    },
    "repair_profiles.py": {
        "list_profiles": "ViewerDep",
        "get_profile": "ViewerDep",
        "create_profile": "ContributorDep",
        "update_profile": "ContributorDep",
        "set_active": "ContributorDep",
        "delete_profile": "AdminDep",
    },
}


def test_calculation_and_repair_use_exact_role_aliases(
) -> None:
    failures: list[str] = []

    for filename, expected in (
        _CALCULATION_REPAIR_ROLE_ALIASES.items()
    ):
        functions = _functions(_tree(filename))
        for name, alias in expected.items():
            actual = _actor_annotation(functions[name])
            if actual != alias:
                failures.append(
                    f"{filename}:{name}: "
                    f"expected={alias}, actual={actual}"
                )

    assert failures == [], "\n".join(failures)


def test_calculation_and_repair_role_floors_and_metadata(
    authenticated_client,
    session,
    actor_context,
) -> None:
    contributor = actor_context(
        tenant_id="tenant-a",
        user_id="contributor-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-contributor-demand",
    )
    _use_actor(authenticated_client, contributor)

    spare = SparePart(
        code="SP-ROLE-META",
        name="role metadata spare",
        unit="piece",
        is_repairable=True,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)

    calculation = authenticated_client.post(
        "/api/v1/demand/calculations",
        json=_calculation_payload(spare),
    )
    assert calculation.status_code == 200, calculation.text
    calculation_id = calculation.json()["data"]["id"]
    assert calculation.json()["meta"] == {
        "request_id": "request-contributor-demand",
        "tenant_id": "tenant-a",
        "version": None,
    }

    profile = authenticated_client.post(
        "/api/v1/demand/repair-profiles",
        json={
            "profile_code": "RP-ROLE-META",
            "profile_name": "role metadata profile",
            "spare_part_id": spare.id,
            "repair_success_rate": "0.85",
            "condemnation_rate": "0.10",
            "repair_turnaround_hours": "72",
            "data_source_type": "MAINTENANCE_RECORD",
        },
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["data"]["id"]
    assert profile.json()["meta"]["tenant_id"] == "tenant-a"
    assert profile.json()["meta"]["request_id"] == (
        "request-contributor-demand"
    )
    assert profile.json()["meta"]["version"] == 1

    contributor_delete = authenticated_client.delete(
        f"/api/v1/demand/repair-profiles/{profile_id}"
    )
    assert contributor_delete.status_code == 403

    viewer = actor_context(
        tenant_id="tenant-a",
        user_id="viewer-a",
        role=MaintenanceRole.VIEWER,
        request_id="request-viewer-demand",
    )
    _use_actor(authenticated_client, viewer)

    calculation_list = authenticated_client.get(
        "/api/v1/demand/calculations"
    )
    assert calculation_list.status_code == 200
    assert calculation_list.json()["meta"] == {
        "request_id": "request-viewer-demand",
        "tenant_id": "tenant-a",
        "version": None,
    }

    calculation_detail = authenticated_client.get(
        f"/api/v1/demand/calculations/{calculation_id}"
    )
    assert calculation_detail.status_code == 200
    assert calculation_detail.json()["meta"]["tenant_id"] == (
        "tenant-a"
    )

    profile_list = authenticated_client.get(
        "/api/v1/demand/repair-profiles"
    )
    assert profile_list.status_code == 200
    assert profile_list.json()["meta"]["request_id"] == (
        "request-viewer-demand"
    )

    denied_cancel = authenticated_client.post(
        f"/api/v1/demand/calculations/{calculation_id}/cancel"
    )
    assert denied_cancel.status_code == 403

    denied_profile_update = authenticated_client.patch(
        f"/api/v1/demand/repair-profiles/{profile_id}/active",
        json={"is_active": False},
    )
    assert denied_profile_update.status_code == 403

    admin = actor_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role=MaintenanceRole.ADMIN,
        request_id="request-admin-demand",
    )
    _use_actor(authenticated_client, admin)

    deleted = authenticated_client.delete(
        f"/api/v1/demand/repair-profiles/{profile_id}"
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["meta"] == {
        "request_id": "request-admin-demand",
        "tenant_id": "tenant-a",
        "version": None,
    }
