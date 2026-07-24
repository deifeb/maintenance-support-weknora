def test_demand_review_api_persists_findings(client) -> None:
    response = client.post(
        "/api/v1/ai/reviews/demand-lists",
        json={
            "items": [
                {
                    "spare_part_id": 10,
                    "recommended_spare_quantity": "8",
                    "usable_inventory": "3",
                    "net_demand_gap": "5",
                    "inventory_coverage_rate": "0.375",
                    "selected_reliability_profile_id": 2,
                }
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["review_id"] > 0
    assert any(item["rule_code"] == "INV-001" for item in data["findings"])
