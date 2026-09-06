from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from app.importers.inspection import inspect_workbook
from app.importers.template import create_template_bytes
from app.models.catalog import SparePart
from app.models.import_task import ImportTaskStatus
from app.models.inventory_ledger import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryPolicy,
    InventoryTransaction,
)
from app.repositories.import_task_repository import (
    ImportTaskRepository,
)
from app.schemas.import_data import (
    ImportIssue,
    ImportValidationResult,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.security.dependencies import get_actor
from app.services.import_task_service import (
    ImportTaskFileStore,
    ImportTaskService,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import func, select


class FakeImportService:
    def __init__(
        self,
        result: ImportValidationResult,
    ) -> None:
        self.result = result
        self.validate_calls: list[dict[str, object]] = []
        self.apply_calls = 0

    def validate(
        self,
        session,
        *,
        tenant_id: str,
        content: bytes,
        filename: str,
        mapping=None,
    ) -> ImportValidationResult:
        del session
        self.validate_calls.append(
            {
                "tenant_id": tenant_id,
                "content": content,
                "filename": filename,
                "mapping": mapping,
            }
        )
        return self.result

    def apply(self, *args, **kwargs):
        del args, kwargs
        self.apply_calls += 1
        raise AssertionError(
            "preview must never call apply"
        )


def _mapping(content: bytes) -> dict[str, dict[str, str]]:
    inspection = inspect_workbook(content)
    return {
        sheet["name"]: sheet["suggested_mapping"]
        for sheet in inspection["sheets"]
    }


@pytest.fixture()
def task_service(tmp_path: Path) -> ImportTaskService:
    return ImportTaskService(
        repository=ImportTaskRepository(),
        file_store=ImportTaskFileStore(root=tmp_path),
        task_ttl_seconds=1800,
        max_size_mb=10,
    )


@pytest.fixture()
def task_app(
    monkeypatch: pytest.MonkeyPatch,
    task_service: ImportTaskService,
) -> FastAPI:
    import app.api.v1.master_data.imports as imports_api
    from app.main import create_app

    monkeypatch.setattr(
        imports_api,
        "import_task_service",
        task_service,
        raising=False,
    )
    return create_app()


@contextmanager
def _client(
    app: FastAPI,
    actor: ActorContext,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_actor] = lambda: actor
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_import_task_response_schemas_are_exact():
    import app.schemas.import_data as schemas

    upload = getattr(schemas, "ImportTaskUploadResult")
    preview_request = getattr(
        schemas,
        "ImportPreviewRequest",
    )
    task_view = getattr(schemas, "ImportTaskView")

    assert set(upload.model_fields) == {
        "task_id",
        "status",
        "original_filename",
        "file_sha256",
        "template_version",
        "sheets",
        "expires_at",
    }
    assert set(preview_request.model_fields) == {"mapping"}
    assert set(task_view.model_fields) == {
        "task_id",
        "status",
        "original_filename",
        "file_sha256",
        "template_version",
        "sheets",
        "preview",
        "errors",
        "warnings",
        "can_execute",
        "created_at",
        "expires_at",
        "started_at",
        "finished_at",
        "result",
        "error_code",
        "error_message",
    }


def test_import_task_routes_have_exact_role_dependencies(
    task_app: FastAPI,
):
    app = task_app
    expected = {
        (
            "/api/v1/master-data/import/tasks",
            "POST",
        ): "require_contributor",
        (
            "/api/v1/master-data/import/tasks/{task_id}/preview",
            "POST",
        ): "require_contributor",
        (
            "/api/v1/master-data/import/tasks/{task_id}",
            "GET",
        ): "require_contributor",
        (
            "/api/v1/master-data/import/tasks/{task_id}/errors.xlsx",
            "GET",
        ): "require_contributor",
    }

    actual: dict[tuple[str, str], set[str]] = {}
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.original_route, APIRoute):
            continue
        dependency_names = {
            dependency.call.__name__
            for dependency in route.dependant.dependencies
            if dependency.call is not None
            and hasattr(dependency.call, "__name__")
        }
        for method in route.methods or set():
            actual[(route.path, method)] = dependency_names

    for key, role_name in expected.items():
        assert key in actual
        assert role_name in actual[key]


def test_upload_returns_mapping_without_internal_path(
    task_app: FastAPI,
    actor_contributor: ActorContext,
):
    content = create_template_bytes()

    with _client(task_app, actor_contributor) as client:
        response = client.post(
            "/api/v1/master-data/import/tasks",
            files={
                "file": (
                    "master-data.xlsx",
                    content,
                    (
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),
                )
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "UPLOADED"
    assert data["sheets"]
    assert "file_path" not in data
    assert "tenant_id" not in data
    assert "created_by_user_id" not in data
    assert "created_by_request_id" not in data
    assert "mapping_json" not in data


def test_preview_never_calls_apply_or_mutates_business_rows(
    monkeypatch: pytest.MonkeyPatch,
    task_service: ImportTaskService,
    session,
    actor_admin: ActorContext,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    fake = FakeImportService(
        ImportValidationResult(
            valid=True,
            sheet_counts={
                sheet["name"]: 0
                for sheet in inspect_workbook(
                    content
                )["sheets"]
            },
            errors=[],
            warnings=[],
            preview={},
        )
    )
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        fake,
        raising=False,
    )

    task = task_service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename="master-data.xlsx",
    )
    before = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    result = task_service.preview(
        session,
        actor=actor_admin,
        task_id=task.id,
        mapping=_mapping(content),
    )

    session.expire_all()
    after = session.scalar(
        select(func.count()).select_from(SparePart)
    )

    assert before == after
    assert fake.apply_calls == 0
    assert len(fake.validate_calls) == 1
    assert (
        fake.validate_calls[0]["tenant_id"]
        == actor_admin.tenant_id
    )
    assert result.status is ImportTaskStatus.PREVIEW_VALID
    assert result.errors_json == []
    assert result.warnings_json == []


def test_owner_can_read_task_but_other_tenant_gets_404(
    task_app: FastAPI,
    task_service: ImportTaskService,
    session,
    actor_admin: ActorContext,
    actor_context,
):
    content = create_template_bytes()
    task = task_service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename="master-data.xlsx",
    )

    with _client(task_app, actor_admin) as client:
        owner_response = client.get(
            (
                "/api/v1/master-data/import/tasks/"
                f"{task.id}"
            )
        )

    other_actor = actor_context(
        tenant_id="tenant-b",
        user_id=actor_admin.user_id,
    )
    with _client(task_app, other_actor) as client:
        other_response = client.get(
            (
                "/api/v1/master-data/import/tasks/"
                f"{task.id}"
            )
        )

    assert owner_response.status_code == 200
    assert (
        owner_response.json()["data"]["task_id"]
        == task.id
    )
    assert other_response.status_code == 404


def test_invalid_preview_exposes_error_workbook(
    monkeypatch: pytest.MonkeyPatch,
    task_app: FastAPI,
    task_service: ImportTaskService,
    session,
    actor_admin: ActorContext,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    fake = FakeImportService(
        ImportValidationResult(
            valid=False,
            sheet_counts={"04_维修器材": 1},
            errors=[
                ImportIssue(
                    sheet="04_维修器材",
                    row=2,
                    field="code",
                    code="REQUIRED",
                    message="器材编码不能为空",
                )
            ],
            warnings=[],
            preview={"04_维修器材": []},
        )
    )
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        fake,
        raising=False,
    )

    task = task_service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename="invalid.xlsx",
    )

    with _client(task_app, actor_admin) as client:
        preview = client.post(
            (
                "/api/v1/master-data/import/tasks/"
                f"{task.id}/preview"
            ),
            json={"mapping": _mapping(content)},
        )
        workbook = client.get(
            (
                "/api/v1/master-data/import/tasks/"
                f"{task.id}/errors.xlsx"
            )
        )

    assert preview.status_code == 200
    assert (
        preview.json()["data"]["status"]
        == "PREVIEW_INVALID"
    )
    assert workbook.status_code == 200
    assert workbook.headers[
        "content-type"
    ].startswith(
        (
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )
    assert workbook.content


def test_import_service_accepts_inspection_mapping_for_task_preview(
    session,
    actor_admin: ActorContext,
):
    from app.services.import_service import (
        master_data_import_service,
    )

    content = create_template_bytes()
    result = master_data_import_service.validate(
        session,
        tenant_id=actor_admin.tenant_id,
        content=content,
        filename="master-data.xlsx",
        mapping=_mapping(content),
    )

    assert result.valid is True
    assert result.errors == []


class FakeImportTaskExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, str]] = []

    def submit(
        self,
        task_id: str,
        tenant_id: str,
    ) -> bool:
        self.submissions.append((task_id, tenant_id))
        return True


