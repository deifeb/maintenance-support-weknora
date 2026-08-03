from __future__ import annotations

import importlib
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from app.db.session import SessionLocal
from app.importers.inspection import inspect_workbook
from app.importers.template import create_template_bytes
from app.models.catalog import SparePart
from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.models.mixins import utc_now
from app.schemas.import_data import (
    ImportExecutionResult,
    ImportValidationResult,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.import_task_service import (
    ImportTaskFileStore,
)
from sqlalchemy import func, select


class FakeWorkerImportService:
    def __init__(
        self,
        *,
        fail_after_write: bool = False,
    ) -> None:
        self.fail_after_write = fail_after_write
        self.validate_calls = 0
        self.apply_calls = 0

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
        self.validate_calls += 1
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
        del task_id, content, filename, mapping
        self.apply_calls += 1

        if self.fail_after_write:
            session.add(
                SparePart(
                    tenant_id=actor.tenant_id,
                    code="ROLLBACK-PROBE",
                    name="must rollback",
                    unit="件",
                )
            )
            session.flush()
            raise RuntimeError(
                "sensitive late transaction detail"
            )

        return ImportExecutionResult(
            imported=True,
            created={},
            updated={},
            total_rows=0,
        )


def _mapping(
    content: bytes,
) -> dict[str, dict[str, str]]:
    inspection = inspect_workbook(content)
    return {
        sheet["name"]: sheet["suggested_mapping"]
        for sheet in inspection["sheets"]
    }


def _queued_task(
    *,
    session,
    file_store: ImportTaskFileStore,
    tenant_id: str,
    user_id: str,
    content: bytes,
) -> MasterDataImportTask:
    task_id = str(uuid.uuid4())
    file_path = file_store.write_source(
        task_id=task_id,
        content=content,
        original_filename="master-data.xlsx",
    )
    task = MasterDataImportTask(
        id=task_id,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        created_by_request_id="request-worker-red",
        original_filename="master-data.xlsx",
        file_path=file_path,
        file_sha256=file_store.sha256(content),
        template_version="1.0",
        status=ImportTaskStatus.QUEUED,
        mapping_json=_mapping(content),
        sheet_summary_json={},
        preview_json={},
        errors_json=[],
        warnings_json=[],
        result_json=None,
        expires_at=utc_now() + timedelta(minutes=30),
    )
    session.add(task)
    session.commit()
    return task


def _build_worker(
    *,
    file_store: ImportTaskFileStore,
    import_service: FakeWorkerImportService,
):
    module = importlib.import_module(
        "app.workers.import_executor"
    )
    return module.ImportTaskExecutor(
        session_factory=SessionLocal,
        file_store=file_store,
        import_service=import_service,
        max_workers=1,
    )


def test_execute_revalidates_file_hash_before_writing(
    tmp_path: Path,
    session,
    actor_admin,
):
    file_store = ImportTaskFileStore(root=tmp_path)
    import_service = FakeWorkerImportService()
    content = create_template_bytes()
    task = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_admin.tenant_id,
        user_id=actor_admin.user_id,
        content=content,
    )
    before = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    file_store.write_source(
        task_id=task.id,
        content=b"tampered",
        original_filename=task.original_filename,
    )

    worker = _build_worker(
        file_store=file_store,
        import_service=import_service,
    )
    try:
        worker.run_once(
            task_id=task.id,
            tenant_id=task.tenant_id,
            user_id=task.created_by_user_id,
            execution_role=MaintenanceRole.ADMIN,
        )
    finally:
        worker.shutdown(wait=False)

    session.rollback()
    refreshed = session.get(
        MasterDataImportTask,
        task.id,
    )
    after = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    assert refreshed is not None
    assert refreshed.status is ImportTaskStatus.FAILED
    assert (
        refreshed.error_code
        == "IMPORT_FILE_HASH_MISMATCH"
    )
    assert after == before
    assert import_service.validate_calls == 0
    assert import_service.apply_calls == 0


def test_failed_business_transaction_writes_no_partial_rows(
    tmp_path: Path,
    session,
    actor_admin,
):
    file_store = ImportTaskFileStore(root=tmp_path)
    import_service = FakeWorkerImportService(
        fail_after_write=True
    )
    content = create_template_bytes()
    task = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_admin.tenant_id,
        user_id=actor_admin.user_id,
        content=content,
    )
    before = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    worker = _build_worker(
        file_store=file_store,
        import_service=import_service,
    )
    try:
        worker.run_once(
            task_id=task.id,
            tenant_id=task.tenant_id,
            user_id=task.created_by_user_id,
            execution_role=MaintenanceRole.ADMIN,
        )
    finally:
        worker.shutdown(wait=False)

    session.rollback()
    refreshed = session.get(
        MasterDataImportTask,
        task.id,
    )
    after = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    assert refreshed is not None
    assert refreshed.status is ImportTaskStatus.FAILED
    assert (
        refreshed.error_code
        == "IMPORT_EXECUTION_FAILED"
    )
    assert refreshed.error_message
    assert (
        "sensitive late transaction detail"
        not in refreshed.error_message
    )
    assert after == before
    assert import_service.validate_calls == 1
    assert import_service.apply_calls == 1


def test_worker_rejects_non_admin_execution_role_without_starting_task(
    tmp_path: Path,
    session,
    actor_contributor,
):
    file_store = ImportTaskFileStore(root=tmp_path)
    import_service = FakeWorkerImportService()
    task = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_contributor.tenant_id,
        user_id=actor_contributor.user_id,
        content=create_template_bytes(),
    )
    worker = _build_worker(
        file_store=file_store,
        import_service=import_service,
    )
    try:
        with pytest.raises(Exception) as raised:
            worker.run_once(
                task_id=task.id,
                tenant_id=task.tenant_id,
                user_id=task.created_by_user_id,
                execution_role=MaintenanceRole.CONTRIBUTOR,
            )
    finally:
        worker.shutdown(wait=False)

    assert getattr(raised.value, "code", None) == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    assert session.get(MasterDataImportTask, task.id).status is ImportTaskStatus.QUEUED
    assert import_service.validate_calls == 0
    assert import_service.apply_calls == 0
