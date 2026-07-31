from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import AISession, AISessionSnapshot
from app.repositories.ai_session_repository import (
    AISessionRepository,
    ai_session_repository,
)
from app.schemas.scenario_draft import (
    ScenarioDraftEnvelope,
    ScenarioDraftEvaluation,
    ScenarioDraftOrigin,
    ScenarioDraftPayload,
    ScenarioFieldState,
)
from app.security.actor import ActorContext

_STEP_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "basics": (
        "scenario_name",
        "mission_code",
        "start_at",
        "end_at",
        "priority",
    ),
    "configuration": (
        "equipment_model_id",
        "configuration_version_id",
        "fleet_groups",
    ),
    "mission": ("stages",),
    "reliabilityRepair": ("reliability_profiles",),
    "calculation": (
        "service_level",
        "execution_preference",
        "missing_parameter_policy",
    ),
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _required_value(
    draft: ScenarioDraftPayload,
    field_name: str,
) -> Any:
    if field_name == "scenario_name":
        return draft.scenario_name
    field = draft.fields.get(field_name)
    return field.value if field is not None else None


def evaluate_scenario_draft(
    draft: ScenarioDraftPayload,
) -> ScenarioDraftEvaluation:
    blocking: set[str] = set()
    completion: dict[str, bool] = {}

    for step, required_fields in _STEP_REQUIREMENTS.items():
        missing = [
            field_name
            for field_name in required_fields
            if not _has_value(
                _required_value(draft, field_name)
            )
        ]
        blocking.update(missing)
        completion[step] = not missing

    for field_name, field in draft.fields.items():
        if field.risk == "BLOCKING" and not field.confirmed:
            blocking.add(field_name)

    ordered_blocking = sorted(blocking)
    completion["confirmation"] = not ordered_blocking
    return ScenarioDraftEvaluation(
        completion=completion,
        blocking_fields=ordered_blocking,
    )


def _initial_fields() -> dict[str, ScenarioFieldState]:
    field_names = {
        field_name
        for required_fields in _STEP_REQUIREMENTS.values()
        for field_name in required_fields
        if field_name != "scenario_name"
    }
    return {
        field_name: ScenarioFieldState(
            source="SYSTEM_DEFAULT",
            risk="BLOCKING",
        )
        for field_name in sorted(field_names)
    }


def _field_sources(
    draft: ScenarioDraftPayload,
) -> dict[str, dict[str, Any]]:
    return {
        field_name: field.model_dump(
            mode="json",
            exclude={"value"},
        )
        for field_name, field in draft.fields.items()
    }


