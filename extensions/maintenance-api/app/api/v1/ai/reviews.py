from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models import AIReviewFinding
from app.models.enums import (
    AIReviewFindingStatus,
)
from app.schemas.ai_review import (
    AIDemandReviewRequest,
    AIReviewFindingActionRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_contributor,
    require_viewer,
)
from app.services.ai_review_engine import (
    ReviewContext,
)
from app.services.ai_review_service import (
    ai_review_service,
)

router = APIRouter()


def _finding_data(
    row: AIReviewFinding,
) -> dict:
    return {
        "id": row.id,
        "rule_code": row.rule_code,
        "category": row.category,
        "title": row.finding_title,
        "message": (
            row.deterministic_message
        ),
        "severity": row.severity.value,
        "blocking_level": (
            row.blocking_level.value
        ),
        "status": row.status.value,
        "spare_part_id": (
            row.affected_spare_part_id
        ),
        "suggested_actions": (
            row.suggested_actions_json or []
        ),
        "explanation": (
            row.llm_explanation_json or {}
        ),
    }


@router.post("/reviews/demand-lists")
async def review_demand_list(
    payload: AIDemandReviewRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    review = (
        await ai_review_service
        .create_demand_list_review(
            session,
            actor,
            calculation_run_id=(
                payload.calculation_run_id
            ),
            session_id=payload.session_id,
            context=ReviewContext(
                scenario_snapshot=(
                    payload.scenario_snapshot
                ),
                calculation_items=(
                    payload.items
                ),
                evidence_items=(
                    payload.evidence_items
                ),
            ),
        )
    )
    return success_response(
        {
            "review_id": review.id,
            "status": (
                review.run.status.value
            ),
            "summary": (
                review.run.summary_json
            ),
            "findings": [
                _finding_data(row)
                for row in review.findings
            ],
        },
        actor=actor,
    )


@router.post("/reviews/scenarios")
def review_scenario(
    payload: dict,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
):
    missing = [
        key
        for key in (
            "equipment_model",
            "configuration_version",
            "stages",
        )
        if not payload.get(key)
    ]
    return success_response(
        {
            "blocking": bool(missing),
            "missing_fields": missing,
        },
        actor=actor,
    )


@router.get("/reviews/{review_id}")
def get_review(
    review_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    row = ai_review_service.get_review(
        session,
        actor,
        review_id,
    )
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
            "summary": row.summary_json or {},
        },
        actor=actor,
    )


@router.get(
    "/reviews/{review_id}/findings"
)
def get_findings(
    review_id: int,
    actor: Annotated[
        ActorContext,
        Depends(require_viewer),
    ],
    session: Session = Depends(get_db_session),
):
    findings = ai_review_service.list_findings(
        session,
        actor,
        review_id,
    )
    return success_response(
        [
            _finding_data(finding)
            for finding in findings
        ],
        actor=actor,
    )


@router.post(
    "/reviews/findings/{finding_id}/acknowledge"
)
def acknowledge_finding(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    row = (
        ai_review_service
        .transition_finding(
            session,
            actor,
            finding_id,
            status=(
                AIReviewFindingStatus
                .ACKNOWLEDGED
            ),
            comment=payload.comment,
        )
    )
    return success_response(
        _finding_data(row),
        actor=actor,
    )


@router.post(
    "/reviews/findings/{finding_id}/resolve"
)
def resolve_finding(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    row = (
        ai_review_service
        .transition_finding(
            session,
            actor,
            finding_id,
            status=(
                AIReviewFindingStatus.RESOLVED
            ),
            comment=payload.comment,
        )
    )
    return success_response(
        _finding_data(row),
        actor=actor,
    )


@router.post(
    "/reviews/findings/{finding_id}/accept-risk"
)
def accept_risk(
    finding_id: int,
    payload: AIReviewFindingActionRequest,
    actor: Annotated[
        ActorContext,
        Depends(require_contributor),
    ],
    session: Session = Depends(get_db_session),
):
    row = (
        ai_review_service
        .transition_finding(
            session,
            actor,
            finding_id,
            status=(
                AIReviewFindingStatus
                .ACCEPTED_RISK
            ),
            comment=payload.comment,
        )
    )
    return success_response(
        _finding_data(row),
        actor=actor,
    )
