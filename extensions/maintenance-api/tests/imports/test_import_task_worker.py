from __future__ import annotations

import importlib
import inspect
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from app.db.session import SessionLocal
from app.importers.inspection import inspect_workbook
from app.importers.template import SHEET_SPECS, create_template_bytes
from app.models.catalog import SparePart
from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.models.inventory_ledger import (
    InventoryTargetReceipt,
    InventoryTransaction,
)
from app.models.mixins import utc_now
from app.schemas.import_data import (
    ImportExecutionResult,
    ImportValidationResult,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.import_execution_principal import (
    INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE,
    INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE,
)
from app.services.import_service import master_data_import_service
from app.services.import_task_service import (
    ImportTaskFileStore,
)
from openpyxl import load_workbook
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
        self.applied_actors: list[ActorContext] = []

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
        self.applied_actors.append(actor)

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


def _ledger_inventory_workbook() -> bytes:
    workbook = load_workbook(BytesIO(master_data_import_service.template_bytes()))
    rows = {
        "04_维修器材": {
            "operation": "CREATE",
            "code": "SP-AUDIT",
            "name": "Audit spare",
            "unit": "EA",
        },
        "07_库房": {
            "operation": "CREATE",
            "code": "WH-AUDIT",
            "name": "Audit warehouse",
            "status": "NORMAL",
            "is_active": True,
        },
        "08_库存": {
            "operation": "CREATE",
            "warehouse_code": "WH-AUDIT",
            "spare_part_code": "SP-AUDIT",
            "on_hand_quantity": "5.0000",
            "reserved_quantity": "1.0000",
            "damaged_quantity": "0.0000",
            "quarantined_quantity": "0.0000",
            "in_transit_quantity": "2.0000",
            "safety_stock": "1.0000",
            "reorder_point": "2.0000",
            "maximum_stock": "10.0000",
        },
    }
    for sheet_name, values in rows.items():
        workbook[sheet_name].append(
            [values.get(field) for field, _header, _required in SHEET_SPECS[sheet_name]]
        )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


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
    task.execution_user_id = user_id
    task.execution_roles_json = [MaintenanceRole.ADMIN.value]
    task.execution_request_id = "request-execute-admin"
    task.execution_token_id = "token-execute-admin"
    task.queued_at = utc_now()
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
    task.execution_roles_json = [MaintenanceRole.CONTRIBUTOR.value]
    session.commit()
    try:
        with pytest.raises(Exception) as raised:
            worker.run_once(
                task_id=task.id,
                tenant_id=task.tenant_id,
            )
    finally:
        worker.shutdown(wait=False)

    assert getattr(raised.value, "code", None) == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    recovered = session.get(MasterDataImportTask, task.id)
    assert recovered.status is ImportTaskStatus.PREVIEW_VALID
    assert recovered.error_code == INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE
    assert recovered.error_message == INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE
    assert recovered.execution_user_id is None
    assert recovered.execution_roles_json is None
    assert import_service.validate_calls == 0
    assert import_service.apply_calls == 0


def test_worker_public_entrypoints_do_not_accept_caller_principal_markers():
    module = importlib.import_module("app.workers.import_executor")
    assert set(inspect.signature(module.ImportTaskExecutor.submit).parameters) == {
        "self",
        "task_id",
        "tenant_id",
    }
    assert set(inspect.signature(module.ImportTaskExecutor.run_once).parameters) == {
        "self",
        "task_id",
        "tenant_id",
    }


def test_worker_audit_uses_persisted_execution_admin_not_uploader(
    tmp_path,
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
    task.execution_user_id = "different-admin"
    task.execution_roles_json = [MaintenanceRole.ADMIN.value]
    task.execution_request_id = "admin-execute-request"
    task.execution_token_id = "admin-execute-token"
    session.commit()
    worker = _build_worker(file_store=file_store, import_service=import_service)
    try:
        worker.run_once(
            task_id=task.id,
            tenant_id=task.tenant_id,
        )
    finally:
        worker.shutdown(wait=False)

    assert len(import_service.applied_actors) == 1
    execution_actor = import_service.applied_actors[0]
    assert execution_actor == ActorContext(
        user_id="different-admin",
        tenant_id=actor_contributor.tenant_id,
        role=MaintenanceRole.ADMIN,
        request_id="admin-execute-request",
        token_id="admin-execute-token",
    )


def test_worker_rejects_non_admin_persisted_principal_from_database(
    tmp_path,
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
    task.execution_roles_json = [MaintenanceRole.CONTRIBUTOR.value]
    session.commit()
    worker = _build_worker(file_store=file_store, import_service=import_service)
    try:
        with pytest.raises(Exception) as raised:
            worker.run_once(
                task_id=task.id,
                tenant_id=task.tenant_id,
            )
    finally:
        worker.shutdown(wait=False)

    assert getattr(raised.value, "code", None) == "INSUFFICIENT_MAINTENANCE_ROLE"
    session.expire_all()
    recovered = session.get(MasterDataImportTask, task.id)
    assert recovered.status is ImportTaskStatus.PREVIEW_VALID
    assert recovered.error_code == INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE
    assert recovered.error_message == INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE
    assert recovered.execution_user_id is None
    assert recovered.execution_roles_json is None
    assert import_service.apply_calls == 0


class _RecordingRecoveryExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, str]] = []

    def submit(self, task_id: str, tenant_id: str) -> bool:
        self.submissions.append((task_id, tenant_id))
        return True


def test_restart_recovery_resets_running_and_resubmits_all_durable_queued_tasks(
    tmp_path,
    session,
    actor_admin,
):
    module = importlib.import_module("app.workers.import_executor")
    file_store = ImportTaskFileStore(root=tmp_path)
    content = create_template_bytes()
    running = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_admin.tenant_id,
        user_id=actor_admin.user_id,
        content=content,
    )
    queued = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_admin.tenant_id,
        user_id=actor_admin.user_id,
        content=content,
    )
    running.status = ImportTaskStatus.RUNNING
    running.started_at = utc_now()
    session.commit()
    executor = _RecordingRecoveryExecutor()

    module.recover_stale_import_tasks(
        session,
        file_store=file_store,
        executor=executor,
    )

    session.expire_all()
    assert session.get(MasterDataImportTask, running.id).status is ImportTaskStatus.QUEUED
    assert session.get(MasterDataImportTask, running.id).started_at is None
    assert session.get(MasterDataImportTask, queued.id).status is ImportTaskStatus.QUEUED
    assert set(executor.submissions) == {
        (running.id, running.tenant_id),
        (queued.id, queued.tenant_id),
    }


