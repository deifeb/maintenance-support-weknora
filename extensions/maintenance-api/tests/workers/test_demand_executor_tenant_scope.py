from __future__ import annotations

from inspect import signature

from app.workers.executor import DemandTaskExecutor
from app.workers.task_registry import registry


class CapturingPool:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, function, *args):
        self.calls.append((function, args))
        return object()


def test_demand_executor_submit_requires_tenant() -> None:
    parameters = signature(DemandTaskExecutor.submit).parameters
    assert "tenant_id" in parameters
    assert "calculation_id" in parameters


def test_submit_deduplicates_per_tenant(monkeypatch) -> None:
    executor = DemandTaskExecutor()
    pool = CapturingPool()
    monkeypatch.setattr(executor, "_pool", lambda: pool)

    local_key = ("tenant-a", 41)
    other_key = ("tenant-b", 41)
    try:
        assert executor.submit("tenant-a", 41) is True
        assert executor.submit("tenant-a", 41) is False
        assert executor.submit("tenant-b", 41) is True
        assert [args for _, args in pool.calls] == [
            ("tenant-a", 41),
            ("tenant-b", 41),
        ]
    finally:
        registry.unregister(local_key)
        registry.unregister(other_key)


def test_worker_forwards_trusted_tenant_context(monkeypatch) -> None:
    seen = {}

    class FakeSession:
        def close(self) -> None:
            seen["closed"] = True

    session = FakeSession()

    def fake_run_internal(db, *, tenant_id, calculation_id):
        seen["db"] = db
        seen["tenant_id"] = tenant_id
        seen["calculation_id"] = calculation_id

    unregistered = []
    monkeypatch.setattr(
        "app.workers.executor.SessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        "app.workers.executor.calculation_service.run_internal",
        fake_run_internal,
    )
    monkeypatch.setattr(
        "app.workers.executor.registry.unregister",
        unregistered.append,
    )

    DemandTaskExecutor._run("tenant-a", 41)

    assert seen == {
        "db": session,
        "tenant_id": "tenant-a",
        "calculation_id": 41,
        "closed": True,
    }
    assert unregistered == [("tenant-a", 41)]


def test_submit_unregisters_when_scheduling_fails(monkeypatch) -> None:
    executor = DemandTaskExecutor()
    key = ("tenant-a", 99)

    class FailingPool:
        def submit(self, function, *args):
            del function, args
            raise RuntimeError("pool unavailable")

    monkeypatch.setattr(executor, "_pool", lambda: FailingPool())

    try:
        try:
            executor.submit("tenant-a", 99)
        except RuntimeError as exc:
            assert str(exc) == "pool unavailable"
        else:
            raise AssertionError("scheduling failure was not raised")

        assert registry.register(key) is True
    finally:
        registry.unregister(key)


# TASK_073_REVIEW_FIXES


def test_task_registry_contract_uses_tenant_key() -> None:
    registry_type = type(registry)
    parameters = signature(
        registry_type.register
    ).parameters

    assert "key" in parameters
    assert "calculation_id" not in parameters

    isolated = registry_type()
    local_key = ("tenant-a", 7)
    other_key = ("tenant-b", 7)

    assert isolated.register(local_key) is True
    assert isolated.register(local_key) is False
    assert isolated.register(other_key) is True
    assert isolated.is_running(local_key) is True
    assert isolated.is_running(other_key) is True

    isolated.unregister(local_key)
    assert isolated.is_running(local_key) is False
    assert isolated.is_running(other_key) is True
