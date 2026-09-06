from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AppException,
    BusinessValidationError,
    InsufficientMaintenanceRoleError,
)
from app.db.session import SessionLocal
from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.models.mixins import utc_now
from app.services.import_execution_principal import (
    INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE,
    INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE,
    execution_actor_from_task,
    has_valid_execution_principal,
)
from app.services.import_service import (
    MasterDataImportService,
    master_data_import_service,
)
from app.services.import_task_service import (
    ImportTaskFileStore,
)

SessionFactory = Callable[[], Session]
TaskKey = tuple[str, str]


def _recover_invalid_execution_principal(
    session: Session,
    *,
    task: MasterDataImportTask,
    now: datetime,
) -> bool:
    if task.status not in {
        ImportTaskStatus.QUEUED,
        ImportTaskStatus.RUNNING,
    }:
        return False
    result = session.execute(
        update(MasterDataImportTask)
        .where(
            MasterDataImportTask.id == task.id,
            MasterDataImportTask.tenant_id == task.tenant_id,
            MasterDataImportTask.status == task.status,
            MasterDataImportTask.version == task.version,
            MasterDataImportTask.expires_at > now,
        )
        .values(
            status=ImportTaskStatus.PREVIEW_VALID,
            execution_user_id=None,
            execution_roles_json=None,
            execution_request_id=None,
            execution_token_id=None,
            queued_at=None,
            started_at=None,
            finished_at=None,
            error_code=INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE,
            error_message=INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE,
            version=MasterDataImportTask.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


class ImportTaskExecutor:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        file_store: ImportTaskFileStore,
        import_service: MasterDataImportService,
        max_workers: int,
    ) -> None:
        if max_workers <= 0:
            raise ValueError(
                "max_workers must be positive"
            )

        self.session_factory = session_factory
        self.file_store = file_store
        self.import_service = import_service
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._running: set[TaskKey] = set()
        self._lock = Lock()

    def _pool(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="master-data-import",
            )
        return self._executor

    def submit(
        self,
        task_id: str,
        tenant_id: str,
    ) -> bool:
        key = (tenant_id, task_id)
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)

        try:
            self._pool().submit(
                self._run_guarded,
                task_id,
                tenant_id,
            )
        except Exception:
            with self._lock:
                self._running.discard(key)
            raise
        return True

    def _run_guarded(
        self,
        task_id: str,
        tenant_id: str,
    ) -> None:
        key = (tenant_id, task_id)
        try:
            self.run_once(
                task_id=task_id,
                tenant_id=tenant_id,
            )
        finally:
            with self._lock:
                self._running.discard(key)

    @staticmethod
    def _is_expired(expires_at: datetime) -> bool:
        now = utc_now()
        if expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return expires_at <= now

    @staticmethod
    def _load_exact(
        session: Session,
        *,
        task_id: str,
        tenant_id: str,
    ) -> MasterDataImportTask | None:
        return session.scalar(
            select(MasterDataImportTask)
            .execution_options(populate_existing=True)
            .where(
                MasterDataImportTask.id == task_id,
                MasterDataImportTask.tenant_id
                == tenant_id,
            )
        )

    def _start_task(
        self,
        *,
        task_id: str,
        tenant_id: str,
    ) -> bool:
        session = self.session_factory()
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
            )
            if (
                task is None
                or task.status
                is not ImportTaskStatus.QUEUED
            ):
                return False

            if self._is_expired(task.expires_at):
                task.status = ImportTaskStatus.EXPIRED
                task.error_code = "IMPORT_TASK_EXPIRED"
                task.error_message = "Import task expired"
                task.finished_at = utc_now()
                session.commit()
                return False

            task.status = ImportTaskStatus.RUNNING
            task.started_at = utc_now()
            task.finished_at = None
            task.error_code = None
            task.error_message = None
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _failure_details(
        exc: Exception,
    ) -> tuple[str, str]:
        if isinstance(exc, AppException):
            return exc.code, exc.message
        return (
            "IMPORT_EXECUTION_FAILED",
            "Import execution failed",
        )

    def _persist_failure(
        self,
        *,
        task_id: str,
        tenant_id: str,
        exc: Exception,
    ) -> None:
        session = self.session_factory()
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
            )
            if task is None:
                return
            if task.status in {
                ImportTaskStatus.SUCCEEDED,
                ImportTaskStatus.EXPIRED,
            }:
                return

            code, message = self._failure_details(exc)
            task.status = ImportTaskStatus.FAILED
            task.error_code = code
            task.error_message = message
            task.finished_at = utc_now()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run_once(
        self,
        *,
        task_id: str,
        tenant_id: str,
    ) -> None:
        principal_session = self.session_factory()
        try:
            pending = self._load_exact(
                principal_session,
                task_id=task_id,
                tenant_id=tenant_id,
            )
            if (
                pending is None
                or pending.status is not ImportTaskStatus.QUEUED
            ):
                return
            if not self._is_expired(pending.expires_at):
                try:
                    execution_actor_from_task(pending)
                except InsufficientMaintenanceRoleError:
                    recovered = _recover_invalid_execution_principal(
                        principal_session,
                        task=pending,
                        now=utc_now(),
                    )
                    if recovered:
                        principal_session.commit()
                        raise
                    principal_session.rollback()
                    current = self._load_exact(
                        principal_session,
                        task_id=task_id,
                        tenant_id=tenant_id,
                    )
                    if (
                        current is None
                        or current.status
                        is not ImportTaskStatus.QUEUED
                    ):
                        raise
                    if (
                        not has_valid_execution_principal(current)
                        and not self._is_expired(
                            current.expires_at
                        )
                    ):
                        raise
        except InsufficientMaintenanceRoleError:
            raise
        except Exception:
            principal_session.rollback()
            raise
        finally:
            principal_session.close()
        if not self._start_task(
            task_id=task_id,
            tenant_id=tenant_id,
        ):
            return

        session = self.session_factory()
        task: MasterDataImportTask | None = None
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
            )
            if (
                task is None
                or task.status
                is not ImportTaskStatus.RUNNING
            ):
                return
            execution_actor = execution_actor_from_task(task)

            content = self.file_store.read_source(
                task.file_path
            )
            if (
                self.file_store.sha256(content)
                != task.file_sha256
            ):
                raise BusinessValidationError(
                    "Import workbook hash does not match",
                    code="IMPORT_FILE_HASH_MISMATCH",
                )

            if self._is_expired(task.expires_at):
                raise BusinessValidationError(
                    "Import task expired",
                    code="IMPORT_TASK_EXPIRED",
                )

            validation = self.import_service.validate(
                session,
                tenant_id=tenant_id,
                content=content,
                filename=task.original_filename,
                mapping=task.mapping_json,
                task_id=task.id,
            )
            if not validation.valid:
                raise BusinessValidationError(
                    "Import workbook validation failed",
                    code="IMPORT_VALIDATION_FAILED",
                )

            result = self.import_service.apply(
                session,
                actor=execution_actor,
                task_id=task.id,
                content=content,
                filename=task.original_filename,
                mapping=task.mapping_json,
            )
            task.status = ImportTaskStatus.SUCCEEDED
            task.result_json = result.model_dump(
                mode="json"
            )
            task.error_code = None
            task.error_message = None
            task.finished_at = utc_now()
            session.commit()
        except InsufficientMaintenanceRoleError:
            if task is not None:
                recovered = _recover_invalid_execution_principal(
                    session,
                    task=task,
                    now=utc_now(),
                )
                if recovered:
                    session.commit()
                else:
                    session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            self._persist_failure(
                task_id=task_id,
                tenant_id=tenant_id,
                exc=exc,
            )
        finally:
            session.close()

    def shutdown(self, wait: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(
                wait=wait,
                cancel_futures=False,
            )
            self._executor = None


def recover_stale_import_tasks(
    session: Session,
    *,
    file_store: ImportTaskFileStore,
    executor: ImportTaskExecutor | None = None,
) -> None:
    now = utc_now()
    stale = list(
        session.scalars(
            select(MasterDataImportTask).where(
                MasterDataImportTask.expires_at <= now,
                MasterDataImportTask.status.in_(
                    (
                        ImportTaskStatus.QUEUED,
                        ImportTaskStatus.RUNNING,
                    )
                ),
            )
        )
    )

    for task in stale:
        task.status = ImportTaskStatus.EXPIRED
        task.error_code = "IMPORT_TASK_EXPIRED"
        task.error_message = "Import task expired"
        task.finished_at = now

    active = list(
        session.scalars(
            select(MasterDataImportTask).where(
                MasterDataImportTask.expires_at > now,
                MasterDataImportTask.status.in_(
                    (
                        ImportTaskStatus.QUEUED,
                        ImportTaskStatus.RUNNING,
                    )
                ),
            )
        )
    )
    recoverable: list[TaskKey] = []
    for task in active:
        if not has_valid_execution_principal(task):
            recovered = _recover_invalid_execution_principal(
                session,
                task=task,
                now=now,
            )
            if recovered:
                continue
            current = ImportTaskExecutor._load_exact(
                session,
                task_id=task.id,
                tenant_id=task.tenant_id,
            )
            if (
                current is not None
                and current.status is ImportTaskStatus.QUEUED
                and has_valid_execution_principal(current)
            ):
                recoverable.append(
                    (current.tenant_id, current.id)
                )
            continue
        if task.status is ImportTaskStatus.RUNNING:
            result = session.execute(
                update(MasterDataImportTask)
                .where(
                    MasterDataImportTask.id == task.id,
                    MasterDataImportTask.tenant_id
                    == task.tenant_id,
                    MasterDataImportTask.status
                    == ImportTaskStatus.RUNNING,
                    MasterDataImportTask.version == task.version,
                    MasterDataImportTask.expires_at > now,
                )
                .values(
                    status=ImportTaskStatus.QUEUED,
                    started_at=None,
                    finished_at=None,
                    error_code=None,
                    error_message=None,
                    version=MasterDataImportTask.version + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                current = ImportTaskExecutor._load_exact(
                    session,
                    task_id=task.id,
                    tenant_id=task.tenant_id,
                )
                if (
                    current is not None
                    and current.status is ImportTaskStatus.QUEUED
                    and has_valid_execution_principal(current)
                ):
                    recoverable.append(
                        (current.tenant_id, current.id)
                    )
                continue
        recoverable.append((task.tenant_id, task.id))

    terminal = list(
        session.scalars(
            select(MasterDataImportTask).where(
                MasterDataImportTask.expires_at <= now,
                MasterDataImportTask.status.in_(
                    (
                        ImportTaskStatus.SUCCEEDED,
                        ImportTaskStatus.FAILED,
                        ImportTaskStatus.EXPIRED,
                    )
                ),
            )
        )
    )
    session.commit()

    if executor is not None:
        for tenant_id, task_id in recoverable:
            executor.submit(task_id, tenant_id)

    for task in terminal:
        try:
            file_store.delete_task_files(task.id)
        except (OSError, ValueError):
            continue


_settings = get_settings()
import_task_executor = ImportTaskExecutor(
    session_factory=SessionLocal,
    file_store=ImportTaskFileStore(
        root=_settings.master_data_import_dir
    ),
    import_service=master_data_import_service,
    max_workers=(
        _settings.master_data_import_worker_count
    ),
)
