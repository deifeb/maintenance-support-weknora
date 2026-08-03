from __future__ import annotations

from datetime import timedelta

from app.models.mixins import utc_now
from app.services.import_service import master_data_import_service


def _build_service(tmp_path):
    from app.repositories.import_task_repository import (
        ImportTaskRepository,
    )
    from app.services.import_task_service import (
        ImportTaskFileStore,
        ImportTaskService,
    )

    repository = ImportTaskRepository()
    file_store = ImportTaskFileStore(root=tmp_path)
    service = ImportTaskService(
        repository=repository,
        file_store=file_store,
        task_ttl_seconds=1800,
        max_size_mb=10,
    )
    return repository, file_store, service


def _upload(session, actor_admin, tmp_path, *, filename="master-data.xlsx"):
    repository, file_store, service = _build_service(tmp_path)
    content = master_data_import_service.template_bytes()
    task = service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename=filename,
    )
    return repository, file_store, service, task, content


def test_import_task_status_values_are_exact():
    from app.models.import_task import ImportTaskStatus

    assert [item.value for item in ImportTaskStatus] == [
        "UPLOADED",
        "PREVIEWING",
        "PREVIEW_VALID",
        "PREVIEW_INVALID",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "EXPIRED",
    ]


def test_uploaded_task_uses_uuid_path_not_original_filename(
    session,
    actor_admin,
    tmp_path,
):
    from app.models.import_task import ImportTaskStatus

    _, file_store, _, task, content = _upload(
        session,
        actor_admin,
        tmp_path,
        filename="../../escape.xlsx",
    )

    assert task.original_filename == "escape.xlsx"
    assert task.file_path == f"{task.id}/source.xlsx"
    assert ".." not in task.file_path
    assert task.tenant_id == actor_admin.tenant_id
    assert task.created_by_user_id == actor_admin.user_id
    assert task.created_by_request_id == actor_admin.request_id
    assert task.status is ImportTaskStatus.UPLOADED
    assert len(task.file_sha256) == 64
    assert (tmp_path / task.file_path).is_file()
    assert file_store.read_source(task.file_path) == content


def test_other_tenant_task_is_reported_as_not_found(
    session,
    actor_admin,
    tmp_path,
):
    repository, _, _, task, _ = _upload(
        session,
        actor_admin,
        tmp_path,
    )

    assert (
        repository.get_visible(
            session,
            task_id=task.id,
            tenant_id="tenant-b",
            user_id=task.created_by_user_id,
        )
        is None
    )


def test_other_user_task_is_reported_as_not_found(
    session,
    actor_admin,
    tmp_path,
):
    repository, _, _, task, _ = _upload(
        session,
        actor_admin,
        tmp_path,
    )

    assert (
        repository.get_visible(
            session,
            task_id=task.id,
            tenant_id=task.tenant_id,
            user_id="user-b",
        )
        is None
    )


def test_expired_task_is_not_visible(
    session,
    actor_admin,
    tmp_path,
):
    repository, _, _, task, _ = _upload(
        session,
        actor_admin,
        tmp_path,
    )
    task.expires_at = utc_now() - timedelta(seconds=1)
    session.commit()

    assert (
        repository.get_visible(
            session,
            task_id=task.id,
            tenant_id=task.tenant_id,
            user_id=task.created_by_user_id,
        )
        is None
    )
