def test_report_api_generates_validates_finalizes_and_exports(client) -> None:
    created = client.post(
        "/api/v1/ai/reports",
        json={
            "title": "维修器材保障分析报告",
            "report_type": "MANAGEMENT_DECISION",
            "metadata": {"allowed_numbers": ["8"]},
            "sections": [
                {
                    "section_code": "management_summary",
                    "title": "管理摘要",
                    "content": "本次共识别 8 项需求。[E-001]",
                    "source_type": "DETERMINISTIC",
                }
            ],
            "citations": [
                {
                    "citation_id": "E-001",
                    "source_type": "CALCULATION_SNAPSHOT",
                    "source_name": "需求计算快照",
                }
            ],
        },
    )
    assert created.status_code == 200
    report_id = created.json()["data"]["id"]

    generated = client.post(f"/api/v1/ai/reports/{report_id}/generate")
    assert generated.status_code == 200
    assert len(generated.json()["data"]["sections"]) == 17

    validated = client.post(f"/api/v1/ai/reports/{report_id}/validate")
    assert validated.status_code == 200
    assert validated.json()["data"]["findings"] == []

    finalized = client.post(f"/api/v1/ai/reports/{report_id}/finalize", json={"actor": "tester"})
    assert finalized.status_code == 200
    assert finalized.json()["data"]["status"] == "FINAL"

    versions = client.get(f"/api/v1/ai/reports/{report_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()["data"]) == 1

    docx = client.get(f"/api/v1/ai/reports/{report_id}/exports/docx")
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"
