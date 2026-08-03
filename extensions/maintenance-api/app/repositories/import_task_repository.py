from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.models.mixins import utc_now


class ImportTaskRepository:
    def create(
        self,
        session: Session,
        task: MasterDataImportTask,
    ) -> MasterDataImportTask:
        session.add(task)
        session.flush()
        return task

    def get_visible(
        self,
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
                MasterDataImportTask.tenant_id == tenant_id,
                MasterDataImportTask.created_by_user_id
                == user_id,
                MasterDataImportTask.expires_at > utc_now(),
                MasterDataImportTask.status
                != ImportTaskStatus.EXPIRED,
            )
        )

    def get_for_execution(
        self,
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
                MasterDataImportTask.tenant_id == tenant_id,
                MasterDataImportTask.expires_at > utc_now(),
                MasterDataImportTask.status != ImportTaskStatus.EXPIRED,
            )
        )


import_task_repository = ImportTaskRepository()
