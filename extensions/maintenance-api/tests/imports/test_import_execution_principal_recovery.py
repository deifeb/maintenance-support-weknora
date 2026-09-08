from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from app.db.session import SessionLocal
from app.importers.template import create_template_bytes
from app.models.import_task import ImportTaskStatus, MasterDataImportTask
from app.models.mixins import utc_now
from app.repositories.import_task_repository import ImportTaskRepository
from app.schemas.import_data import ImportExecutionResult, ImportValidationResult
from app.security.actor import ActorContext, MaintenanceRole
from app.services.import_execution_principal import (
    INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE,
    INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE,
)
from app.services.import_task_service import ImportTaskFileStore, ImportTaskService
from app.workers.import_executor import ImportTaskExecutor, recover_stale_import_tasks


class _NoopImportService:
    def validate(
        self,
        session,
        *,
        tenant_id: str,
        content: bytes,
        filename: str,
        mapping=None,
        task_id: str | None = None,
    ) -> ImportValidationResult:
        del session, tenant_id, content, filename, mapping, task_id
        return ImportValidationResult(
            valid=True,
            sheet_counts={},
            errors=[],
            warnings=[],
            preview={},
        )

    def apply(
        self,
        session,
        *,
        actor: ActorContext,
        task_id: str,
        content: bytes,
        filename: str,
        mapping=None,
    ) -> ImportExecutionResult:
        del session, actor, task_id, content, filename, mapping
        return ImportExecutionResult(
            imported=True,
            created={},
            updated={},
            total_rows=0,
        )


class _RecordingExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, str]] = []

    def submit(self, task_id: str, tenant_id: str) -> bool:
        self.submissions.append((task_id, tenant_id))
        return True


def _service(tmp_path: Path) -> ImportTaskService:
    return ImportTaskService(
        repository=ImportTaskRepository(),
        file_store=ImportTaskFileStore(root=tmp_path),
        task_ttl_seconds=1800,
        max_size_mb=10,
    )


def _task(
    *,
    session,
    file_store: ImportTaskFileStore,
    tenant_id: str = "tenant-a",
    uploader_id: str = "contributor-a",
    status: ImportTaskStatus = ImportTaskStatus.QUEUED,
    principal: str = "missing",
) -> MasterDataImportTask:
    task_id = str(uuid.uuid4())
    content = create_template_bytes()
    file_path = file_store.write_source(
        task_id=task_id,
        content=content,
        original_filename="principal-recovery.xlsx",
    )
    task = MasterDataImportTask(
        id=task_id,
        tenant_id=tenant_id,
        created_by_user_id=uploader_id,
        created_by_request_id="upload-request",
        original_filename="principal-recovery.xlsx",
        file_path=file_path,
        file_sha256=file_store.sha256(content),
        template_version="1.0",
        status=status,
        mapping_json={},
        sheet_summary_json={},
        preview_json={},
        errors_json=[],
        warnings_json=[],
        expires_at=utc_now() + timedelta(minutes=30),
    )
    if principal == "admin":
        task.execution_user_id = "winning-admin"
        task.execution_roles_json = [MaintenanceRole.ADMIN.value]
        task.execution_request_id = "winning-request"
        task.execution_token_id = "winning-token"
        task.queued_at = utc_now()
    elif principal == "contributor":
        task.execution_user_id = "invalid-contributor"
        task.execution_roles_json = [MaintenanceRole.CONTRIBUTOR.value]
        task.execution_request_id = "invalid-request"
        task.execution_token_id = "invalid-token"
        task.queued_at = utc_now()
    elif principal != "missing":
        raise ValueError(f"unsupported principal fixture: {principal}")
    if status is ImportTaskStatus.RUNNING:
        task.started_at = utc_now()
    session.add(task)
    session.commit()
    return task


def _recovery_admin() -> ActorContext:
    return ActorContext(
        user_id="recovery-admin",
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
        request_id="recovery-request",
        token_id="recovery-token",
    )


@pytest.mark.parametrize("principal", ["missing", "contributor"])
def test_admin_reclaims_invalid_queued_execution_principal(
    tmp_path: Path,
    session,
    principal: str,
) -> None:
    service = _service(tmp_path)
    task = _task(
        session=session,
        file_store=service.file_store,
        principal=principal,
    )
    original_version = task.version
    actor = _recovery_admin()

    queued, should_submit = service.queue_for_execution(
        session,
        actor=actor,
        task_id=task.id,
        max_pending_tasks=10,
    )

    assert should_submit is True
    assert queued.status is ImportTaskStatus.QUEUED
    assert queued.version == original_version + 1
    assert queued.execution_user_id == actor.user_id
    assert queued.execution_roles_json == [MaintenanceRole.ADMIN.value]
    assert queued.execution_request_id == actor.request_id
    assert queued.execution_token_id == actor.token_id
    assert queued.queued_at is not None
    assert queued.error_code is None
    assert queued.error_message is None


