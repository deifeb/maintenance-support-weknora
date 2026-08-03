from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.exporters.import_error_excel import (
    build_import_error_workbook,
)
from app.importers.inspection import inspect_workbook
from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.models.mixins import utc_now
from app.repositories.import_task_repository import (
    ImportTaskRepository,
    import_task_repository,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.import_service import (
    master_data_import_service,
)


class ImportTaskFileStore:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise ValueError(
                "Import task path must be relative"
            )

        candidate = (self.root / path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                "Import task path escapes the configured root"
            ) from exc
        return candidate

    @staticmethod
    def _canonical_task_id(task_id: str) -> str:
        return str(uuid.UUID(task_id))

    @staticmethod
    def _safe_original_filename(filename: str) -> str:
        normalized = filename.replace("\\", "/").strip()
        safe_name = Path(normalized).name.strip()
        if safe_name in {"", ".", ".."}:
            raise ValueError(
                "Original filename must not be blank"
            )
        return safe_name

    @staticmethod
    def sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _write(
        self,
        *,
        relative_path: str,
        content: bytes,
    ) -> str:
        destination = self._resolve(relative_path)
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return PurePosixPath(relative_path).as_posix()

    def write_source(
        self,
        *,
        task_id: str,
        content: bytes,
        original_filename: str | None = None,
    ) -> str:
        canonical_id = self._canonical_task_id(task_id)
        if original_filename is not None:
            self._safe_original_filename(
                original_filename
            )
        relative = PurePosixPath(
            canonical_id,
            "source.xlsx",
        )
        return self._write(
            relative_path=relative.as_posix(),
            content=content,
        )

    def read_source(self, relative_path: str) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def write_error_workbook(
        self,
        *,
        task_id: str,
        content: bytes,
    ) -> str:
        canonical_id = self._canonical_task_id(task_id)
        relative = PurePosixPath(
            canonical_id,
            "errors.xlsx",
        )
        return self._write(
            relative_path=relative.as_posix(),
            content=content,
        )

    def read_error_workbook(
        self,
        relative_path: str,
    ) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def delete_error_workbook(
        self,
        task_id: str,
    ) -> None:
        canonical_id = self._canonical_task_id(task_id)
        relative = PurePosixPath(
            canonical_id,
            "errors.xlsx",
        )
        path = self._resolve(relative.as_posix())
        if path.exists():
            path.unlink()

    def delete_task_files(self, task_id: str) -> None:
        canonical_id = self._canonical_task_id(task_id)
        directory = self._resolve(canonical_id)
        if directory.exists():
            shutil.rmtree(directory)

    def delete_task(self, task_id: str) -> None:
        self.delete_task_files(task_id)


class ImportTaskService:
    def __init__(
        self,
        *,
        repository: ImportTaskRepository,
        file_store: ImportTaskFileStore,
        task_ttl_seconds: int,
        max_size_mb: int,
    ) -> None:
        if task_ttl_seconds <= 0:
            raise ValueError(
                "task_ttl_seconds must be positive"
            )
        if max_size_mb <= 0:
            raise ValueError(
                "max_size_mb must be positive"
            )

        self.repository = repository
        self.file_store = file_store
        self.task_ttl_seconds = task_ttl_seconds
        self.max_size_bytes = (
            max_size_mb * 1024 * 1024
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        normalized = filename.replace("\\", "/").strip()
        safe_name = Path(normalized).name.strip()
        if safe_name in {"", ".", ".."}:
            raise BusinessValidationError(
                "Workbook filename is required",
                code="INVALID_IMPORT_FILENAME",
            )
        if not safe_name.lower().endswith(".xlsx"):
            raise BusinessValidationError(
                "Only .xlsx files are accepted",
                code="INVALID_FILE_TYPE",
            )
        return safe_name

    def upload(
        self,
        session: Session,
        *,
        actor: ActorContext,
        content: bytes,
        filename: str,
    ) -> MasterDataImportTask:
        safe_name = self._safe_filename(filename)
        if not content:
            raise BusinessValidationError(
                "Workbook is empty",
                code="EMPTY_IMPORT_FILE",
            )
        if len(content) > self.max_size_bytes:
            raise BusinessValidationError(
                "Workbook exceeds the configured size limit",
                code="FILE_TOO_LARGE",
            )

        inspection = inspect_workbook(content)
        task_id = str(uuid.uuid4())
        relative_path = self.file_store.write_source(
            task_id=task_id,
            original_filename=safe_name,
            content=content,
        )
        task = MasterDataImportTask(
            id=task_id,
            tenant_id=actor.tenant_id,
            created_by_user_id=actor.user_id,
            created_by_request_id=actor.request_id,
            original_filename=safe_name,
            file_path=relative_path,
            file_sha256=self.file_store.sha256(content),
            template_version=inspection[
                "template_version"
            ],
            status=ImportTaskStatus.UPLOADED,
            mapping_json=None,
            sheet_summary_json=inspection[
                "sheet_summary"
            ],
            preview_json=None,
            errors_json=None,
            warnings_json=None,
            result_json=None,
            expires_at=(
                utc_now()
                + timedelta(
                    seconds=self.task_ttl_seconds
                )
            ),
        )

        try:
            self.repository.create(session, task)
            session.commit()
        except Exception:
            session.rollback()
            self.file_store.delete_task_files(task_id)
            raise

        return task

    def _require_for_actor(
        self,
        session: Session,
        *,
        task_id: str,
        actor: ActorContext,
    ) -> MasterDataImportTask:
        task = self.get_for_actor(
            session,
            task_id=task_id,
            actor=actor,
        )
        if task is None:
            raise NotFoundError(
                "master_data_import_task",
                task_id,
            )
        return task

    @staticmethod
    def _sheet_summaries(
        result: Any,
    ) -> list[dict[str, int | str]]:
        invalid_rows: dict[str, set[int]] = {}
        for issue in result.errors:
            if issue.sheet is None or issue.row is None:
                continue
            invalid_rows.setdefault(
                issue.sheet,
                set(),
            ).add(issue.row)

        summaries: list[dict[str, int | str]] = []
        for name, total in result.sheet_counts.items():
            invalid = len(
                invalid_rows.get(name, set())
            )
            summaries.append(
                {
                    "name": name,
                    "total_rows": total,
                    "valid_rows": max(
                        total - invalid,
                        0,
                    ),
                    "invalid_rows": invalid,
                }
            )
        return summaries

    def preview(
        self,
        session: Session,
        *,
        actor: ActorContext,
        task_id: str,
        mapping: dict[str, dict[str, str]],
    ) -> MasterDataImportTask:
        task = self._require_for_actor(
            session,
            task_id=task_id,
            actor=actor,
        )
        allowed_statuses = {
            ImportTaskStatus.UPLOADED,
            ImportTaskStatus.PREVIEW_VALID,
            ImportTaskStatus.PREVIEW_INVALID,
        }
        if task.status not in allowed_statuses:
            raise ConflictError(
                code="IMPORT_TASK_STATE_INVALID",
                message=(
                    "Import task cannot be previewed "
                    f"from status {task.status.value}"
                ),
                details={
                    "task_id": task.id,
                    "status": task.status.value,
                },
            )

        task.status = ImportTaskStatus.PREVIEWING
        task.error_code = None
        task.error_message = None
        session.commit()

        try:
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

            result = master_data_import_service.validate(
                session,
                tenant_id=actor.tenant_id,
                content=content,
                filename=task.original_filename,
                mapping=mapping,
            )
            summaries = self._sheet_summaries(result)

            if result.errors:
                error_content = build_import_error_workbook(
                    errors=result.errors,
                    summaries=summaries,
                )
                task.error_workbook_path = (
                    self.file_store.write_error_workbook(
                        task_id=task.id,
                        content=error_content,
                    )
                )
            else:
                self.file_store.delete_error_workbook(
                    task.id
                )
                task.error_workbook_path = None

            task.mapping_json = mapping
            task.sheet_summary_json = {
                str(summary["name"]): summary
                for summary in summaries
            }
            task.preview_json = result.preview
            task.errors_json = [
                issue.model_dump(mode="json")
                for issue in result.errors
            ]
            task.warnings_json = [
                issue.model_dump(mode="json")
                for issue in result.warnings
            ]
            task.status = (
                ImportTaskStatus.PREVIEW_VALID
                if result.valid
                else ImportTaskStatus.PREVIEW_INVALID
            )
            task.error_code = None
            task.error_message = None
            session.commit()
            return task
        except Exception as exc:
            session.rollback()
            failed = session.get(
                MasterDataImportTask,
                task.id,
            )
            if failed is not None:
                failed.status = ImportTaskStatus.FAILED
                if isinstance(exc, AppException):
                    failed.error_code = exc.code
                    failed.error_message = exc.message
                else:
                    failed.error_code = (
                        "IMPORT_PREVIEW_FAILED"
                    )
                    failed.error_message = (
                        "Import preview failed"
                    )
                try:
                    session.commit()
                except Exception:
                    session.rollback()
            raise

    def queue_for_execution(
        self,
        session: Session,
        *,
        actor: ActorContext,
        task_id: str,
        max_pending_tasks: int,
    ) -> tuple[MasterDataImportTask, bool]:
        if actor.role is not MaintenanceRole.ADMIN:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )
        if max_pending_tasks <= 0:
            raise ValueError(
                "max_pending_tasks must be positive"
            )

        task = self.repository.get_for_execution(
            session,
            task_id=task_id,
            tenant_id=actor.tenant_id,
        )
        if task is None:
            raise NotFoundError("master_data_import_task", task_id)
        terminal_idempotent_statuses = {
            ImportTaskStatus.RUNNING,
            ImportTaskStatus.SUCCEEDED,
        }
        if task.status is ImportTaskStatus.QUEUED:
            return task, True
        if task.status in terminal_idempotent_statuses:
            return task, False

        if task.status is not ImportTaskStatus.PREVIEW_VALID:
            raise ConflictError(
                code="IMPORT_TASK_STATE_INVALID",
                message=(
                    "Import task cannot be executed "
                    f"from status {task.status.value}"
                ),
                details={
                    "task_id": task.id,
                    "status": task.status.value,
                },
            )

        pending_count = session.scalar(
            select(func.count())
            .select_from(MasterDataImportTask)
            .where(
                MasterDataImportTask.tenant_id == actor.tenant_id,
                MasterDataImportTask.status.in_(
                    (
                        ImportTaskStatus.QUEUED,
                        ImportTaskStatus.RUNNING,
                    )
                )
            )
        )
        if int(pending_count or 0) >= max_pending_tasks:
            raise ConflictError(
                code="IMPORT_QUEUE_FULL",
                message="Import execution queue is full",
                details={
                    "max_pending_tasks": max_pending_tasks,
                },
            )

        expected_version = task.version
        now = utc_now()
        result = session.execute(
            update(MasterDataImportTask)
            .where(
                MasterDataImportTask.id == task.id,
                MasterDataImportTask.tenant_id
                == actor.tenant_id,
                MasterDataImportTask.status
                == ImportTaskStatus.PREVIEW_VALID,
                MasterDataImportTask.version
                == expected_version,
                MasterDataImportTask.expires_at > now,
            )
            .values(
                status=ImportTaskStatus.QUEUED,
                version=MasterDataImportTask.version + 1,
                error_code=None,
                error_message=None,
                execution_user_id=actor.user_id,
                execution_roles_json=[actor.role.value],
                execution_request_id=actor.request_id,
                execution_token_id=actor.token_id,
                queued_at=now,
                updated_at=now,
            )
            .execution_options(
                synchronize_session=False
            )
        )

        if result.rowcount != 1:
            session.rollback()
            current = self.repository.get_for_execution(
                session,
                task_id=task_id,
                tenant_id=actor.tenant_id,
            )
            if (
                current is not None
                and current.status is ImportTaskStatus.QUEUED
            ):
                return current, True
            if (
                current is not None
                and current.status in terminal_idempotent_statuses
            ):
                return current, False
            raise ConflictError(
                code="IMPORT_TASK_QUEUE_CONFLICT",
                message=(
                    "Import task queue state changed "
                    "concurrently"
                ),
                details={"task_id": task_id},
            )

        session.commit()
        queued = self.repository.get_for_execution(
            session,
            task_id=task_id,
            tenant_id=actor.tenant_id,
        )
        assert queued is not None
        return queued, True

    def read_error_workbook_for_actor(
        self,
        session: Session,
        *,
        task_id: str,
        actor: ActorContext,
    ) -> bytes:
        task = self._require_for_actor(
            session,
            task_id=task_id,
            actor=actor,
        )
        if not task.error_workbook_path:
            raise NotFoundError(
                "master_data_import_error_workbook",
                task_id,
            )
        try:
            return self.file_store.read_error_workbook(
                task.error_workbook_path
            )
        except FileNotFoundError as exc:
            raise NotFoundError(
                "master_data_import_error_workbook",
                task_id,
            ) from exc

    def get_for_actor(
        self,
        session: Session,
        *,
        task_id: str,
        actor: ActorContext,
    ) -> MasterDataImportTask | None:
        return self.repository.get_visible(
            session,
            task_id=task_id,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
        )


def build_import_task_service(
    *,
    root: Path,
    task_ttl_seconds: int,
    max_size_mb: int,
) -> ImportTaskService:
    return ImportTaskService(
        repository=import_task_repository,
        file_store=ImportTaskFileStore(root=root),
        task_ttl_seconds=task_ttl_seconds,
        max_size_mb=max_size_mb,
    )
