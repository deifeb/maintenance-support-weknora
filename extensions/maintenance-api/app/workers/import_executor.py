from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

from sqlalchemy import select
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
from app.security.actor import ActorContext, MaintenanceRole
from app.services.import_service import (
    MasterDataImportService,
    master_data_import_service,
)
from app.services.import_task_service import (
    ImportTaskFileStore,
)

SessionFactory = Callable[[], Session]
TaskKey = tuple[str, str]


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
        user_id: str,
        execution_role: MaintenanceRole,
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
                user_id,
                execution_role,
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
        user_id: str,
        execution_role: MaintenanceRole,
    ) -> None:
        key = (tenant_id, task_id)
        try:
            self.run_once(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
                execution_role=execution_role,
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
        user_id: str,
    ) -> MasterDataImportTask | None:
        return session.scalar(
            select(MasterDataImportTask)
            .execution_options(populate_existing=True)
            .where(
                MasterDataImportTask.id == task_id,
                MasterDataImportTask.tenant_id
                == tenant_id,
                MasterDataImportTask.created_by_user_id
                == user_id,
            )
        )

    def _start_task(
        self,
        *,
        task_id: str,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        session = self.session_factory()
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
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
        user_id: str,
        exc: Exception,
    ) -> None:
        session = self.session_factory()
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
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
        user_id: str,
        execution_role: MaintenanceRole,
    ) -> None:
        if execution_role is not MaintenanceRole.ADMIN:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=execution_role.value,
                request_id=f"import-task:{task_id}",
            )
        if not self._start_task(
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
        ):
            return

        session = self.session_factory()
        try:
            task = self._load_exact(
                session,
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if (
                task is None
                or task.status
                is not ImportTaskStatus.RUNNING
            ):
                return

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
                actor=ActorContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=execution_role,
                    request_id=task.created_by_request_id,
                    token_id=f"import-task:{task.id}",
                ),
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
        except Exception as exc:
            session.rollback()
            self._persist_failure(
                task_id=task_id,
                tenant_id=tenant_id,
                user_id=user_id,
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
