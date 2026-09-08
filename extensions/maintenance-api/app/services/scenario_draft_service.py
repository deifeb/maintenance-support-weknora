from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models import (
    AISession,
    AISessionSnapshot,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.repositories.ai_session_repository import (
    AISessionRepository,
    ai_session_repository,
)
from app.schemas.demand_scenario import ScenarioValidationResult
from app.schemas.scenario_draft import (
    ScenarioDraftEnvelope,
    ScenarioDraftEvaluation,
    ScenarioDraftMaterializationPayload,
    ScenarioDraftOrigin,
    ScenarioDraftPayload,
    ScenarioFieldState,
)
from app.security.actor import ActorContext
from app.services.scenario_service import (
    ScenarioService,
    scenario_service,
)

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


@dataclass(slots=True)
class ScenarioDraftMaterialization:
    template: DemandScenarioTemplate
    scenario_version: DemandScenarioVersion
    validation: ScenarioValidationResult
    status: str = "DRAFT"
    replayed: bool = False


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
        scenario_service_instance: ScenarioService | None = None,
    ) -> None:
        self.repository = repository or ai_session_repository
        self.scenario_service = (
            scenario_service_instance or scenario_service
        )

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
            self._raise_version_conflict(
                actor,
                expected_version=expected_version,
                actual_version=latest.snapshot_version,
            )

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

    def materialize(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> ScenarioDraftMaterialization:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise BusinessValidationError(
                "Idempotency-Key must not be blank",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )

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

        request_hash = self._materialization_hash(
            session_id,
            latest.scenario_draft_json,
        )
        receipt_snapshot = (
            self.repository.materialization_snapshot(
                session,
                actor.tenant_id,
                session_id,
                normalized_key,
            )
        )
        if receipt_snapshot is not None:
            return self._replay_materialization(
                session,
                actor,
                receipt_snapshot,
                request_hash=request_hash,
            )

        if latest.snapshot_version != expected_version:
            self._raise_version_conflict(
                actor,
                expected_version=expected_version,
                actual_version=latest.snapshot_version,
            )

        draft = ScenarioDraftPayload.model_validate(
            latest.scenario_draft_json
        )
        evaluation = evaluate_scenario_draft(draft)
        if evaluation.blocking_fields:
            session.rollback()
            raise BusinessValidationError(
                "scenario draft has blocking fields",
                code="SCENARIO_DRAFT_BLOCKED",
                details={
                    "blocking_fields": (
                        evaluation.blocking_fields
                    )
                },
            )

        try:
            materialization_payload = (
                self._materialization_payload(draft)
            )
            materialized = (
                self.scenario_service.materialize_draft(
                    session,
                    actor,
                    materialization_payload,
                )
            )
            ai_session.active_scenario_version_id = (
                materialized.scenario_version.id
            )
            context = dict(
                latest.execution_context_json or {}
            )
            context["materialization"] = {
                "idempotency_key": normalized_key,
                "request_hash": request_hash,
                "scenario_id": materialized.template.id,
                "scenario_version_id": (
                    materialized.scenario_version.id
                ),
                "status": "DRAFT",
                "validation": (
                    materialized.validation.model_dump(
                        mode="json"
                    )
                ),
            }
            receipt = self.repository.create_snapshot(
                session,
                actor.tenant_id,
                session_id,
                current_state=ai_session.status.value,
                scenario_draft=draft.model_dump(mode="json"),
                field_sources=(
                    latest.field_sources_json or {}
                ),
                execution_context=context,
                pending_confirmations=(
                    latest.pending_confirmations_json
                ),
                completed_step_ids=(
                    latest.completed_step_ids_json
                ),
                evidence_package_ids=(
                    latest.evidence_package_ids_json
                ),
            )
            session.commit()
            session.refresh(materialized.template)
            session.refresh(materialized.scenario_version)
            session.refresh(receipt)
            return ScenarioDraftMaterialization(
                template=materialized.template,
                scenario_version=(
                    materialized.scenario_version
                ),
                validation=materialized.validation,
            )
        except (
            BusinessValidationError,
            ConflictError,
        ):
            session.rollback()
            raise
        except (NotFoundError, ValidationError) as exc:
            session.rollback()
            raise BusinessValidationError(
                "scenario draft contains invalid data",
                code="SCENARIO_DRAFT_INVALID",
                details={"reason": str(exc)},
            ) from exc
        except Exception:
            session.rollback()
            raise

    def _replay_materialization(
        self,
        session: Session,
        actor: ActorContext,
        receipt_snapshot: AISessionSnapshot,
        *,
        request_hash: str,
    ) -> ScenarioDraftMaterialization:
        materialization = (
            receipt_snapshot.execution_context_json or {}
        ).get("materialization")
        if not isinstance(materialization, dict):
            raise RuntimeError(
                "materialization receipt is malformed"
            )
        if materialization.get("request_hash") != request_hash:
            conflict = ConflictError(
                "idempotency key was already used",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "scenario_draft",
                    "retryable": False,
                },
            )
            conflict.request_id = actor.request_id
            raise conflict
        template = self.scenario_service.get_template(
            session,
            actor,
            int(materialization["scenario_id"]),
        )
        version = self.scenario_service.get_version(
            session,
            actor,
            int(materialization["scenario_version_id"]),
        )
        validation = ScenarioValidationResult.model_validate(
            materialization["validation"]
        )
        return ScenarioDraftMaterialization(
            template=template,
            scenario_version=version,
            validation=validation,
            status=str(materialization["status"]),
            replayed=True,
        )

    @staticmethod
    def _materialization_hash(
        session_id: int,
        draft_json: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            {
                "session_id": session_id,
                "draft": draft_json,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _field_value(
        draft: ScenarioDraftPayload,
        field_name: str,
        default: Any = None,
    ) -> Any:
        field = draft.fields.get(field_name)
        if field is None or field.value is None:
            return default
        return field.value

    def _materialization_payload(
        self,
        draft: ScenarioDraftPayload,
    ) -> ScenarioDraftMaterializationPayload:
        template_data = {
            "code": self._field_value(
                draft,
                "mission_code",
            ),
            "name": draft.scenario_name,
            "category": self._field_value(
                draft,
                "category",
            ),
            "description": self._field_value(
                draft,
                "description",
            ),
            "tags_json": self._field_value(
                draft,
                "tags",
            ),
        }
        version_data = {
            "version_code": self._field_value(
                draft,
                "version_code",
                "V1",
            ),
            "version_name": self._field_value(
                draft,
                "version_name",
                f"{draft.scenario_name} V1",
            ),
            "default_service_level": self._field_value(
                draft,
                "service_level",
            ),
            "missing_parameter_policy": (
                self._field_value(
                    draft,
                    "missing_parameter_policy",
                )
            ),
            "execution_mode": self._field_value(
                draft,
                "execution_preference",
            ),
            "comparison_enabled": self._field_value(
                draft,
                "comparison_enabled",
                False,
            ),
            "description": self._field_value(
                draft,
                "description",
            ),
        }
        simulation_config = self._field_value(
            draft,
            "simulation_config",
        )
        if simulation_config is not None:
            version_data["simulation_config_json"] = (
                simulation_config
            )
        return ScenarioDraftMaterializationPayload.model_validate(
            {
                "template": template_data,
                "version": version_data,
                "fleet_groups": self._field_value(
                    draft,
                    "fleet_groups",
                    [],
                ),
                "stages": self._field_value(
                    draft,
                    "stages",
                    [],
                ),
                "overrides": self._field_value(
                    draft,
                    "parameter_overrides",
                    [],
                ),
            }
        )

    @staticmethod
    def _raise_version_conflict(
        actor: ActorContext,
        *,
        expected_version: int,
        actual_version: int,
    ) -> None:
        conflict = ConflictError(
            "scenario draft version conflict",
            code="SCENARIO_DRAFT_VERSION_CONFLICT",
            details={
                "expected_version": expected_version,
                "actual_version": actual_version,
                "conflict_object": "scenario_draft",
                "suggested_action": "reload_server_draft",
                "retryable": False,
            },
        )
        conflict.request_id = actor.request_id
        raise conflict

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