def test_execute_task_route_requires_admin(
    task_app: FastAPI,
):
    execute_key = (
        (
            "/api/v1/master-data/import/tasks/"
            "{task_id}/execute"
        ),
        "POST",
    )
    actual: dict[tuple[str, str], set[str]] = {}

    for route in iter_route_contexts(
        task_app.routes
    ):
        if not isinstance(
            route.original_route,
            APIRoute,
        ):
            continue

        dependency_names = {
            dependency.call.__name__
            for dependency
            in route.dependant.dependencies
            if dependency.call is not None
            and hasattr(
                dependency.call,
                "__name__",
            )
        }
        for method in route.methods or set():
            actual[
                (
                    route.path,
                    method,
                )
            ] = dependency_names

    assert execute_key in actual
    assert (
        "require_admin"
        in actual[execute_key]
    )


def test_duplicate_execute_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    task_app: FastAPI,
    task_service: ImportTaskService,
    session,
    actor_admin: ActorContext,
):
    import app.api.v1.master_data.imports as imports_api
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    fake_import_service = FakeImportService(
        ImportValidationResult(
            valid=True,
            sheet_counts={
                sheet["name"]: 0
                for sheet in inspect_workbook(
                    content
                )["sheets"]
            },
            errors=[],
            warnings=[],
            preview={},
        )
    )
    fake_executor = FakeImportTaskExecutor()

    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        fake_import_service,
        raising=False,
    )
    monkeypatch.setattr(
        imports_api,
        "import_task_executor",
        fake_executor,
        raising=False,
    )

    task = task_service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename="master-data.xlsx",
    )
    previewed = task_service.preview(
        session,
        actor=actor_admin,
        task_id=task.id,
        mapping=_mapping(content),
    )
    assert (
        previewed.status
        is ImportTaskStatus.PREVIEW_VALID
    )

    path = (
        "/api/v1/master-data/import/tasks/"
        f"{task.id}/execute"
    )
    with _client(task_app, actor_admin) as client:
        first = client.post(path, json={})
        second = client.post(path, json={})

    assert first.status_code == 202
    assert second.status_code in {200, 202}
    assert (
        first.json()["data"]["status"]
        == ImportTaskStatus.QUEUED.value
    )
    assert (
        second.json()["data"]["status"]
        == ImportTaskStatus.QUEUED.value
    )
    assert (
        first.json()["data"]["task_id"]
        == second.json()["data"]["task_id"]
        == task.id
    )
    assert fake_executor.submissions == [
        (task.id, actor_admin.tenant_id),
        (task.id, actor_admin.tenant_id),
    ]

    session.rollback()
    refreshed = session.get(
        type(task),
        task.id,
        populate_existing=True,
    )
    assert refreshed is not None
    assert refreshed.status is ImportTaskStatus.QUEUED


