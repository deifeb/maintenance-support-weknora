from app.models import SparePart


def test_repair_profile_crud(client, session):
    spare = SparePart(
        code="SP-RP",
        name="可修件",
        unit="件",
        is_repairable=True,
        tenant_id="tenant-a",
    )
    session.add(spare)
    session.commit()
    session.refresh(spare)
    payload = {
        "profile_code": "RP-001",
        "profile_name": "基地修理",
        "spare_part_id": spare.id,
        "repair_success_rate": "0.85",
        "condemnation_rate": "0.10",
        "repair_turnaround_hours": "72",
        "data_source_type": "MAINTENANCE_RECORD",
    }
    created = client.post("/api/v1/demand/repair-profiles", json=payload)
    assert created.status_code == 201, created.text
    identifier = created.json()["data"]["id"]
    listed = client.get("/api/v1/demand/repair-profiles")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    updated = client.put(
        f"/api/v1/demand/repair-profiles/{identifier}", json={"repair_turnaround_hours": "48"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["repair_turnaround_hours"] == "48.000000"