class ScenarioDraftService:
    def __init__(
        self,
        *,
        repository: AISessionRepository | None = None,
    ) -> None:
        self.repository = repository or ai_session_repository

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        title: str,
        sensitivity_level: str,
        origin: ScenarioDraftOrigin = "MANUAL",
        draft: ScenarioDraftPayload | None = None,
    ) -> ScenarioDraftEnvelope:
        payload = draft or ScenarioDraftPayload(
            scenario_name=title,
            current_step=1,
            fields=_initial_fields(),
        )
        evaluation = evaluate_scenario_draft(payload)
        ai_session = self.repository.create_session(
            session,
            actor.tenant_id,
            title=title,
            sensitivity_level=sensitivity_level,
            created_by=actor.user_id,
        )
        ai_session.current_intent = "SCENARIO_DRAFT"
        snapshot = self.repository.create_snapshot(
            session,
            actor.tenant_id,
            ai_session.id,
            current_state=ai_session.status.value,
            scenario_draft=payload.model_dump(mode="json"),
            field_sources=_field_sources(payload),
            execution_context={
                "origin": origin,
                "current_step": payload.current_step,
                "completion": evaluation.completion,
                "blocking_fields": (
                    evaluation.blocking_fields
                ),
            },
        )
        session.commit()
        session.refresh(snapshot)
        return self._envelope(
            snapshot,
            origin=origin,
            evaluation=evaluation,
        )

    def get(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
    ) -> ScenarioDraftEnvelope:
        ai_session = self.repository.get(
            session,
            actor.tenant_id,
            session_id,
        )
        if ai_session is None:
            raise NotFoundError("scenario_draft", session_id)
        snapshot = self.repository.latest_snapshot(
            session,
            actor.tenant_id,
            session_id,
        )
        return self._require_envelope(
            ai_session,
            snapshot,
            session_id,
        )

    def save(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        expected_version: int,
        draft: ScenarioDraftPayload,
    ) -> ScenarioDraftEnvelope:
        ai_session = self.repository.get_for_update(
            session,
            actor.tenant_id,
            session_id,
        )
        if ai_session is None:
            raise NotFoundError("scenario_draft", session_id)
        latest = self.repository.latest_snapshot(
            session,
            actor.tenant_id,
            session_id,
        )
        if (
            latest is None
            or latest.scenario_draft_json is None
        ):
            raise NotFoundError("scenario_draft", session_id)
        if latest.snapshot_version != expected_version:
            conflict = ConflictError(
                "scenario draft version conflict",
                code="SCENARIO_DRAFT_VERSION_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": (
                        latest.snapshot_version
                    ),
                    "conflict_object": "scenario_draft",
                    "suggested_action": (
                        "reload_server_draft"
                    ),
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict

        evaluation = evaluate_scenario_draft(draft)
        origin = self._origin(latest)
        snapshot = self.repository.create_snapshot(
            session,
            actor.tenant_id,
            session_id,
            current_state=ai_session.status.value,
            scenario_draft=draft.model_dump(mode="json"),
            field_sources=_field_sources(draft),
            execution_context={
                "origin": origin,
                "current_step": draft.current_step,
                "completion": evaluation.completion,
                "blocking_fields": (
                    evaluation.blocking_fields
                ),
            },
        )
        session.commit()
        session.refresh(snapshot)
        return self._envelope(
            snapshot,
            origin=origin,
            evaluation=evaluation,
        )

    def validate(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
    ) -> ScenarioDraftEnvelope:
        envelope = self.get(
            session,
            actor,
            session_id,
        )
        evaluation = evaluate_scenario_draft(
            envelope.draft
        )
        return envelope.model_copy(
            update={
                "completion": evaluation.completion,
                "blocking_fields": (
                    evaluation.blocking_fields
                ),
            }
        )

    def _require_envelope(
        self,
        ai_session: AISession,
        snapshot: AISessionSnapshot | None,
        session_id: int,
    ) -> ScenarioDraftEnvelope:
        del ai_session
        if (
            snapshot is None
            or snapshot.scenario_draft_json is None
        ):
            raise NotFoundError("scenario_draft", session_id)
        return self._envelope(snapshot)

    def _envelope(
        self,
        snapshot: AISessionSnapshot,
        *,
        origin: ScenarioDraftOrigin | None = None,
        evaluation: ScenarioDraftEvaluation | None = None,
    ) -> ScenarioDraftEnvelope:
        payload = ScenarioDraftPayload.model_validate(
            snapshot.scenario_draft_json
        )
        current_evaluation = (
            evaluation
            or evaluate_scenario_draft(payload)
        )
        return ScenarioDraftEnvelope(
            session_id=snapshot.session_id,
            snapshot_id=snapshot.id,
            version=snapshot.snapshot_version,
            origin=origin or self._origin(snapshot),
            draft=payload,
            completion=current_evaluation.completion,
            blocking_fields=(
                current_evaluation.blocking_fields
            ),
            updated_at=snapshot.updated_at,
        )

    @staticmethod
    def _origin(
        snapshot: AISessionSnapshot,
    ) -> ScenarioDraftOrigin:
        value = (
            snapshot.execution_context_json or {}
        ).get("origin")
        return "MANUAL" if value == "MANUAL" else "AI"


scenario_draft_service = ScenarioDraftService()
