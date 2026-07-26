import time

from app.models import SparePart


def test_async_calculation_completes(client, session):
    spare = SparePart(
        code="SP-ASYNC",
        name="异步器材",
        unit="件",
        is_repairable=False,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)
    payload = {
        "calculation_name": "异步计算",
        "requested_mode": "MONTE_CARLO",
        "execution_preference": "ASYNC",
        "random_seed": 42,
        "temporary_scenario": {
            "stages": [
                {
                    "code": "S1",
                    "name": "阶段",
                    "order": 1,
                    "duration_hours": 100,
                    "utilization_rate": 1,
                }
            ],
            "items": [
                {
                    "spare_part_id": spare.id,
                    "spare_part_code": spare.code,
                    "spare_part_name": spare.name,
                    "installed_positions": 20,
                    "replacement_ratio": 1,
                    "is_repairable": False,
                    "failure_process_mode": "SINGLE_FAILURE",
                    "target_service_level": 0.95,
                    "reliability": {"model_type": "EXPONENTIAL", "failure_rate": 0.001},
                    "inventory": {},
                }
            ],
            "simulation": {
                "min_runs": 200,
                "max_runs": 400,
                "batch_size": 100,
                "required_stable_batches": 1,
                "quantiles": [0.5, 0.95],
            },
        },
    }
    created = client.post("/api/v1/demand/calculations", json=payload)
    assert created.status_code == 200, created.text
    calculation_id = created.json()["data"]["id"]
    status = created.json()["data"]["status"]
    for _ in range(40):
        if status in {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"}:
            break
        time.sleep(0.05)
        status = client.get(f"/api/v1/demand/calculations/{calculation_id}/status").json()["data"][
            "status"
        ]
    assert status in {"SUCCEEDED", "PARTIAL_SUCCESS"}
