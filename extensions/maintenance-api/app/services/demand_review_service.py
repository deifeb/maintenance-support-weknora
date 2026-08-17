from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models.demand_review import (
    DemandReview,
    DemandReviewEvent,
    DemandReviewFinding,
)
from app.models.enums import (
    DemandListStatus,
    DemandReviewCommandType,
    DemandReviewDecisionStatus,
    DemandReviewEventType,
    DemandReviewStatus,
)
from app.repositories.demand_list_repository import (
    DemandListItemRepository,
    DemandListRepository,
)
from app.repositories.demand_review_repository import DemandReviewRepository
from app.schemas.demand_review import (
    DemandReviewFindingRead,
    DemandReviewRead,
)
from app.security.actor import ActorContext
from app.services.demand_review_rules import run_rules
from app.services.demand_review_snapshot import DemandReviewSnapshotBuilder
from app.services.snapshot_service import snapshot_service


class DemandReviewService:
    def __init__(
        self,
        *,
        repository: DemandReviewRepository | None = None,
        demand_list_repository: DemandListRepository | None = None,
        item_repository: DemandListItemRepository | None = None,
        snapshot_builder: DemandReviewSnapshotBuilder | None = None,
    ) -> None:
        self.repository = repository or DemandReviewRepository()
        self.demand_list_repository = (
            demand_list_repository or DemandListRepository()
        )
        self.item_repository = (
            item_repository or DemandListItemRepository()
        )
        self.snapshot_builder = (
            snapshot_builder or DemandReviewSnapshotBuilder()
        )

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        clean_key = idempotency_key.strip()
        if not clean_key:
            raise BusinessValidationError(
                "idempotency key is required",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
        if len(clean_key) > 128:
            raise BusinessValidationError(
                "idempotency key is invalid",
                code="INVALID_IDEMPOTENCY_KEY",
            )
        return clean_key

    @staticmethod
    def _run_request_hash(
        *,
        demand_list_id: int,
        expected_source_version: int,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "command": "RUN",
                "demand_list_id": demand_list_id,
                "expected_source_version": expected_source_version,
            }
        )

    @staticmethod
    def _replay(
        event: DemandReviewEvent,
        request_hash: str,
    ) -> DemandReviewRead:
        if event.request_hash != request_hash:
            raise ConflictError(
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "demand_review",
                    "retryable": False,
                },
            )
        if event.response_snapshot_json is None:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "demand_review",
                    "retryable": False,
                },
            )
        try:
            return DemandReviewRead.model_validate(
                event.response_snapshot_json
            )
        except ValidationError as exc:
            raise ConflictError(
                "idempotent response is unavailable",
                code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
                details={
                    "conflict_object": "demand_review",
                    "retryable": False,
                },
            ) from exc

    @staticmethod
    def _require_source_authority(source: Any) -> None:
        if (
            source.status is not DemandListStatus.PUBLISHED
            or not source.is_current
        ):
            raise ConflictError(
                "formal demand review source must be current and published",
                code="DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED",
                details={
                    "conflict_object": "source_demand_list",
                    "retryable": False,
                },
            )

    @staticmethod
    def _require_source_version(
        source: Any,
        expected_source_version: int,
    ) -> None:
        if source.version != expected_source_version:
            raise ConflictError(
                "demand review source version conflict",
                code="REVIEW_VERSION_CONFLICT",
                details={
                    "expected_version": expected_source_version,
                    "actual_version": source.version,
                    "conflict_object": "source_demand_list",
                    "retryable": False,
                },
            )

    def _load_source(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
    ):
        source = self.demand_list_repository.get(
            session,
            actor.tenant_id,
            demand_list_id,
        )
        if source is None:
            raise NotFoundError(
                "demand_list",
                demand_list_id,
            )
        return source

    def _read_model(
        self,
        session: Session,
        actor: ActorContext,
        review: DemandReview,
    ) -> DemandReviewRead:
        findings = self.repository.list_findings(
            session,
            actor.tenant_id,
            review.id,
        )
        return DemandReviewRead(
            id=review.id,
            tenant_id=review.tenant_id,
            source_demand_list_id=review.source_demand_list_id,
            source_demand_list_version=(
                review.source_demand_list_version
            ),
            source_lineage_id=review.source_lineage_id,
            source_version_number=review.source_version_number,
            status=review.status,
            rule_set_version=review.rule_set_version,
            input_hash=review.input_hash,
            source_snapshot=review.source_snapshot_json,
            total_finding_count=review.total_finding_count,
            blocking_finding_count=review.blocking_finding_count,
            pending_finding_count=review.pending_finding_count,
            pending_blocking_finding_count=(
                review.pending_blocking_finding_count
            ),
            derived_demand_list_id=review.derived_demand_list_id,
            failure_code=review.failure_code,
            failure_summary=review.failure_summary,
            version=review.version,
            findings=tuple(
                self._finding_read(row)
                for row in findings
            ),
        )

    @staticmethod
    def _finding_read(
        row: DemandReviewFinding,
    ) -> DemandReviewFindingRead:
        return DemandReviewFindingRead(
            id=row.id,
            finding_key=row.finding_key,
            rule_code=row.rule_code,
            finding_type=row.finding_type,
            severity=row.severity,
            blocking=row.blocking,
            requires_admin_acceptance=row.requires_admin_acceptance,
            source_demand_list_item_id=(
                row.source_demand_list_item_id
            ),
            effect_key=row.effect_key,
            evidence_snapshot=row.evidence_snapshot_json,
            suggestion_snapshot=row.suggestion_snapshot_json,
            decision_status=row.decision_status,
            version=row.version,
        )

    @staticmethod
    def _refresh_counts(
        review: DemandReview,
        findings: list[DemandReviewFinding],
    ) -> None:
        review.total_finding_count = len(findings)
        review.blocking_finding_count = sum(
            1 for finding in findings if finding.blocking
        )
        review.pending_finding_count = sum(
            1
            for finding in findings
            if finding.decision_status
            is DemandReviewDecisionStatus.PENDING
        )
        review.pending_blocking_finding_count = sum(
            1
            for finding in findings
            if finding.blocking
            and finding.decision_status
            is DemandReviewDecisionStatus.PENDING
        )

    @staticmethod
    def _failure_summary(error: Exception) -> str:
        message = str(error).strip() or error.__class__.__name__
        return message[:1000]

    def run(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
        *,
        expected_source_version: int,
        idempotency_key: str,
    ) -> DemandReviewRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        request_hash = self._run_request_hash(
            demand_list_id=demand_list_id,
            expected_source_version=expected_source_version,
        )

        existing = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=DemandReviewCommandType.RUN,
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay(existing, request_hash)

        source = self._load_source(
            session,
            actor,
            demand_list_id,
        )
        self._require_source_authority(source)
        self._require_source_version(
            source,
            expected_source_version,
        )
        items = self.item_repository.list_for_demand_list(
            session,
            actor.tenant_id,
            source.id,
        )
        events = list(source.events)

        try:
            review = self.repository.create_review(
                session,
                actor.tenant_id,
                {
                    "source_demand_list_id": source.id,
                    "source_demand_list_version": source.version,
                    "source_lineage_id": source.lineage_id,
                    "source_version_number": source.version_number,
                    "status": DemandReviewStatus.CREATED,
                    "rule_set_version": "DEMAND-REVIEW-1",
                    "input_hash": "0" * 64,
                    "source_snapshot_json": {},
                },
            )
            self.repository.append_event(
                session,
                actor.tenant_id,
                review_id=review.id,
                data={
                    "event_type": DemandReviewEventType.CREATED,
                    "actor_user_id": actor.user_id,
                    "actor_roles_json": [actor.role.value],
                    "request_id": actor.request_id,
                    "after_summary_json": {
                        "status": DemandReviewStatus.CREATED.value,
                    },
                },
            )

            review.status = DemandReviewStatus.RUNNING
            self.repository.append_event(
                session,
                actor.tenant_id,
                review_id=review.id,
                data={
                    "event_type": DemandReviewEventType.RUNNING,
                    "actor_user_id": actor.user_id,
                    "actor_roles_json": [actor.role.value],
                    "request_id": actor.request_id,
                    "before_summary_json": {
                        "status": DemandReviewStatus.CREATED.value,
                    },
                    "after_summary_json": {
                        "status": DemandReviewStatus.RUNNING.value,
                    },
                },
            )
            session.flush()

            try:
                with session.begin_nested():
                    snapshot = self.snapshot_builder.build(
                        session,
                        actor,
                        source,
                        items,
                        events,
                    )
                    drafts = run_rules(snapshot)
                    review.rule_set_version = snapshot.rule_set_version
                    review.input_hash = snapshot.input_hash
                    review.source_snapshot_json = snapshot.model_dump(
                        mode="json"
                    )

                    persisted: list[DemandReviewFinding] = []
                    for draft in drafts:
                        persisted.append(
                            self.repository.append_finding(
                                session,
                                actor.tenant_id,
                                review_id=review.id,
                                data={
                                    "finding_key": draft.finding_key,
                                    "rule_code": draft.rule_code,
                                    "finding_type": draft.finding_type,
                                    "severity": draft.severity,
                                    "blocking": draft.blocking,
                                    "requires_admin_acceptance": (
                                        draft.requires_admin_acceptance
                                    ),
                                    "source_demand_list_item_id": (
                                        draft.source_demand_list_item_id
                                    ),
                                    "effect_key": draft.effect_key,
                                    "evidence_snapshot_json": (
                                        draft.evidence_snapshot
                                    ),
                                    "suggestion_snapshot_json": (
                                        draft.suggestion_snapshot
                                    ),
                                },
                            )
                        )

                    self._refresh_counts(review, persisted)
                    review.status = (
                        DemandReviewStatus.READY_TO_DERIVE
                        if review.pending_blocking_finding_count == 0
                        else DemandReviewStatus.OPEN
                    )
                    review.failure_code = None
                    review.failure_summary = None
                    session.flush()
            except Exception as rule_error:
                review.status = DemandReviewStatus.FAILED
                review.failure_code = "DEMAND_REVIEW_RUN_FAILED"
                review.failure_summary = self._failure_summary(rule_error)
                review.total_finding_count = 0
                review.blocking_finding_count = 0
                review.pending_finding_count = 0
                review.pending_blocking_finding_count = 0
                session.flush()

            final_event_type = {
                DemandReviewStatus.OPEN: DemandReviewEventType.OPENED,
                DemandReviewStatus.READY_TO_DERIVE: (
                    DemandReviewEventType.READY_TO_DERIVE
                ),
                DemandReviewStatus.FAILED: DemandReviewEventType.FAILED,
            }[review.status]
            final_event = self.repository.append_event(
                session,
                actor.tenant_id,
                review_id=review.id,
                data={
                    "event_type": final_event_type,
                    "command_type": DemandReviewCommandType.RUN,
                    "actor_user_id": actor.user_id,
                    "actor_roles_json": [actor.role.value],
                    "request_id": actor.request_id,
                    "idempotency_key": clean_key,
                    "request_hash": request_hash,
                    "before_summary_json": {
                        "status": DemandReviewStatus.RUNNING.value,
                    },
                    "after_summary_json": {
                        "status": review.status.value,
                        "total_finding_count": (
                            review.total_finding_count
                        ),
                        "blocking_finding_count": (
                            review.blocking_finding_count
                        ),
                    },
                    "error_code": review.failure_code,
                },
            )
            response = self._read_model(
                session,
                actor,
                review,
            )
            final_event.response_snapshot_json = response.model_dump(
                mode="json"
            )
            session.flush()
            session.commit()
            return response
        except IntegrityError as exc:
            session.rollback()
            winner = self.repository.find_command_event(
                session,
                actor.tenant_id,
                command_type=DemandReviewCommandType.RUN,
                idempotency_key=clean_key,
            )
            if winner is None:
                raise exc
            return self._replay(winner, request_hash)
        except Exception:
            session.rollback()
            raise
