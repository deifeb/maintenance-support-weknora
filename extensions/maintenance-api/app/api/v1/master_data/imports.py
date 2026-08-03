from io import BytesIO
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.responses import success_response
from app.db.session import get_db_session
from app.importers.inspection import inspect_workbook
from app.models.import_task import (
    ImportTaskStatus,
    MasterDataImportTask,
)
from app.schemas.common import MaintenanceSuccessResponse
from app.schemas.import_data import (
    ImportExecutionResult,
    ImportPreviewRequest,
    ImportSheetInspection,
    ImportSheetSummary,
    ImportTaskUploadResult,
    ImportTaskView,
    ImportValidationResult,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.import_service import (
    master_data_import_service,
)
from app.services.import_task_service import (
    build_import_task_service,
)
from app.workers.import_executor import (
    import_task_executor,
)

router = APIRouter(
    prefix="/import",
    tags=["master-data: import"],
)
SessionDep = Annotated[
    Session,
    Depends(get_db_session),
]

_settings = get_settings()
import_task_service = build_import_task_service(
    root=_settings.master_data_import_dir,
    task_ttl_seconds=(
        _settings.master_data_import_task_ttl_seconds
    ),
    max_size_mb=_settings.max_import_size_mb,
)


def _status_value(
    task: MasterDataImportTask,
) -> str:
    status_value = task.status
    if isinstance(status_value, ImportTaskStatus):
        return status_value.value
    return str(status_value)


def _task_summaries(
    task: MasterDataImportTask,
) -> list[ImportSheetSummary]:
    raw = task.sheet_summary_json or {}
    summaries: list[ImportSheetSummary] = []

    for name, value in raw.items():
        if isinstance(value, dict):
            total_rows = int(
                value.get("total_rows", 0)
            )
            valid_rows = int(
                value.get("valid_rows", 0)
            )
            invalid_rows = int(
                value.get("invalid_rows", 0)
            )
        else:
            total_rows = int(value)
            valid_rows = total_rows
            invalid_rows = 0

        summaries.append(
            ImportSheetSummary(
                name=name,
                total_rows=total_rows,
                valid_rows=valid_rows,
                invalid_rows=invalid_rows,
            )
        )

    return summaries


def _task_view(
    task: MasterDataImportTask,
) -> ImportTaskView:
    return ImportTaskView(
        task_id=task.id,
        status=_status_value(task),
        original_filename=task.original_filename,
        file_sha256=task.file_sha256,
        template_version=task.template_version,
        sheets=_task_summaries(task),
        preview=task.preview_json or {},
        errors=task.errors_json or [],
        warnings=task.warnings_json or [],
        can_execute=(
            task.status
            is ImportTaskStatus.PREVIEW_VALID
        ),
        created_at=task.created_at,
        expires_at=task.expires_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        result=task.result_json,
        error_code=task.error_code,
        error_message=task.error_message,
    )


def _upload_result(
    *,
    task: MasterDataImportTask,
    content: bytes,
) -> ImportTaskUploadResult:
    inspection = inspect_workbook(content)
    sheets = [
        ImportSheetInspection(
            name=sheet["name"],
            source_headers=sheet["source_headers"],
            suggested_mapping=(
                sheet["suggested_mapping"]
            ),
            required_fields=sheet["required_fields"],
        )
        for sheet in inspection["sheets"]
    ]
    return ImportTaskUploadResult(
        task_id=task.id,
        status=_status_value(task),
        original_filename=task.original_filename,
        file_sha256=task.file_sha256,
        template_version=task.template_version,
        sheets=sheets,
        expires_at=task.expires_at,
    )


@router.get("/template")
def download_template(
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
) -> StreamingResponse:
    content = master_data_import_service.template_bytes()
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                "attachment; filename="
                '"maintenance_master_data_template.xlsx"'
            )
        },
    )


@router.post(
    "/validate",
    response_model=MaintenanceSuccessResponse[
        ImportValidationResult
    ],
)
async def validate_import(
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    file: UploadFile = File(...),
):
    content = await file.read()
    result = master_data_import_service.validate(
        session,
        tenant_id=actor.tenant_id,
        content=content,
        filename=file.filename or "upload.xlsx",
    )
    return success_response(
        result,
        "Workbook validation completed",
        actor=actor,
    )


@router.post(
    "/execute",
    response_model=MaintenanceSuccessResponse[
        ImportExecutionResult
    ],
)
async def execute_import(
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    file: UploadFile = File(...),
):
    content = await file.read()
    try:
        result = master_data_import_service.apply(
            session,
            tenant_id=actor.tenant_id,
            content=content,
            filename=file.filename or "upload.xlsx",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return success_response(
        result,
        "Workbook imported",
        actor=actor,
    )


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=MaintenanceSuccessResponse[
        ImportTaskUploadResult
    ],
)
async def upload_import_task(
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    file: UploadFile = File(...),
):
    content = await file.read()
    task = import_task_service.upload(
        session,
        actor=actor,
        content=content,
        filename=file.filename or "upload.xlsx",
    )
    return success_response(
        _upload_result(
            task=task,
            content=content,
        ),
        "Import task uploaded",
        actor=actor,
        version=task.version,
    )


@router.post(
    "/tasks/{task_id}/preview",
    response_model=MaintenanceSuccessResponse[
        ImportTaskView
    ],
)
def preview_import_task(
    task_id: str,
    request: ImportPreviewRequest,
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
):
    task = import_task_service.preview(
        session,
        actor=actor,
        task_id=task_id,
        mapping=request.mapping,
    )
    return success_response(
        _task_view(task),
        "Import task preview completed",
        actor=actor,
        version=task.version,
    )


@router.post(
    "/tasks/{task_id}/execute",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MaintenanceSuccessResponse[
        ImportTaskView
    ],
)
def execute_import_task(
    task_id: str,
    response: Response,
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
):
    task, should_submit = (
        import_task_service.queue_for_execution(
            session,
            actor=actor,
            task_id=task_id,
            max_pending_tasks=(
                _settings.master_data_import_max_pending_tasks
            ),
        )
    )

    if should_submit:
        import_task_executor.submit(
            task.id,
            actor.tenant_id,
            actor.user_id,
        )
        response.status_code = (
            status.HTTP_202_ACCEPTED
        )
        message = "Import task queued"
    else:
        response.status_code = status.HTTP_200_OK
        message = "Import task already queued"

    return success_response(
        _task_view(task),
        message,
        actor=actor,
        version=task.version,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=MaintenanceSuccessResponse[
        ImportTaskView
    ],
)
def read_import_task(
    task_id: str,
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
):
    task = import_task_service.get_for_actor(
        session,
        task_id=task_id,
        actor=actor,
    )
    if task is None:
        raise NotFoundError(
            "master_data_import_task",
            task_id,
        )
    return success_response(
        _task_view(task),
        "Import task loaded",
        actor=actor,
        version=task.version,
    )


@router.get(
    "/tasks/{task_id}/errors.xlsx",
)
def download_import_errors(
    task_id: str,
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
) -> StreamingResponse:
    content = (
        import_task_service.read_error_workbook_for_actor(
            session,
            task_id=task_id,
            actor=actor,
        )
    )
    filename = (
        f"master-data-import-{task_id}-errors.xlsx"
    )
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )
