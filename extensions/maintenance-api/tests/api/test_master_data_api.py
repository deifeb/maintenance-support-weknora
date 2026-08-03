import pytest
from app.security.actor import MaintenanceRole


@pytest.mark.parametrize(
    "path,payload",
    [
        ("equipment-models", {"code": "EQ-1", "name": "Equipment"}),
        ("parts", {"code": "PT-1", "name": "Part"}),
        ("spare-parts", {"code": "SP-1", "name": "Spare", "unit": "件"}),
        ("warehouses", {"code": "WH-1", "name": "Warehouse"}),
        ("suppliers", {"code": "SUP-1", "name": "Supplier"}),
    ],
)
def test_simple_resource_crud(
    client,
    path,
    payload,
    internal_auth_headers,
) -> None:
    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="contributor-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-master-contributor",
    )
    created = client.post(
        f"/api/v1/master-data/{path}",
        json=payload,
        headers=contributor_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["meta"]["tenant_id"] == "tenant-a"
    assert created.json()["meta"]["request_id"] == (
        "request-master-contributor"
    )
    assert created.json()["meta"]["version"] == 1
    identifier = created.json()["data"]["id"]

    listed = client.get(
        f"/api/v1/master-data/{path}",
        headers=contributor_headers,
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["meta"]["tenant_id"] == "tenant-a"

    fetched = client.get(
        f"/api/v1/master-data/{path}/{identifier}",
        headers=contributor_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["meta"]["request_id"] == (
        "request-master-contributor"
    )

    deactivated = client.patch(
        f"/api/v1/master-data/{path}/{identifier}/active",
        json={"is_active": False},
        headers=contributor_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["meta"]["version"] >= (
        created.json()["meta"]["version"]
    )

    contributor_delete = client.delete(
        f"/api/v1/master-data/{path}/{identifier}",
        headers=contributor_headers,
    )
    assert contributor_delete.status_code == 403

    admin_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="admin-a",
        role=MaintenanceRole.ADMIN,
        request_id="request-master-admin",
    )
    deleted = client.delete(
        f"/api/v1/master-data/{path}/{identifier}",
        headers=admin_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["meta"] == {
        "request_id": "request-master-admin",
        "tenant_id": "tenant-a",
        "version": None,
    }

def test_configuration_api_flow(
    client,
    internal_auth_headers,
) -> None:
    headers = internal_auth_headers(
        role=MaintenanceRole.CONTRIBUTOR,
    )
    equipment = client.post(
        "/api/v1/master-data/equipment-models", json={"code": "EQ-1", "name": "E"}, headers=headers
    ).json()["data"]
    part = client.post(
        "/api/v1/master-data/parts", json={"code": "PT-1", "name": "P"}, headers=headers
    ).json()["data"]
    version = client.post(
        "/api/v1/master-data/configuration-versions",
        json={
            "equipment_model_id": equipment["id"],
            "version_code": "V1",
            "version_name": "Version 1",
        },
        headers=headers,
    )
    assert version.status_code == 201
    version_id = version.json()["data"]["id"]
    item = client.post(
        "/api/v1/master-data/configuration-items",
        json={
            "configuration_version_id": version_id,
            "item_code": "ROOT",
            "part_id": part["id"],
            "install_quantity": 1,
        },
        headers=headers,
    )
    assert item.status_code == 201
    published = client.post(
        f"/api/v1/master-data/configuration-versions/{version_id}/publish", headers=headers
    )
    assert published.status_code == 200
    tree = client.get(
        f"/api/v1/master-data/configuration-versions/{version_id}/tree", headers=headers
    )
    assert tree.status_code == 200
    assert tree.json()["data"]["items"][0]["item_code"] == "ROOT"


def test_openapi_contains_master_data_routes(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/master-data/equipment-models" in paths
    assert "/api/v1/master-data/import/template" in paths
