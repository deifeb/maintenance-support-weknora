from __future__ import annotations

import hashlib
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import CalculationGroup, DemandScenarioVersion
from app.models.enums import (
    CalculationGroupStatus,
    ScenarioVersionStatus,
)
from app.repositories.calculation_group_repository import (
    CalculationGroupChildRepository,
    CalculationGroupRepository,
)
from app.schemas.common import PageData
from app.schemas.model_recommendation import (
    CandidateRecommendation,
)
from app.security.actor import ActorContext
from app.services.demand_calculation_service import (
    CandidateExecutionSpec,
    DemandCalculationService,
    calculation_service,
)
from app.services.model_recommendation_service import (
    ModelRecommendationService,
    model_recommendation_service,
)
from app.services.snapshot_service import snapshot_service


class CalculationGroupService:
    def __init__(self) -> None:
        self.group_repository = CalculationGroupRepository()
        self.child_repository = (
            CalculationGroupChildRepository()
        )
        self.calculation_service: DemandCalculationService = (
            calculation_service
        )
        self.recommendation_service: (
            ModelRecommendationService
        ) = model_recommendation_service

    def _locked_version(
        self,
        session: Session,
        actor: ActorContext,
        scenario_version_id: int,
    ) -> DemandScenarioVersion:
        version = session.scalar(
            select(DemandScenarioVersion)
            .where(
                DemandScenarioVersion.tenant_id
                == actor.tenant_id,
                DemandScenarioVersion.id
                == scenario_version_id,
            )
            .with_for_update()
        )
        if version is None:
            raise NotFoundError(
                "demand_scenario_version",
                scenario_version_id,
            )
        if version.status is not ScenarioVersionStatus.PUBLISHED:
            raise ConflictError(
                "scenario version must be published",
                code="SCENARIO_NOT_PUBLISHED",
            )
        return version

    @staticmethod
    def _request_hash(
        *,
        scenario_version_id: int,
        primary_candidate_key: str,
        selected_candidate_keys: list[str],
        random_seed: int,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "scenario_version_id": scenario_version_id,
                "primary_candidate_key": (
                    primary_candidate_key
                ),
                "selected_candidate_keys": sorted(
                    selected_candidate_keys
                ),
                "random_seed": random_seed,
            }
        )

    @staticmethod
    def _calculation_idempotency_key(
        group_idempotency_key: str,
        candidate_key: str,
        attempt_number: int,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{group_idempotency_key}:"
                f"{candidate_key}:"
                f"{attempt_number}"
            ).encode("utf-8")
        ).hexdigest()
        return f"group:{digest}"

    @staticmethod
    def _candidate_map(
        items: list[CandidateRecommendation],
    ) -> dict[str, CandidateRecommendation]:
        return {
            item.candidate_key: item
            for item in items
        }

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        scenario_version_id: int,
        primary_candidate_key: str,
        selected_candidate_keys: list[str],
        idempotency_key: str,
        random_seed: int = 20260723,
    ) -> CalculationGroup:
        selected = list(dict.fromkeys(selected_candidate_keys))
        if (
            not selected
            or len(selected) != len(selected_candidate_keys)
        ):
            raise BusinessValidationError(
                "selected candidates must be non-empty and unique",
                code="INVALID_CANDIDATE_SELECTION",
            )
        if primary_candidate_key not in selected:
            raise BusinessValidationError(
                "primary candidate must be selected",
                code="PRIMARY_CANDIDATE_NOT_SELECTED",
            )
        request_hash = self._request_hash(
            scenario_version_id=scenario_version_id,
            primary_candidate_key=primary_candidate_key,
            selected_candidate_keys=selected,
            random_seed=random_seed,
        )
        existing = (
            self.group_repository.get_by_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ConflictError(
                    "idempotency key was reused",
                    code="IDEMPOTENCY_KEY_REUSED",
                )
            loaded = self.group_repository.get(
                session,
                actor.tenant_id,
                existing.id,
            )
            assert loaded is not None
            return loaded

        try:
            self._locked_version(
                session,
                actor,
                scenario_version_id,
            )
            recommendation = (
                self.recommendation_service.recommend(
                    session,
                    actor,
                    scenario_version_id,
                )
            )
            candidates = self._candidate_map(
                recommendation.items
            )
            invalid = [
                key
                for key in selected
                if (
                    key not in candidates
                    or not candidates[key].applicable
                )
            ]
            if invalid:
                raise BusinessValidationError(
                    "selected candidate is not applicable",
                    code="CANDIDATE_NOT_APPLICABLE",
                    details={"candidate_keys": invalid},
                )

            group = self.group_repository.create(
                session,
                actor.tenant_id,
                {
                    "scenario_version_id": (
                        scenario_version_id
                    ),
                    "status": CalculationGroupStatus.PENDING,
                    "primary_candidate_key": (
                        primary_candidate_key
                    ),
                    "recommendation_snapshot_json": (
                        recommendation.model_dump(mode="json")
                    ),
                    "parameter_snapshot_json": {
                        "random_seed": random_seed,
                        "selected_candidate_keys": selected,
                    },
                    "idempotency_key": idempotency_key,
                    "request_hash": request_hash,
                    "created_by_user_id": actor.user_id,
                    "created_by_request_id": actor.request_id,
                },
            )
            self.group_repository.append_event(
                session,
                actor.tenant_id,
                group.id,
                event_type="group.created",
                payload={
                    "status": CalculationGroupStatus.PENDING.value,
                    "primary_candidate_key": (
                        primary_candidate_key
                    ),
                },
            )
            for key in selected:
                candidate = candidates[key]
                calculation = (
                    self.calculation_service.submit_candidate(
                        session,
                        actor,
                        scenario_version_id=(
                            scenario_version_id
                        ),
                        spec=CandidateExecutionSpec(
                            candidate_key=key,
                            reliability_model=(
                                candidate.reliability_model
                            ),
                            execution_mode=(
                                candidate.execution_mode
                            ),
                            random_seed=random_seed,
                        ),
                        idempotency_key=(
                            self._calculation_idempotency_key(
                                idempotency_key,
                                key,
                                1,
                            )
                        ),
                    )
                )
                child = self.child_repository.create_attempt(
                    session,
                    actor.tenant_id,
                    group.id,
                    {
                        "candidate_key": key,
                        "reliability_model": (
                            candidate.reliability_model
                        ),
                        "execution_mode": (
                            candidate.execution_mode
                        ),
                        "calculation_id": calculation.id,
                        "is_primary": (
                            key == primary_candidate_key
                        ),
                        "selection_reason": ";".join(
                            candidate.reasons
                        ),
                    },
                )
                self.group_repository.append_event(
                    session,
                    actor.tenant_id,
                    group.id,
                    child_id=child.id,
                    event_type="child.queued",
                    payload={
                        "candidate_key": key,
                        "calculation_id": calculation.id,
                        "attempt_number": 1,
                    },
                )
            session.commit()
        except Exception:
            session.rollback()
            raise

        loaded = self.group_repository.get(
            session,
            actor.tenant_id,
            group.id,
        )
        assert loaded is not None
        return loaded

    def get(
        self,
        session: Session,
        actor: ActorContext,
        group_id: int,
    ) -> CalculationGroup:
        group = self.group_repository.get(
            session,
            actor.tenant_id,
            group_id,
        )
        if group is None:
            raise NotFoundError(
                "calculation_group",
                group_id,
            )
        return group

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        status: CalculationGroupStatus | None = None,
    ) -> PageData[dict[str, object]]:
        rows, total = self.group_repository.list_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status.value if status else None,
        )
        return PageData[dict[str, object]](
            items=[
                {
                    "id": row.id,
                    "scenario_version_id": (
                        row.scenario_version_id
                    ),
                    "status": row.status.value,
                    "primary_candidate_key": (
                        row.primary_candidate_key
                    ),
                    "last_event_sequence": (
                        row.last_event_sequence
                    ),
                    "version": row.version,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )


calculation_group_service = CalculationGroupService()
