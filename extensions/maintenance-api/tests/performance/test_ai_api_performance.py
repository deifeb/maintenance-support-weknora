import statistics
import time

import pytest


@pytest.mark.performance
def test_ai_session_create_and_read_p95_under_targets(client) -> None:
    create_durations = []
    read_durations = []
    for index in range(100):
        started = time.perf_counter()
        created = client.post("/api/v1/ai/sessions", json={"title": f"性能会话{index}"})
        create_durations.append(time.perf_counter() - started)
        session_id = created.json()["data"]["id"]
        started = time.perf_counter()
        response = client.get(f"/api/v1/ai/sessions/{session_id}")
        read_durations.append(time.perf_counter() - started)
        assert response.status_code == 200

    create_p95 = statistics.quantiles(create_durations, n=20)[18]
    read_p95 = statistics.quantiles(read_durations, n=20)[18]
    assert create_p95 < 0.3
    assert read_p95 < 0.5


@pytest.mark.performance
def test_sse_once_returns_first_bytes_under_one_second(client) -> None:
    created = client.post("/api/v1/ai/sessions", json={"title": "SSE性能"})
    session_id = created.json()["data"]["id"]
    started = time.perf_counter()
    with client.stream(
        "GET",
        f"/api/v1/ai/sessions/{session_id}/stream?once=true",
    ) as response:
        body = "".join(response.iter_text())
    duration = time.perf_counter() - started
    assert response.status_code == 200
    assert "SESSION_STARTED" in body
    assert duration < 1.0
