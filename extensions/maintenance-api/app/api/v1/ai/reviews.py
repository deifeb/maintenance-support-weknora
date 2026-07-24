from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError, NotFoundError
from app.core.responses import success_response
from app.db.session import get_db_session
from app.models import AIReviewFinding, AIReviewRun
from app.models.enums import AIReviewFindingStatus, AISeverity
from app.schemas.ai_review import AIDemandReviewRequest, AIReviewFindingActionRequest
from app.services.ai_review_engine import ReviewContext
from app.services.ai_review_service import ai_review_service

router = APIRouter()


def _finding_data(row: AIReviewFinding) -> dict:
    return {
        "id": row.id,
        "rule_code": row.rule_code,
        "category": row.category,
        "title": row.finding_title,
        "message": row.deterministic_message,
        "severity": row.severity.value,
        "blocking_level": row.blocking_level.value,
        "status": row.status.value,
        "spare_part_id": row.affected_spare_part_id,
        "suggested_actions": row.suggested_actions_json or [],
        "explanation": row.llm_explanation_json or {},
    }


@router.post("/reviews/demand-lists")
async def review_demand_list(
    payload: AIDemandReviewRequest,
    session: Session = Depends(get_db_session),
):
    review = await ai_review_service.create_demand_list_review(
        session,
        calculation_run_id=payload.calculation_run_id,
        created_by="api-user",
        session_id=payload.session_id,
        context=ReviewContext(
            scenario_snapshot=payload.scenario_snapshot,
            calculation_items=payload.items,
            evidence_items=payload.evidence_items,
        ),
    )
    return success_response(
        {
            "review_id": review.id,
            "status": review.run.status.value,
            "summary": review.run.summary_json,
            "findings": [_finding_data(row) for row in review.findings],
        }
    )


@router.post("/reviews/scenarios")
def review_scenario(payload: dict):
    missing = [
        key
        for key in ("equipment_model", "configuration_version", "stages")
        if not payload.get(key)
    ]
    return success_response({"blocking": bool(missing), "missing_fields": missing})


@router.get("/reviews/{review_id}")
def get_review(review_id: int, session: Session = Depends(get_db_session)):
    row = session.get(AIReviewRun, review_id)
    if row is None:
        raise NotFoundError("ai_review", review_id)
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
            "summary": row.summary_json or {},
        }
    )


@router.get("/reviews/{review_id}/findings")
def get_findings(review_id: int, session: Session = Depends(get_db_session)):
    row = session.get(AIReviewRun, review_id)
    if row is None:
        raise NotFoundError("ai_review", review_id)
    findings = ai_review_service.repository.list_findings(session, review_id)
    return success_response([_finding_data(finding) for finding in findings])


def _update_finding(
    session: Session,
    finding_id: int,
    status: AIReviewFindingStatus,
    payload: AIReviewFindingActionRequest,
) -> AIReviewFinding:
    row = session.get(AIReviewFinding, finding_id)
    if row is None:
        raise NotFoundError("ai_review_finding", finding_id)
    if status is AIReviewFindingStatus.ACCEPTED_RISK and row.severity is AISeverity.CRITICAL:
        raise BusinessValidationError(
            "critical finding requires secondary confirmation",
            code="CRITICAL_RISK_CONFIRMATION_REQUIRED",
        )
    row.status = status
    row.resolution_comment = payload.comment
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = "api-user"
    session.commit()
    session.refresh(row)
    return row


@router.post("/reviews/findings/{finding_id}/acknowledge")
def acknowledge_finding(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    session: Session = Depends(get_db_session),
):
    return success_response(
        _finding_data(
            _update_finding(
                session,
                finding_id,
                AIReviewFindingStatus.ACKNOWLEDGED,
                payload,
            )
        )
    )


@router.post("/reviews/findings/{finding_id}/resolve")
def resolve_finding(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    session: Session = Depends(get_db_session),
):
    return success_response(
        _finding_data(
            _update_finding(
                session,
                finding_id,
                AIReviewFindingStatus.RESOLVED,
                payload,
            )
        )
    )


@router.post("/reviews/findings/{finding_id}/accept-risk")
def accept_risk(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    session: Session = Depends(get_db_session),
):
    return success_response(
        _finding_data(
            _update_finding(
                session,
                finding_id,
                AIReviewFindingStatus.ACCEPTED_RISK,
                payload,
            )
        )
    )
