from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.models import AllocationRuleVersion
from app.repositories.allocation_repository import AllocationRepository
from app.schemas.allocation import (
    AllocationRuleActionResult,
    AllocationRuleDraftCommand,
    AllocationRulePublishCommand,
    AllocationRuleRead,
    AllocationRuleRetireCommand,
    AllocationSimulationSummaryRead,
    RuleSnapshot,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services.allocation_scoring import validate_weights
from app.services.snapshot_service import snapshot_service

_ROLE_RANK = {
    MaintenanceRole.VIEWER: 0,
    MaintenanceRole.CONTRIBUTOR: 1,
    MaintenanceRole.ADMIN: 2,
}
_DEFAULT_MAX_HIGH_PRIORITY_REGRESSION = Decimal("0.100000")


class AllocationRuleService:
    def __init__(
        self,
        *,
        repository: AllocationRepository | None = None,
    ) -> None:
        self.repository = repository or AllocationRepository()

    def create_draft(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command: AllocationRuleDraftCommand,
    ) -> AllocationRuleVersion:
        self._require_contributor(actor)
        validate_weights(command.weights)
        version_number = self.repository.next_lineage_version(
            session,
            actor.tenant_id,
            command.lineage_id,
        )
        return self.repository.create_rule(
            session,
            actor.tenant_id,
            self._draft_values(command, version_number=version_number),
        )

    # PLAN05_4D_TASK6_GREEN_D: route-facing rule reads/actions.
    def list_page(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        lineage_id: str | None = None,
    ) -> tuple[list[AllocationRuleVersion], int]:
        return self.repository.list_rules_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            lineage_id=lineage_id,
        )

    @staticmethod
    def read(
        rule: AllocationRuleVersion,
        *,
        latest_simulation: (
            AllocationSimulationSummaryRead | None
        ),
    ) -> AllocationRuleRead:
        return AllocationRuleRead(
            id=rule.id,
            lineage_id=rule.lineage_id,
            version_number=rule.version_number,
            status=rule.status,
            scope=dict(rule.scope_json or {}),
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            hard_rules=dict(rule.hard_rules_json or {}),
            weights=dict(rule.weights_json or {}),
            normalization=dict(
                rule.normalization_json or {}
            ),
            change_reason=rule.change_reason,
            published_by_user_id=rule.published_by_user_id,
            published_by_request_id=(
                rule.published_by_request_id
            ),
            published_at=rule.published_at,
            version=rule.version,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            latest_simulation=latest_simulation,
        )

    @staticmethod
    def action_result(
        rule: AllocationRuleVersion,
    ) -> AllocationRuleActionResult:
        return AllocationRuleActionResult(
            rule_id=rule.id,
            status=rule.status,
            version=rule.version,
            version_number=rule.version_number,
        )

    def publish_action(
        self,
        session: Session,
        actor: ActorContext,
        rule_id: int,
        *,
        command: AllocationRulePublishCommand,
        latest_simulation: Any,
        idempotency_key: str,
    ) -> AllocationRuleActionResult:
        self._require_admin(actor)
        clean_key = self._normalize_publish_idempotency_key(
            actor,
            idempotency_key,
        )
        request_hash = snapshot_service.canonical_hash(
            {
                "action": "RULE_PUBLISH",
                "rule_id": rule_id,
                "command": command.model_dump(mode="json"),
            }
        )

        receipt = (
            self.repository
            .get_rule_by_publish_idempotency_key(
                session,
                actor.tenant_id,
                clean_key,
            )
        )
        if receipt is not None:
            replay = self._validate_publish_replay(
                actor,
                receipt,
                rule_id=rule_id,
                request_hash=request_hash,
            )
            return self._stored_publish_action_result(
                actor,
                replay,
            )

        current = self.repository.get_rule(
            session,
            actor.tenant_id,
            rule_id,
        )
        if current is not None and current.status == "PUBLISHED":
            rule = self.publish_prevalidated(
                session,
                actor,
                rule_id,
                command=command,
                idempotency_key=clean_key,
            )
        else:
            rule = self.publish(
                session,
                actor,
                rule_id,
                command=command,
                latest_simulation=latest_simulation,
                idempotency_key=clean_key,
            )
        return self._stored_publish_action_result(
            actor,
            rule,
        )

    @staticmethod
    def _stored_publish_action_result(
        actor: ActorContext,
        rule: AllocationRuleVersion,
    ) -> AllocationRuleActionResult:
        snapshot = rule.publish_response_snapshot_json
        if not isinstance(snapshot, dict):
            AllocationRuleService._raise_conflict(
                actor,
                "stored idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )
        try:
            result = AllocationRuleActionResult.model_validate(
                snapshot
            )
        except (TypeError, ValueError):
            AllocationRuleService._raise_conflict(
                actor,
                "stored idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )
        return result.model_copy(deep=True)

    def revise(
        self,
        session: Session,
        actor: ActorContext,
        rule_id: int,
        *,
        command: AllocationRuleDraftCommand,
    ) -> AllocationRuleVersion:
        self._require_contributor(actor)
        validate_weights(command.weights)
        source = self.repository.get_rule_for_update(
            session,
            actor.tenant_id,
            rule_id,
        )
        if source is None:
            self._raise_not_found(actor, rule_id)
        if command.lineage_id != source.lineage_id:
            self._raise_conflict(
                actor,
                "allocation rule lineage cannot change during revision",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
            )

        if source.status == "DRAFT":
            source.scope_json = dict(command.scope)
            source.effective_from = command.effective_from
            source.effective_to = command.effective_to
            source.hard_rules_json = dict(command.hard_rules)
            source.weights_json = self._decimal_strings(command.weights)
            source.normalization_json = self._normalization_strings(
                command.normalization
            )
            source.change_reason = command.change_reason
            source.version += 1
            session.flush()
            return source

        version_number = self.repository.next_lineage_version(
            session,
            actor.tenant_id,
            source.lineage_id,
        )
        return self.repository.create_rule(
            session,
            actor.tenant_id,
            self._draft_values(command, version_number=version_number),
        )

    def publish(
        self,
        session: Session,
        actor: ActorContext,
        rule_id: int,
        *,
        command: AllocationRulePublishCommand,
        latest_simulation: Any,
        idempotency_key: str,
        max_high_priority_regression: Decimal = _DEFAULT_MAX_HIGH_PRIORITY_REGRESSION,
    ) -> AllocationRuleVersion:
        rule = self.repository.get_rule(session, actor.tenant_id, rule_id)
        if rule is None:
            self._raise_not_found(actor, rule_id)
        self.validate_publish_gate(
            rule_snapshot=self.snapshot(rule),
            latest_simulation=latest_simulation,
            max_high_priority_regression=max_high_priority_regression,
        )
        return self.publish_prevalidated(
            session,
            actor,
            rule_id,
            command=command,
            idempotency_key=idempotency_key,
        )

    def publish_prevalidated(
        self,
        session: Session,
        actor: ActorContext,
        rule_id: int,
        *,
        command: AllocationRulePublishCommand,
        idempotency_key: str,
    ) -> AllocationRuleVersion:
        self._require_admin(actor)
        clean_key = self._normalize_publish_idempotency_key(
            actor,
            idempotency_key,
        )
        request_hash = snapshot_service.canonical_hash(
            {
                "action": "RULE_PUBLISH",
                "rule_id": rule_id,
                "command": command.model_dump(mode="json"),
            }
        )

        receipt = self.repository.get_rule_by_publish_idempotency_key(
            session,
            actor.tenant_id,
            clean_key,
        )
        if receipt is not None:
            return self._validate_publish_replay(
                actor,
                receipt,
                rule_id=rule_id,
                request_hash=request_hash,
            )

        rule = self.repository.get_rule_for_update(
            session,
            actor.tenant_id,
            rule_id,
        )
        if rule is None:
            self._raise_not_found(actor, rule_id)

        receipt = self.repository.get_rule_by_publish_idempotency_key(
            session,
            actor.tenant_id,
            clean_key,
        )
        if receipt is not None:
            return self._validate_publish_replay(
                actor,
                receipt,
                rule_id=rule_id,
                request_hash=request_hash,
            )

        self._require_expected_version(actor, rule, command.expected_version)

        if rule.status == "PUBLISHED":
            if rule.publish_idempotency_key is not None:
                self._raise_conflict(
                    actor,
                    "allocation rule is already published under another receipt",
                    code="ALLOCATION_RULE_VERSION_CONFLICT",
                    details={
                        "status": rule.status,
                        "retryable": False,
                    },
                )
            self._persist_publish_receipt(
                session,
                actor,
                rule,
                idempotency_key=clean_key,
                request_hash=request_hash,
            )
            return rule

        if rule.status != "SIMULATED":
            self._raise_conflict(
                actor,
                "only a simulated allocation rule can be published",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={"status": rule.status},
            )

        overlaps = self.repository.find_overlapping_published_rules(
            session,
            tenant_id=actor.tenant_id,
            scope_json=rule.scope_json,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            exclude_rule_id=rule.id,
        )
        ambiguous = [
            item for item in overlaps
            if item.lineage_id != rule.lineage_id
        ]
        if ambiguous:
            self._raise_conflict(
                actor,
                "published allocation rule scope and effective range overlap",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={
                    "overlapping_rule_ids": [
                        item.id for item in ambiguous
                    ]
                },
            )
        for existing in overlaps:
            existing.status = "RETIRED"
            existing.version += 1

        rule.status = "PUBLISHED"
        rule.published_by_user_id = actor.user_id
        rule.published_by_request_id = actor.request_id
        rule.published_at = datetime.now(timezone.utc)
        rule.version += 1

        session.flush()
        self._persist_publish_receipt(
            session,
            actor,
            rule,
            idempotency_key=clean_key,
            request_hash=request_hash,
        )
        return rule

    def retire(
        self,
        session: Session,
        actor: ActorContext,
        rule_id: int,
        *,
        command: AllocationRuleRetireCommand,
        idempotency_key: str,
    ) -> AllocationRuleVersion:
        del idempotency_key
        self._require_admin(actor)
        rule = self.repository.get_rule_for_update(
            session,
            actor.tenant_id,
            rule_id,
        )
        if rule is None:
            self._raise_not_found(actor, rule_id)
        if rule.status == "RETIRED":
            return rule
        self._require_expected_version(actor, rule, command.expected_version)
        if rule.status != "PUBLISHED":
            self._raise_conflict(
                actor,
                "only a published allocation rule can be retired",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={"status": rule.status},
            )
        rule.status = "RETIRED"
        rule.version += 1
        session.flush()
        return rule

    @staticmethod
    def validate_publish_gate(
        *,
        rule_snapshot: Any,
        latest_simulation: Any,
        max_high_priority_regression: Decimal,
    ) -> None:
        reason: str | None = None
        if latest_simulation is None:
            reason = "missing"
        elif getattr(latest_simulation, "status", None) != "COMPLETED":
            reason = "not-completed"
        elif getattr(latest_simulation, "rule_hash", None) != rule_snapshot.canonical_hash:
            reason = "hash-mismatch"
        elif getattr(latest_simulation, "blockers", None):
            reason = "hard-rule-blocker"
        elif Decimal(
            str(getattr(latest_simulation, "high_priority_regression", "0"))
        ) > Decimal(str(max_high_priority_regression)):
            reason = "regression-threshold"

        if reason is not None:
            raise BusinessValidationError(
                "allocation rule requires a fresh successful simulation",
                code="ALLOCATION_RULE_SIMULATION_REQUIRED",
                details={"reason": reason},
            )

    # PLAN05_4D_TASK6_GREEN_A: strict rule-publish receipt helpers.
    @staticmethod
    def _normalize_publish_idempotency_key(
        actor: ActorContext,
        idempotency_key: str,
    ) -> str:
        clean_key = idempotency_key.strip()
        if not clean_key:
            error = BusinessValidationError(
                "Idempotency-Key header is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
                details={"retryable": False},
            )
            error.request_id = actor.request_id
            raise error
        if len(clean_key) > 128:
            error = BusinessValidationError(
                "Idempotency-Key must be at most 128 characters",
                details={"retryable": False},
            )
            error.request_id = actor.request_id
            raise error
        return clean_key

    @staticmethod
    def _publish_action_result(
        rule: AllocationRuleVersion,
    ) -> AllocationRuleActionResult:
        return AllocationRuleActionResult(
            rule_id=rule.id,
            status=rule.status,
            version=rule.version,
            version_number=rule.version_number,
        )

    def _validate_publish_replay(
        self,
        actor: ActorContext,
        receipt: AllocationRuleVersion,
        *,
        rule_id: int,
        request_hash: str,
    ) -> AllocationRuleVersion:
        if (
            receipt.id != rule_id
            or receipt.publish_request_hash != request_hash
        ):
            self._raise_conflict(
                actor,
                "Idempotency-Key was already used for a different request",
                code="IDEMPOTENCY_KEY_REUSED",
                details={"retryable": False},
            )

        snapshot = receipt.publish_response_snapshot_json
        if snapshot is None:
            self._raise_conflict(
                actor,
                "stored idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )

        try:
            stored = AllocationRuleActionResult.model_validate(snapshot)
        except (TypeError, ValueError):
            self._raise_conflict(
                actor,
                "stored idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )

        if stored.rule_id != receipt.id:
            self._raise_conflict(
                actor,
                "stored idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={"retryable": False},
            )
        return receipt

    def _persist_publish_receipt(
        self,
        session: Session,
        actor: ActorContext,
        rule: AllocationRuleVersion,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> None:
        try:
            with session.begin_nested():
                rule.publish_idempotency_key = idempotency_key
                rule.publish_request_hash = request_hash
                rule.publish_response_snapshot_json = (
                    self._publish_action_result(rule).model_dump(mode="json")
                )
                session.flush()
        except IntegrityError:
            receipt = self.repository.get_rule_by_publish_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
            if receipt is not None:
                self._validate_publish_replay(
                    actor,
                    receipt,
                    rule_id=rule.id,
                    request_hash=request_hash,
                )
                return
            raise

    @staticmethod
    def snapshot(rule: AllocationRuleVersion) -> RuleSnapshot:
        return RuleSnapshot(
            scope=rule.scope_json,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            hard_rules=rule.hard_rules_json,
            weights=rule.weights_json,
            normalization=rule.normalization_json,
        )

    @classmethod
    def _draft_values(
        cls,
        command: AllocationRuleDraftCommand,
        *,
        version_number: int,
    ) -> dict[str, Any]:
        return {
            "lineage_id": command.lineage_id,
            "version_number": version_number,
            "status": "DRAFT",
            "scope_json": dict(command.scope),
            "effective_from": command.effective_from,
            "effective_to": command.effective_to,
            "hard_rules_json": dict(command.hard_rules),
            "weights_json": cls._decimal_strings(command.weights),
            "normalization_json": cls._normalization_strings(command.normalization),
            "change_reason": command.change_reason,
            "version": 1,
        }

    @staticmethod
    def _decimal_strings(values: dict[str, Decimal]) -> dict[str, str]:
        return {key: format(value, "f") for key, value in values.items()}

    @staticmethod
    def _normalization_strings(
        values: dict[str, dict[str, Decimal]],
    ) -> dict[str, dict[str, str]]:
        return {
            key: {
                "min": format(bounds["min"], "f"),
                "max": format(bounds["max"], "f"),
            }
            for key, bounds in values.items()
        }

    @staticmethod
    def _require_expected_version(
        actor: ActorContext,
        rule: AllocationRuleVersion,
        expected_version: int,
    ) -> None:
        if rule.version != expected_version:
            AllocationRuleService._raise_conflict(
                actor,
                "allocation rule version conflict",
                code="ALLOCATION_RULE_VERSION_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": rule.version,
                },
            )

    @staticmethod
    def _require_contributor(actor: ActorContext) -> None:
        if _ROLE_RANK[actor.role] < _ROLE_RANK[MaintenanceRole.CONTRIBUTOR]:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.CONTRIBUTOR.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _require_admin(actor: ActorContext) -> None:
        if _ROLE_RANK[actor.role] < _ROLE_RANK[MaintenanceRole.ADMIN]:
            raise InsufficientMaintenanceRoleError(
                required_role=MaintenanceRole.ADMIN.value,
                actual_role=actor.role.value,
                request_id=actor.request_id,
            )

    @staticmethod
    def _raise_not_found(actor: ActorContext, rule_id: int) -> None:
        error = NotFoundError("allocation_rule", rule_id)
        error.request_id = actor.request_id
        raise error

    @staticmethod
    def _raise_conflict(
        actor: ActorContext,
        message: str,
        *,
        code: str,
        details: Any | None = None,
    ) -> None:
        error = ConflictError(message, code=code, details=details)
        error.request_id = actor.request_id
        raise error