def test_duplicate_execute_preserves_valid_winning_principal(
    tmp_path: Path,
    session,
) -> None:
    service = _service(tmp_path)
    task = _task(
        session=session,
        file_store=service.file_store,
        principal="admin",
    )
    original_version = task.version

    queued, should_submit = service.queue_for_execution(
        session,
        actor=_recovery_admin(),
        task_id=task.id,
        max_pending_tasks=10,
    )

    assert should_submit is True
    assert queued.version == original_version
    assert queued.execution_user_id == "winning-admin"
    assert queued.execution_roles_json == [MaintenanceRole.ADMIN.value]
    assert queued.execution_request_id == "winning-request"
    assert queued.execution_token_id == "winning-token"


def test_worker_invalid_principal_returns_task_to_requeueable_state(
    tmp_path: Path,
    session,
) -> None:
    file_store = ImportTaskFileStore(root=tmp_path)
    task = _task(
        session=session,
        file_store=file_store,
        principal="contributor",
    )
    worker = ImportTaskExecutor(
        session_factory=SessionLocal,
        file_store=file_store,
        import_service=_NoopImportService(),
        max_workers=1,
    )
    try:
        with pytest.raises(Exception) as raised:
            worker.run_once(task_id=task.id, tenant_id=task.tenant_id)
    finally:
        worker.shutdown(wait=False)

    assert getattr(raised.value, "code", None) == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    recovered = session.get(MasterDataImportTask, task.id)
    assert recovered is not None
    assert recovered.status is ImportTaskStatus.PREVIEW_VALID
    assert recovered.execution_user_id is None
    assert recovered.execution_roles_json is None
    assert recovered.execution_request_id is None
    assert recovered.execution_token_id is None
    assert recovered.queued_at is None
    assert recovered.started_at is None
    assert recovered.finished_at is None
    assert recovered.error_code == INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE
    assert recovered.error_message == INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE


def test_restart_recovery_partitions_valid_and_invalid_principals(
    tmp_path: Path,
    session,
) -> None:
    file_store = ImportTaskFileStore(root=tmp_path)
    valid_queued = _task(
        session=session,
        file_store=file_store,
        status=ImportTaskStatus.QUEUED,
        principal="admin",
    )
    valid_running = _task(
        session=session,
        file_store=file_store,
        status=ImportTaskStatus.RUNNING,
        principal="admin",
    )
    invalid_queued = _task(
        session=session,
        file_store=file_store,
        status=ImportTaskStatus.QUEUED,
        principal="missing",
    )
    invalid_running = _task(
        session=session,
        file_store=file_store,
        status=ImportTaskStatus.RUNNING,
        principal="contributor",
    )
    executor = _RecordingExecutor()

    recover_stale_import_tasks(
        session,
        file_store=file_store,
        executor=executor,
    )

    session.expire_all()
    assert session.get(MasterDataImportTask, valid_queued.id).status is (
        ImportTaskStatus.QUEUED
    )
    recovered_valid_running = session.get(
        MasterDataImportTask,
        valid_running.id,
    )
    assert recovered_valid_running.status is ImportTaskStatus.QUEUED
    assert recovered_valid_running.started_at is None
    assert set(executor.submissions) == {
        (valid_queued.id, valid_queued.tenant_id),
        (valid_running.id, valid_running.tenant_id),
    }

    for task in (invalid_queued, invalid_running):
        recovered = session.get(MasterDataImportTask, task.id)
        assert recovered.status is ImportTaskStatus.PREVIEW_VALID
        assert recovered.execution_user_id is None
        assert recovered.execution_roles_json is None
        assert recovered.execution_request_id is None
        assert recovered.execution_token_id is None
        assert recovered.queued_at is None
        assert recovered.started_at is None
        assert recovered.finished_at is None
        assert recovered.error_code == INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE
        assert recovered.error_message == INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE



def test_worker_expires_task_when_principal_recovery_crosses_expiry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session,
) -> None:
    import app.workers.import_executor as executor_module

    file_store = ImportTaskFileStore(root=tmp_path)
    task = _task(
        session=session,
        file_store=file_store,
        principal="contributor",
    )
    before_expiry = utc_now()
    after_expiry = before_expiry + timedelta(seconds=2)
    task.expires_at = before_expiry + timedelta(seconds=1)
    session.commit()
    times = iter((before_expiry, after_expiry, after_expiry, after_expiry, after_expiry))
    monkeypatch.setattr(executor_module, "utc_now", lambda: next(times))
    worker = ImportTaskExecutor(
        session_factory=SessionLocal,
        file_store=file_store,
        import_service=_NoopImportService(),
        max_workers=1,
    )

    try:
        worker.run_once(task_id=task.id, tenant_id=task.tenant_id)
    finally:
        worker.shutdown(wait=False)

    session.expire_all()
    expired = session.get(MasterDataImportTask, task.id)
    assert expired is not None
    assert expired.status is ImportTaskStatus.EXPIRED
    assert expired.error_code == "IMPORT_TASK_EXPIRED"
    assert expired.error_message == "Import task expired"
    assert expired.finished_at == after_expiry.replace(tzinfo=None)