def test_contributor_cannot_queue_import_execution(
    monkeypatch: pytest.MonkeyPatch,
    task_app: FastAPI,
    task_service: ImportTaskService,
    session,
    actor_contributor: ActorContext,
):
    import app.api.v1.master_data.imports as imports_api
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    fake_import_service = FakeImportService(
        ImportValidationResult(
            valid=True,
            sheet_counts={
                sheet["name"]: 0
                for sheet in inspect_workbook(content)["sheets"]
            },
            errors=[],
            warnings=[],
            preview={},
        )
    )
    fake_executor = FakeImportTaskExecutor()
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        fake_import_service,
        raising=False,
    )
    monkeypatch.setattr(
        imports_api,
        "import_task_executor",
        fake_executor,
        raising=False,
    )
    task = task_service.upload(
        session,
        actor=actor_contributor,
        content=content,
        filename="master-data.xlsx",
    )
    previewed = task_service.preview(
        session,
        actor=actor_contributor,
        task_id=task.id,
        mapping=_mapping(content),
    )
    assert previewed.status is ImportTaskStatus.PREVIEW_VALID

    with _client(task_app, actor_contributor) as client:
        response = client.post(
            "/api/v1/master-data/import/tasks/"
            f"{task.id}/execute",
            json={},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    assert fake_executor.submissions == []
    session.expire_all()
    assert session.get(type(task), task.id).status is ImportTaskStatus.PREVIEW_VALID
    for model in (
        InventoryPolicy,
        InventoryBalance,
        InventoryTransaction,
        InventoryLedgerEntry,
    ):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def _valid_preview_service(content: bytes) -> FakeImportService:
    return FakeImportService(
        ImportValidationResult(
            valid=True,
            sheet_counts={
                sheet["name"]: 0
                for sheet in inspect_workbook(content)["sheets"]
            },
            errors=[],
            warnings=[],
            preview={},
        )
    )


def test_same_tenant_admin_can_take_over_contributor_preview(
    monkeypatch,
    task_service,
    session,
    actor_contributor,
    actor_context,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        _valid_preview_service(content),
    )
    task = task_service.upload(
        session,
        actor=actor_contributor,
        content=content,
        filename="handoff.xlsx",
    )
    task_service.preview(
        session,
        actor=actor_contributor,
        task_id=task.id,
        mapping=_mapping(content),
    )
    admin = actor_context(
        tenant_id=actor_contributor.tenant_id,
        user_id="different-admin",
        role=MaintenanceRole.ADMIN,
        request_id="execute-request",
        token_id="execute-token",
    )

    queued, should_submit = task_service.queue_for_execution(
        session,
        actor=admin,
        task_id=task.id,
        max_pending_tasks=10,
    )

    assert should_submit is True
    assert queued.status is ImportTaskStatus.QUEUED
    assert queued.created_by_user_id == actor_contributor.user_id
    assert queued.execution_user_id == admin.user_id
    assert queued.execution_roles_json == [MaintenanceRole.ADMIN.value]
    assert queued.execution_request_id == admin.request_id
    assert queued.execution_token_id == admin.token_id
    assert queued.queued_at is not None


def test_admin_takeover_does_not_cross_tenant(
    monkeypatch,
    task_service,
    session,
    actor_contributor,
    actor_context,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        _valid_preview_service(content),
    )
    task = task_service.upload(
        session,
        actor=actor_contributor,
        content=content,
        filename="tenant-boundary.xlsx",
    )
    task_service.preview(
        session,
        actor=actor_contributor,
        task_id=task.id,
        mapping=_mapping(content),
    )
    foreign_admin = actor_context(
        tenant_id="tenant-b",
        user_id="foreign-admin",
        role=MaintenanceRole.ADMIN,
    )

    with pytest.raises(Exception) as raised:
        task_service.queue_for_execution(
            session,
            actor=foreign_admin,
            task_id=task.id,
            max_pending_tasks=10,
        )
    assert getattr(raised.value, "code", None) == "RESOURCE_NOT_FOUND"


def test_contributor_preview_response_cannot_claim_execute_capability(
    monkeypatch,
    task_app,
    task_service,
    session,
    actor_contributor,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        _valid_preview_service(content),
    )
    task = task_service.upload(
        session,
        actor=actor_contributor,
        content=content,
        filename="capability.xlsx",
    )

    with _client(task_app, actor_contributor) as client:
        response = client.post(
            f"/api/v1/master-data/import/tasks/{task.id}/preview",
            json={"mapping": _mapping(content)},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PREVIEW_VALID"
    assert response.json()["data"]["can_execute"] is False


def test_duplicate_queued_task_requests_resubmission_after_submit_failure(
    monkeypatch,
    task_service,
    session,
    actor_admin,
):
    import app.services.import_task_service as service_module

    content = create_template_bytes()
    monkeypatch.setattr(
        service_module,
        "master_data_import_service",
        _valid_preview_service(content),
    )
    task = task_service.upload(
        session,
        actor=actor_admin,
        content=content,
        filename="resubmit.xlsx",
    )
    task_service.preview(
        session,
        actor=actor_admin,
        task_id=task.id,
        mapping=_mapping(content),
    )
    first, first_should_submit = task_service.queue_for_execution(
        session,
        actor=actor_admin,
        task_id=task.id,
        max_pending_tasks=10,
    )
    second, second_should_submit = task_service.queue_for_execution(
        session,
        actor=actor_admin,
        task_id=task.id,
        max_pending_tasks=10,
    )

    assert first.status is second.status is ImportTaskStatus.QUEUED
    assert first_should_submit is True
    assert second_should_submit is True
