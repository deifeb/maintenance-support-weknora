from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.exporters.master_data_excel import MasterDataExcelExporter
from app.security.actor import ActorContext
from app.security.permissions import require_viewer

EXCEL_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)

router = APIRouter(
    prefix="/exports",
    tags=["master-data: exports"],
)
SessionDep = Annotated[
    Session,
    Depends(get_db_session),
]


@router.get("/{resource_key}")
def export_master_data(
    resource_key: str,
    session: SessionDep,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    keyword: Annotated[
        str | None,
        Query(max_length=200),
    ] = None,
    include_inactive: bool = False,
    is_critical: bool | None = None,
    is_repairable: bool | None = None,
    spare_part_id: Annotated[
        int | None,
        Query(ge=1),
    ] = None,
    warehouse_id: Annotated[
        int | None,
        Query(ge=1),
    ] = None,
    supplier_id: Annotated[
        int | None,
        Query(ge=1),
    ] = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> Response:
    filters = {
        "keyword": keyword,
        "include_inactive": include_inactive,
        "is_critical": is_critical,
        "is_repairable": is_repairable,
        "spare_part_id": spare_part_id,
        "warehouse_id": warehouse_id,
        "supplier_id": supplier_id,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    content = MasterDataExcelExporter(
        max_rows=(
            get_settings().master_data_export_max_rows
        )
    ).export(
        session,
        tenant_id=actor.tenant_id,
        resource_key=resource_key,
        filters=filters,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    filename = (
        f"master-data-{resource_key}-"
        f"{timestamp}.xlsx"
    )
    encoded_filename = quote(
        filename,
        safe="",
    )

    return Response(
        content=content,
        media_type=EXCEL_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''"
                f"{encoded_filename}"
            ),
            "Cache-Control": "no-store",
        },
    )
