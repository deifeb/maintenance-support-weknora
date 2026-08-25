from __future__ import annotations

import asyncio
import importlib

import pytest
from app.core.config import get_settings

FEATURE_MISSING = "PLAN05_4D_TASK3_FEATURE_MISSING"


def _worker_api():
    required = (
        "app.services.allocation_simulation_service",
        "app.workers.allocation_simulation_executor",
    )
    missing = [
        name
        for name in required
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        pytest.fail(
            f"{FEATURE_MISSING}: missing Task 3 modules: "
            + ", ".join(missing),
            pytrace=False,
        )
    module = importlib.import_module(
        "app.workers.allocation_simulation_executor"
    )
    if not hasattr(module, "AllocationSimulationExecutor"):
        pytest.fail(
            f"{FEATURE_MISSING}: missing AllocationSimulationExecutor",
            pytrace=False,
        )
    return module


class _DeferredPool:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return object()

    def shutdown(
        self,
        *,
        wait: bool,
        cancel_futures: bool,
    ) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _FakeService:
    def __init__(self, *, fail_run: bool = False) -> None:
        self.fail_run = fail_run
        self.claims: list[tuple[str, int]] = []
        self.runs: list[tuple[str, int]] = []
        self.failures: list[tuple[str, int, Exception]] = []

    def claim(self, session, tenant_id: str, simulation_id: int):
        del session
        self.claims.append((tenant_id, simulation_id))
        return object()

    def run_claimed(
        self,
        session,
        tenant_id: str,
        simulation_id: int,
    ) -> None:
        del session
        self.runs.append((tenant_id, simulation_id))
        if self.fail_run:
            raise RuntimeError("worker boom")

    def fail_safely(
        self,
        tenant_id: str,
        simulation_id: int,
        error: Exception,
    ) -> None:
        self.failures.append((tenant_id, simulation_id, error))


def test_executor_submit_deduplicates_tenant_simulation_key(
    monkeypatch,
) -> None:
    worker_api = _worker_api()
    executor = worker_api.AllocationSimulationExecutor()
    pool = _DeferredPool()
    monkeypatch.setattr(executor, "_pool", lambda: pool)

    first = executor.submit("tenant-dedupe", 101)
    second = executor.submit("tenant-dedupe", 101)

    assert first is True
    assert second is False
    assert len(pool.submissions) == 1


def test_executor_run_claims_runs_and_unregisters(
    monkeypatch,
) -> None:
    worker_api = _worker_api()
    fake_service = _FakeService()
    fake_session = _FakeSession()
    monkeypatch.setattr(
        worker_api,
        "allocation_simulation_service",
        fake_service,
    )
    monkeypatch.setattr(
        worker_api,
        "SessionLocal",
        lambda: fake_session,
    )

    executor = worker_api.AllocationSimulationExecutor()
    executor._run("tenant-run", 202)

    assert fake_service.claims == [("tenant-run", 202)]
    assert fake_service.runs == [("tenant-run", 202)]
    assert fake_service.failures == []
    assert fake_session.closed is True

    pool = _DeferredPool()
    monkeypatch.setattr(executor, "_pool", lambda: pool)
    assert executor.submit("tenant-run", 202) is True


def test_executor_failure_calls_fail_safely_and_unregisters(
    monkeypatch,
) -> None:
    worker_api = _worker_api()
    fake_service = _FakeService(fail_run=True)
    fake_session = _FakeSession()
    monkeypatch.setattr(
        worker_api,
        "allocation_simulation_service",
        fake_service,
    )
    monkeypatch.setattr(
        worker_api,
        "SessionLocal",
        lambda: fake_session,
    )

    executor = worker_api.AllocationSimulationExecutor()
    executor._run("tenant-fail", 303)

    assert fake_service.claims == [("tenant-fail", 303)]
    assert fake_service.runs == [("tenant-fail", 303)]
    assert len(fake_service.failures) == 1
    tenant_id, simulation_id, error = fake_service.failures[0]
    assert tenant_id == "tenant-fail"
    assert simulation_id == 303
    assert isinstance(error, RuntimeError)
    assert fake_session.closed is True

    pool = _DeferredPool()
    monkeypatch.setattr(executor, "_pool", lambda: pool)
    assert executor.submit("tenant-fail", 303) is True


def test_executor_shutdown_releases_pool() -> None:
    worker_api = _worker_api()
    executor = worker_api.AllocationSimulationExecutor()
    pool = _DeferredPool()
    executor._executor = pool

    executor.shutdown(wait=False)

    assert pool.shutdown_calls == [(False, False)]
    assert executor._executor is None


def test_config_exposes_allocation_simulation_worker_count(
    monkeypatch,
) -> None:
    _worker_api()
    monkeypatch.setenv("ALLOCATION_SIMULATION_WORKER_COUNT", "3")
    get_settings.cache_clear()
    try:
        assert get_settings().allocation_simulation_worker_count == 3
    finally:
        get_settings.cache_clear()

def test_app_lifespan_shuts_down_allocation_executor(
    monkeypatch,
) -> None:
    import app.main as main_api

    if not hasattr(main_api, "allocation_simulation_executor"):
        pytest.fail(
            "PLAN05_4D_TASK3_LIFECYCLE_MISSING: "
            "app lifespan does not expose allocation simulation executor",
            pytrace=False,
        )

    shutdown_calls: list[bool] = []

    class _ShutdownProbe:
        def shutdown(self, wait: bool = False) -> None:
            shutdown_calls.append(wait)

    monkeypatch.setattr(
        main_api,
        "allocation_simulation_executor",
        _ShutdownProbe(),
    )
    monkeypatch.setattr(
        main_api,
        "recover_interrupted_calculations",
        lambda session: None,
    )
    monkeypatch.setattr(
        main_api,
        "recover_interrupted_ai_tasks",
        lambda session: None,
    )
    monkeypatch.setattr(
        main_api,
        "recover_stale_import_tasks",
        lambda session, **kwargs: None,
    )

    async def exercise_lifespan() -> None:
        async with main_api.lifespan(object()):
            pass

    asyncio.run(exercise_lifespan())

    assert shutdown_calls == [False]
