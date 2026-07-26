from app.models import SparePart


def _create_spare(session):
    spare = SparePart(
        code="SP-CALC",
        name="计算器材",
        unit="件",
        is_repairable=True,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)
    return spare


def _payload(spare_id):
    return {
        "calculation_name": "同步需求计算",
        "requested_mode": "ANALYTICAL",
        "execution_preference": "SYNC",
        "temporary_scenario": {
            "calculation_code": "TEMP-1",
            "stages": [
                {
                    "code": "S1",
                    "name": "训练",
                    "order": 1,
                    "duration_hours": "100",
                    "utilization_rate": "1",
                }
            ],
            "items": [
                {
                    "spare_part_id": spare_id,
                    "spare_part_code": "SP-CALC",
                    "spare_part_name": "计算器材",
                    "installed_positions": "100",
                    "replacement_ratio": "1",
                    "is_repairable": True,
                    "failure_process_mode": "RENEWAL",
                    "target_service_level": "0.95",
                    "reliability": {"model_type": "EXPONENTIAL", "failure_rate": "0.001"},
                    "inventory": {
                        "on_hand_quantity": "5",
                        "available_quantity": "5",
                        "in_transit_quantity": "0",
                        "safety_stock": "0",
                    },
                }
            ],
            "simulation": {
                "min_runs": 1000,
                "max_runs": 2000,
                "batch_size": 500,
                "quantiles": ["0.5", "0.8", "0.9", "0.95", "0.99"],
            },
        },
    }


def test_sync_calculation_persists_results(client, session):
    spare = _create_spare(session)
    response = client.post("/api/v1/demand/calculations", json=_payload(spare.id))
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "SUCCEEDED"

    result = client.get(f"/api/v1/demand/calculations/{body['id']}/results/items")
    assert result.status_code == 200
    items = result.json()["data"]
    assert len(items) == 1
    assert float(items[0]["expected_demand"]) == 10.0
    assert float(items[0]["net_demand_gap"]) >= 0


def test_idempotency_key_returns_same_calculation(client, session):
    spare = _create_spare(session)
    headers = {"Idempotency-Key": "same-request"}
    first = client.post("/api/v1/demand/calculations", json=_payload(spare.id), headers=headers)
    second = client.post("/api/v1/demand/calculations", json=_payload(spare.id), headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_json_and_excel_exports(client, session):
    spare = _create_spare(session)
    created = client.post("/api/v1/demand/calculations", json=_payload(spare.id)).json()["data"]
    json_export = client.get(f"/api/v1/demand/calculations/{created['id']}/export?format=json")
    excel_export = client.get(f"/api/v1/demand/calculations/{created['id']}/export?format=xlsx")
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert excel_export.status_code == 200
    assert excel_export.content[:2] == b"PK"
