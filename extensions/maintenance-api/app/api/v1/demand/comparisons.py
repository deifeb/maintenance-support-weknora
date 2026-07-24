from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.services.demand_calculation_service import calculation_service

router = APIRouter(prefix="/comparisons", tags=["demand: comparisons"])
SessionDep = Annotated[Session, Depends(get_db_session)]


class HistoricalComparisonRequest(BaseModel):
    left_calculation_id: int = Field(gt=0)
    right_calculation_id: int = Field(gt=0)


@router.post("")
def compare(payload: HistoricalComparisonRequest, session: SessionDep):
    left = calculation_service.get(session, payload.left_calculation_id)
    right = calculation_service.get(session, payload.right_calculation_id)
    left_summary = left.result_summary_json or {}
    right_summary = right.result_summary_json or {}
    return success_response(
        {
            "left": {
                "id": left.id,
                "code": left.calculation_code,
                "snapshot_hash": left.input_snapshot_hash,
                "summary": left_summary,
            },
            "right": {
                "id": right.id,
                "code": right.calculation_code,
                "snapshot_hash": right.input_snapshot_hash,
                "summary": right_summary,
            },
            "same_snapshot": left.input_snapshot_hash == right.input_snapshot_hash,
        }
    )