def test_worker_ledger_transaction_audit_uses_persisted_execute_admin(
    tmp_path,
    session,
    actor_contributor,
):
    file_store = ImportTaskFileStore(root=tmp_path)
    content = _ledger_inventory_workbook()
    task = _queued_task(
        session=session,
        file_store=file_store,
        tenant_id=actor_contributor.tenant_id,
        user_id=actor_contributor.user_id,
        content=content,
    )
    task.execution_user_id = "audit-admin"
    task.execution_roles_json = [MaintenanceRole.ADMIN.value]
    task.execution_request_id = "audit-execute-request"
    task.execution_token_id = "audit-execute-token"
    session.commit()
    worker = _build_worker(
        file_store=file_store,
        import_service=master_data_import_service,
    )
    try:
        worker.run_once(task_id=task.id, tenant_id=task.tenant_id)
    finally:
        worker.shutdown(wait=False)

    session.expire_all()
    transaction = session.scalar(select(InventoryTransaction))
    receipt = session.scalar(select(InventoryTargetReceipt))
    assert session.get(MasterDataImportTask, task.id).status is ImportTaskStatus.SUCCEEDED
    assert transaction is not None
    assert (
        transaction.actor_user_id,
        transaction.actor_roles_json,
        transaction.request_id,
    ) == ("audit-admin", [MaintenanceRole.ADMIN.value], "audit-execute-request")
    assert receipt is not None
    assert (
        receipt.actor_user_id,
        receipt.actor_roles_json,
        receipt.request_id,
    ) == ("audit-admin", [MaintenanceRole.ADMIN.value], "audit-execute-request")
