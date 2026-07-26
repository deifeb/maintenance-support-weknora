from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.common import SuccessResponse
from app.schemas.import_data import ImportExecutionResult, ImportValidationResult
from app.security.actor import ActorContext
from app.security.permissions import require_contributor, require_viewer
from app.services.import_service import master_data_import_service

router = APIRouter(prefix="/import", tags=["master-data: import"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get("/template")
def download_template(
    actor: Annotated[ActorContext, Depends(require_viewer)],
) -> StreamingResponse:
    content = master_data_import_service.template_bytes()
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="maintenance_master_data_template.xlsx"'
        },
    )


@router.post("/validate", response_model=SuccessResponse[ImportValidationResult])
async def validate_import(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
    file: UploadFile = File(...),
):
    content = await file.read()
    result = master_data_import_service.validate(
        session,
        content=content,
        filename=file.filename or "upload.xlsx",
    )
    return success_response(result, "Workbook validation completed")


@router.post("/execute", response_model=SuccessResponse[ImportExecutionResult])
async def execute_import(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_contributor)],
    file: UploadFile = File(...),
):
    content = await file.read()
    result = master_data_import_service.execute(
        session,
        content=content,
        filename=file.filename or "upload.xlsx",
    )
    return success_response(result, "Workbook imported")