def test_cross_tenant_admin_cannot_reclaim_invalid_queued_task(
    tmp_path: Path,
    session,
) -> None:
    service = _service(tmp_path)
    task = _task(
        session=session,
        file_store=service.file_store,
        principal="missing",
    )
    foreign_admin = ActorContext(
        user_id="foreign-admin",
        tenant_id="tenant-b",
        role=MaintenanceRole.ADMIN,
        request_id="foreign-request",
        token_id="foreign-token",
    )

    with pytest.raises(Exception) as raised:
        service.queue_for_execution(
            session,
            actor=foreign_admin,
            task_id=task.id,
            max_pending_tasks=10,
        )

    assert getattr(raised.value, "code", None) == "RESOURCE_NOT_FOUND"
    session.expire_all()
    unchanged = session.get(MasterDataImportTask, task.id)
    assert unchanged.status is ImportTaskStatus.QUEUED
    assert unchanged.execution_user_id is None


def test_startup_recovery_does_not_overwrite_concurrent_admin_reclaim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session,
) -> None:
    import app.workers.import_executor as executor_module

    file_store = ImportTaskFileStore(root=tmp_path)
    service = _service(tmp_path)
    task = _task(
        session=session,
        file_store=file_store,
        principal="contributor",
    )
    winner = _recovery_admin()
    original_validator = executor_module.has_valid_execution_principal
    raced = False

    def reclaim_during_recovery(pending):
        nonlocal raced
        if pending.id == task.id and not raced:
            raced = True
            with SessionLocal() as winner_session:
                service.queue_for_execution(
                    winner_session,
                    actor=winner,
                    task_id=pending.id,
                    max_pending_tasks=10,
                )
        return original_validator(pending)

    monkeypatch.setattr(
        executor_module,
        "has_valid_execution_principal",
        reclaim_during_recovery,
    )
    executor = _RecordingExecutor()

    recover_stale_import_tasks(
        session,
        file_store=file_store,
        executor=executor,
    )

    session.expire_all()
    recovered = session.get(MasterDataImportTask, task.id)
    assert recovered.status is ImportTaskStatus.QUEUED
    assert recovered.execution_user_id == winner.user_id
    assert recovered.execution_roles_json == [MaintenanceRole.ADMIN.value]
    assert recovered.execution_request_id == winner.request_id
    assert recovered.execution_token_id == winner.token_id
    assert executor.submissions == [(task.id, task.tenant_id)]


def test_worker_invalid_principal_recovery_does_not_overwrite_admin_reclaim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session,
) -> None:
    import app.workers.import_executor as executor_module

    file_store = ImportTaskFileStore(root=tmp_path)
    service = ImportTaskService(
        repository=ImportTaskRepository(),
        file_store=file_store,
        task_ttl_seconds=1800,
        max_size_mb=10,
    )
    task = _task(
        session=session,
        file_store=file_store,
        principal="contributor",
    )
    winner = _recovery_admin()
    original_loader = executor_module.execution_actor_from_task
    raced = False

    def reclaim_before_invalid_worker_recovers(pending):
        nonlocal raced
        if not raced:
            raced = True
            with SessionLocal() as winner_session:
                service.queue_for_execution(
                    winner_session,
                    actor=winner,
                    task_id=pending.id,
                    max_pending_tasks=10,
                )
        return original_loader(pending)

    monkeypatch.setattr(
        executor_module,
        "execution_actor_from_task",
        reclaim_before_invalid_worker_recovers,
    )
    worker = ImportTaskExecutor(
        session_factory=SessionLocal,
        file_store=file_store,
        import_service=_NoopImportService(),
        max_workers=1,
    )
    try:
        worker.run_once(task_id=task.id, tenant_id=task.tenant_id)
    finally:
        worker.shutdown(wait=False)

    session.expire_all()
    completed = session.get(MasterDataImportTask, task.id)
    assert completed is not None
    assert completed.status is ImportTaskStatus.SUCCEEDED
    assert completed.execution_user_id == winner.user_id
    assert completed.execution_roles_json == [MaintenanceRole.ADMIN.value]
    assert completed.execution_request_id == winner.request_id
    assert completed.execution_token_id == winner.token_id
