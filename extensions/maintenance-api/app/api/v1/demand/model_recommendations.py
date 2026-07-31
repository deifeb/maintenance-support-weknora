from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.schemas.model_recommendation import (
    ModelRecommendationRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import require_contributor
from app.services.model_recommendation_service import (
    model_recommendation_service,
)

router = APIRouter(
    prefix="/model-recommendations",
    tags=["demand: model recommendations"],
)
SessionDep = Annotated[Session, Depends(get_db_session)]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]


@router.post("")
def recommend_models(
    payload: ModelRecommendationRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    result = model_recommendation_service.recommend(
        session,
        actor,
        payload.scenario_version_id,
    )
    return success_response(
        result,
        actor=actor,
    )
