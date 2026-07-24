def test_demand_routes_are_registered(client):
    paths = set(client.app.openapi()["paths"])
    assert "/api/v1/demand/calculations" in paths
    assert "/api/v1/demand/calculations/preview" in paths
    assert "/api/v1/demand/scenario-versions/{version_id}/publish" in paths
