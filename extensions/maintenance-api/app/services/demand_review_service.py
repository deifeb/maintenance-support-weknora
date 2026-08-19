from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models.demand_review import (
    DemandReview,
    DemandReviewDecision,
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
from app.schemas.common import PageData
from app.schemas.demand_review import (
    DemandReviewBatchDecisionItem,
    DemandReviewBatchDecisionRequest,
    DemandReviewDecisionRead,
    DemandReviewDecisionRequest,
    DemandReviewDeriveRead,
    DemandReviewEventRead,
    DemandReviewFindingRead,
    DemandReviewPublicRead,
    DemandReviewRead,
    DemandReviewSummaryRead,
    DemandReviewTransitionRequest,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.security.permissions import require_role
from app.services.demand_list_service import (
    DemandListDerivedItemOverride,
    DemandListService,
)
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
        demand_list_service: DemandListService | None = None,
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
        self.demand_list_service = (
            demand_list_service
            or DemandListService(
                repository=self.demand_list_repository,
                item_repository=self.item_repository,
            )
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
    def _idempotent_response_unavailable() -> ConflictError:
        return ConflictError(
            "idempotent response is unavailable",
            code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
            details={
                "conflict_object": "demand_review",
                "retryable": False,
            },
        )

    @staticmethod
    def _snapshot_section(
        event: DemandReviewEvent,
        section: str,
    ) -> Any:
        snapshot = event.response_snapshot_json
        if (
            isinstance(snapshot, dict)
            and snapshot.get("_format")
            == "demand_review_command_response_v2"
        ):
            return snapshot.get(section)
        if section == "internal":
            return snapshot
        return None

    @staticmethod
    def _response_envelope(
        internal: DemandReviewRead | DemandReviewDeriveRead,
        public: DemandReviewPublicRead,
    ) -> dict[str, Any]:
        return {
            "_format": "demand_review_command_response_v2",
            "internal": internal.model_dump(mode="json"),
            "public": public.model_dump(mode="json"),
        }

    @staticmethod
    def _public_replay(
        event: DemandReviewEvent,
    ) -> DemandReviewPublicRead:
        payload = DemandReviewService._snapshot_section(
            event,
            "public",
        )
        if payload is None:
            raise DemandReviewService._idempotent_response_unavailable()
        try:
            return DemandReviewPublicRead.model_validate(payload)
        except ValidationError as exc:
            raise (
                DemandReviewService._idempotent_response_unavailable()
            ) from exc

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
        payload = DemandReviewService._snapshot_section(
            event,
            "internal",
        )
        if payload is None:
            raise DemandReviewService._idempotent_response_unavailable()
        try:
            return DemandReviewRead.model_validate(payload)
        except ValidationError as exc:
            raise (
                DemandReviewService._idempotent_response_unavailable()
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
    def _summary_read(
        row: DemandReview,
    ) -> DemandReviewSummaryRead:
        return DemandReviewSummaryRead(
            id=row.id,
            source_demand_list_id=row.source_demand_list_id,
            source_demand_list_version=row.source_demand_list_version,
            source_lineage_id=row.source_lineage_id,
            source_version_number=row.source_version_number,
            status=row.status,
            rule_set_version=row.rule_set_version,
            input_hash=row.input_hash,
            total_finding_count=row.total_finding_count,
            blocking_finding_count=row.blocking_finding_count,
            pending_finding_count=row.pending_finding_count,
            pending_blocking_finding_count=(
                row.pending_blocking_finding_count
            ),
            derived_demand_list_id=row.derived_demand_list_id,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _decision_read(
        row: DemandReviewDecision,
    ) -> DemandReviewDecisionRead:
        return DemandReviewDecisionRead(
            id=row.id,
            finding_id=row.finding_id,
            action=DemandReviewDecisionStatus(row.action),
            suggested_quantity=row.suggested_quantity,
            final_quantity=row.final_quantity,
            reason=row.reason,
            actor_user_id=row.actor_user_id,
            actor_roles=tuple(row.actor_roles_json),
            request_id=row.request_id,
            review_version_before=row.review_version_before,
            review_version_after=row.review_version_after,
            finding_version_before=row.finding_version_before,
            finding_version_after=row.finding_version_after,
            before_snapshot=row.before_snapshot_json,
            after_snapshot=row.after_snapshot_json,
            occurred_at=row.occurred_at,
        )

    @staticmethod
    def _event_read(
        row: DemandReviewEvent,
    ) -> DemandReviewEventRead:
        return DemandReviewEventRead(
            id=row.id,
            event_type=row.event_type,
            command_type=row.command_type,
            actor_user_id=row.actor_user_id,
            actor_roles=tuple(row.actor_roles_json),
            request_id=row.request_id,
            before_summary=row.before_summary_json,
            after_summary=row.after_summary_json,
            error_code=row.error_code,
            occurred_at=row.occurred_at,
        )

    def _public_read(
        self,
        session: Session,
        actor: ActorContext,
        review: DemandReview,
    ) -> DemandReviewPublicRead:
        summary = self._summary_read(review)
        findings = self.repository.list_findings(
            session,
            actor.tenant_id,
            review.id,
        )
        decisions = self.repository.list_decisions(
            session,
            actor.tenant_id,
            review.id,
        )
        events = self.repository.list_events(
            session,
            actor.tenant_id,
            review.id,
        )
        return DemandReviewPublicRead(
            **summary.model_dump(),
            failure_code=review.failure_code,
            failure_summary=review.failure_summary,
            findings=tuple(
                self._finding_read(row)
                for row in findings
            ),
            decisions=tuple(
                self._decision_read(row)
                for row in decisions
            ),
            events=tuple(
                self._event_read(row)
                for row in events
            ),
        )

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int = 1,
        page_size: int = 20,
        status: DemandReviewStatus | None = None,
        source_demand_list_id: int | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> PageData[DemandReviewSummaryRead]:
        require_role(actor, MaintenanceRole.VIEWER)
        if page < 1 or page_size < 1 or page_size > 200:
            raise BusinessValidationError(
                "invalid demand review pagination",
                code="REVIEW_LIST_INVALID",
            )
        if sort_by not in {
            "id",
            "status",
            "created_at",
            "updated_at",
        } or sort_order not in {"asc", "desc"}:
            raise BusinessValidationError(
                "invalid demand review sort",
                code="REVIEW_LIST_INVALID",
            )

        rows, total = self.repository.list_page(
            session,
            actor.tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            source_demand_list_id=source_demand_list_id,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        pages = (
            (total + page_size - 1) // page_size
            if total
            else 0
        )
        return PageData[DemandReviewSummaryRead](
            items=[
                self._summary_read(row)
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    def get(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
    ) -> DemandReviewPublicRead:
        require_role(actor, MaintenanceRole.VIEWER)
        review = self.repository.get(
            session,
            actor.tenant_id,
            review_id,
        )
        if review is None:
            raise NotFoundError("demand_review", review_id)
        return self._public_read(
            session,
            actor,
            review,
        )

    def _public_command_response(
        self,
        session: Session,
        actor: ActorContext,
        *,
        command_type: DemandReviewCommandType,
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        event = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=command_type,
            idempotency_key=idempotency_key,
        )
        if event is None:
            raise self._idempotent_response_unavailable()
        return self._public_replay(event)

    def run_public(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
        *,
        expected_source_version: int,
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        self.run(
            session,
            actor,
            demand_list_id,
            expected_source_version=expected_source_version,
            idempotency_key=clean_key,
        )
        return self._public_command_response(
            session,
            actor,
            command_type=DemandReviewCommandType.RUN,
            idempotency_key=clean_key,
        )

    def decide_finding_public(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        finding_id: int,
        *,
        expected_review_version: int,
        expected_finding_version: int,
        action: DemandReviewDecisionStatus,
        final_quantity: Decimal | None,
        reason: str | None,
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        self.decide_finding(
            session,
            actor,
            review_id,
            finding_id,
            expected_review_version=expected_review_version,
            expected_finding_version=expected_finding_version,
            action=action,
            final_quantity=final_quantity,
            reason=reason,
            idempotency_key=clean_key,
        )
        return self._public_command_response(
            session,
            actor,
            command_type=DemandReviewCommandType.DECIDE_FINDING,
            idempotency_key=clean_key,
        )

    def batch_decide_public(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        commands: tuple[DemandReviewBatchDecisionItem, ...],
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        self.batch_decide(
            session,
            actor,
            review_id,
            expected_review_version=expected_review_version,
            commands=commands,
            idempotency_key=clean_key,
        )
        return self._public_command_response(
            session,
            actor,
            command_type=DemandReviewCommandType.BATCH_DECIDE,
            idempotency_key=clean_key,
        )

    def derive_public(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        self.derive(
            session,
            actor,
            review_id,
            expected_review_version=expected_review_version,
            idempotency_key=clean_key,
        )
        return self._public_command_response(
            session,
            actor,
            command_type=DemandReviewCommandType.DERIVE,
            idempotency_key=clean_key,
        )

    def void_public(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        idempotency_key: str,
    ) -> DemandReviewPublicRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        self.void(
            session,
            actor,
            review_id,
            expected_review_version=expected_review_version,
            idempotency_key=clean_key,
        )
        return self._public_command_response(
            session,
            actor,
            command_type=DemandReviewCommandType.VOID,
            idempotency_key=clean_key,
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
    def _void_request_hash(
        *,
        review_id: int,
        expected_review_version: int,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "command": "VOID",
                "review_id": review_id,
                "expected_review_version": expected_review_version,
            }
        )

    @staticmethod
    def _derive_request_hash(
        *,
        review_id: int,
        expected_review_version: int,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "command": "DERIVE",
                "review_id": review_id,
                "expected_review_version": expected_review_version,
            }
        )

    @staticmethod
    def _derive_replay(
        event: DemandReviewEvent,
        request_hash: str,
    ) -> DemandReviewDeriveRead:
        if event.request_hash != request_hash:
            raise ConflictError(
                "idempotency key was reused",
                code="IDEMPOTENCY_KEY_REUSED",
                details={
                    "conflict_object": "demand_review",
                    "retryable": False,
                },
            )
        payload = DemandReviewService._snapshot_section(
            event,
            "internal",
        )
        if payload is None:
            raise DemandReviewService._idempotent_response_unavailable()
        try:
            return DemandReviewDeriveRead.model_validate(payload)
        except ValidationError as exc:
            raise (
                DemandReviewService._idempotent_response_unavailable()
            ) from exc

    @staticmethod
    def _derivation_conflict(
        review: DemandReview,
        source: Any,
        *,
        reason: str,
    ) -> ConflictError:
        return ConflictError(
            "demand review derivation conflict",
            code="REVIEW_DERIVATION_CONFLICT",
            details={
                "reason": reason,
                "expected_status": DemandListStatus.PUBLISHED.value,
                "actual_status": source.status.value,
                "expected_current": True,
                "actual_current": bool(source.is_current),
                "expected_source_version": (
                    review.source_demand_list_version
                ),
                "actual_source_version": source.version,
                "conflict_object": "source_demand_list",
                "retryable": False,
            },
        )

    @classmethod
    def _require_derivation_source(
        cls,
        review: DemandReview,
        source: Any,
    ) -> None:
        if source.status is not DemandListStatus.PUBLISHED:
            raise cls._derivation_conflict(
                review,
                source,
                reason="source_not_published",
            )
        if not source.is_current:
            raise cls._derivation_conflict(
                review,
                source,
                reason="source_not_current",
            )
        if source.version != review.source_demand_list_version:
            raise cls._derivation_conflict(
                review,
                source,
                reason="source_version_changed",
            )

    @staticmethod
    def _derive_quantity(
        finding: DemandReviewFinding,
        decision: DemandReviewDecision,
    ) -> Decimal | None:
        if not DemandReviewService._quantity_effect(finding):
            return None
        if finding.source_demand_list_item_id is None:
            raise ConflictError(
                "demand review derivation conflict",
                code="REVIEW_DERIVATION_CONFLICT",
                details={
                    "reason": "quantity_effect_missing_source_item",
                    "finding_id": finding.id,
                    "conflict_object": "demand_review_finding",
                    "retryable": False,
                },
            )
        expected_effect_key = (
            f"FINAL_QUANTITY:{finding.source_demand_list_item_id}"
        )
        if finding.effect_key != expected_effect_key:
            raise ConflictError(
                "demand review derivation conflict",
                code="REVIEW_DERIVATION_CONFLICT",
                details={
                    "reason": "quantity_effect_key_invalid",
                    "finding_id": finding.id,
                    "effect_key": finding.effect_key,
                    "conflict_object": "demand_review_finding",
                    "retryable": False,
                },
            )

        raw_quantity: Any
        if (
            finding.decision_status
            is DemandReviewDecisionStatus.ACCEPTED
        ):
            raw_quantity = finding.suggestion_snapshot_json.get(
                "final_quantity"
            )
        elif (
            finding.decision_status
            is DemandReviewDecisionStatus.EDIT_ACCEPTED
        ):
            raw_quantity = decision.final_quantity
        else:
            return None

        try:
            quantity = Decimal(str(raw_quantity))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ConflictError(
                "demand review derivation conflict",
                code="REVIEW_DERIVATION_CONFLICT",
                details={
                    "reason": "quantity_effect_value_invalid",
                    "finding_id": finding.id,
                    "conflict_object": "demand_review_finding",
                    "retryable": False,
                },
            ) from exc

        if not quantity.is_finite() or quantity < 0:
            raise ConflictError(
                "demand review derivation conflict",
                code="REVIEW_DERIVATION_CONFLICT",
                details={
                    "reason": "quantity_effect_value_invalid",
                    "finding_id": finding.id,
                    "conflict_object": "demand_review_finding",
                    "retryable": False,
                },
            )
        return quantity

    def _derive_item_overrides(
        self,
        session: Session,
        review: DemandReview,
        findings: list[DemandReviewFinding],
    ) -> dict[int, DemandListDerivedItemOverride]:
        decision_rows = list(
            session.scalars(
                select(DemandReviewDecision)
                .where(
                    DemandReviewDecision.tenant_id == review.tenant_id,
                    DemandReviewDecision.review_id == review.id,
                )
                .order_by(
                    DemandReviewDecision.finding_id.asc(),
                    DemandReviewDecision.id.asc(),
                )
            ).all()
        )
        latest_by_finding: dict[int, DemandReviewDecision] = {}
        for decision in decision_rows:
            latest_by_finding[decision.finding_id] = decision

        overrides: dict[int, DemandListDerivedItemOverride] = {}
        for finding in findings:
            if (
                finding.decision_status
                is DemandReviewDecisionStatus.PENDING
            ):
                if finding.blocking:
                    raise ConflictError(
                        "demand review has unresolved findings",
                        code="REVIEW_FINDINGS_UNRESOLVED",
                        details={
                            "review_id": review.id,
                            "finding_id": finding.id,
                            "conflict_object": "demand_review",
                            "retryable": False,
                        },
                    )
                continue

            decision = latest_by_finding.get(finding.id)
            if decision is None:
                raise ConflictError(
                    "demand review derivation conflict",
                    code="REVIEW_DERIVATION_CONFLICT",
                    details={
                        "reason": "resolved_finding_has_no_decision",
                        "finding_id": finding.id,
                        "conflict_object": "demand_review_finding",
                        "retryable": False,
                    },
                )
            if decision.action != finding.decision_status.value:
                raise ConflictError(
                    "demand review derivation conflict",
                    code="REVIEW_DERIVATION_CONFLICT",
                    details={
                        "reason": "decision_projection_mismatch",
                        "finding_id": finding.id,
                        "conflict_object": "demand_review_finding",
                        "retryable": False,
                    },
                )

            quantity = self._derive_quantity(finding, decision)
            if quantity is None:
                continue

            source_item_id = finding.source_demand_list_item_id
            assert source_item_id is not None
            if source_item_id in overrides:
                raise ConflictError(
                    "demand review derivation conflict",
                    code="REVIEW_DERIVATION_CONFLICT",
                    details={
                        "reason": "duplicate_quantity_effect",
                        "finding_id": finding.id,
                        "source_demand_list_item_id": source_item_id,
                        "conflict_object": "demand_review_finding",
                        "retryable": False,
                    },
                )

            reason = (
                (decision.reason or "").strip()
                or str(
                    finding.suggestion_snapshot_json.get("reason")
                    or ""
                ).strip()
                or "formal demand review quantity"
            )
            overrides[source_item_id] = DemandListDerivedItemOverride(
                final_quantity=quantity,
                reason=reason,
                review_id=review.id,
                finding_id=finding.id,
                decision_id=decision.id,
            )
        return overrides

    @staticmethod
    def _failure_summary(error: Exception) -> str:
        message = str(error).strip() or error.__class__.__name__
        return message[:1000]

    @staticmethod
    def _decision_request_hash(
        *,
        review_id: int,
        finding_id: int,
        request: DemandReviewDecisionRequest,
    ) -> str:
        return snapshot_service.canonical_hash(
            {
                "command": "DECIDE_FINDING",
                "review_id": review_id,
                "finding_id": finding_id,
                "expected_review_version": request.expected_review_version,
                "expected_finding_version": request.expected_finding_version,
                "action": request.action,
                "final_quantity": request.final_quantity,
                "reason": request.reason,
            }
        )

    @staticmethod
    def _batch_request_hash(
        *,
        review_id: int,
        request: DemandReviewBatchDecisionRequest,
    ) -> str:
        canonical_decisions = [
            {
                "finding_id": command.finding_id,
                "expected_finding_version": command.expected_finding_version,
                "action": command.action,
                "final_quantity": command.final_quantity,
                "reason": command.reason,
            }
            for command in sorted(
                request.decisions,
                key=lambda item: item.finding_id,
            )
        ]
        return snapshot_service.canonical_hash(
            {
                "command": "BATCH_DECIDE",
                "review_id": review_id,
                "expected_review_version": request.expected_review_version,
                "decisions": canonical_decisions,
            }
        )

    @staticmethod
    def _version_conflict(
        *,
        conflict_object: str,
        expected_version: int,
        actual_version: int,
        affected_lines: list[int] | None = None,
    ) -> ConflictError:
        return ConflictError(
            "demand review version conflict",
            code="REVIEW_VERSION_CONFLICT",
            details={
                "conflict_object": conflict_object,
                "expected_version": expected_version,
                "actual_version": actual_version,
                "affected_lines": affected_lines or [],
                "retryable": False,
                "suggested_action": "reload_authoritative_review",
            },
        )

    @staticmethod
    def _require_decision_state(review: DemandReview) -> None:
        if review.status not in {
            DemandReviewStatus.OPEN,
            DemandReviewStatus.READY_TO_DERIVE,
        }:
            raise ConflictError(
                "demand review does not accept decisions in its current state",
                code="REVIEW_STATE_CONFLICT",
                details={
                    "conflict_object": "demand_review",
                    "actual_status": review.status.value,
                    "retryable": False,
                },
            )

    @staticmethod
    def _require_review_version(
        review: DemandReview,
        expected_version: int,
        *,
        affected_lines: list[int] | None = None,
    ) -> None:
        if review.version != expected_version:
            raise DemandReviewService._version_conflict(
                conflict_object="demand_review",
                expected_version=expected_version,
                actual_version=review.version,
                affected_lines=affected_lines,
            )

    @staticmethod
    def _require_finding_version(
        finding: DemandReviewFinding,
        expected_version: int,
    ) -> None:
        if finding.version != expected_version:
            raise DemandReviewService._version_conflict(
                conflict_object="demand_review_finding",
                expected_version=expected_version,
                actual_version=finding.version,
                affected_lines=[finding.id],
            )

    @staticmethod
    def _quantity_effect(finding: DemandReviewFinding) -> bool:
        return bool(
            finding.effect_key
            and finding.effect_key.startswith("FINAL_QUANTITY:")
        )

    @staticmethod
    def _suggested_quantity(
        finding: DemandReviewFinding,
    ) -> Decimal | None:
        if not DemandReviewService._quantity_effect(finding):
            return None
        raw_quantity = finding.suggestion_snapshot_json.get(
            "final_quantity"
        )
        if raw_quantity is None:
            return None
        return Decimal(str(raw_quantity))

    @staticmethod
    def _validate_action(
        actor: ActorContext,
        finding: DemandReviewFinding,
        *,
        action: DemandReviewDecisionStatus,
        final_quantity: Decimal | None,
        reason: str | None,
    ) -> None:
        require_role(actor, MaintenanceRole.CONTRIBUTOR)
        if (
            finding.requires_admin_acceptance
            and action
            in {
                DemandReviewDecisionStatus.ACCEPTED,
                DemandReviewDecisionStatus.EDIT_ACCEPTED,
            }
        ):
            require_role(actor, MaintenanceRole.ADMIN)
        if (
            action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            and not DemandReviewService._quantity_effect(finding)
        ):
            raise BusinessValidationError(
                "edited acceptance requires a final quantity finding",
                code="REVIEW_DECISION_INVALID",
                details={
                    "finding_id": finding.id,
                    "effect_key": finding.effect_key,
                },
            )
        if (
            action is DemandReviewDecisionStatus.EDIT_ACCEPTED
            and (final_quantity is None or reason is None)
        ):
            raise BusinessValidationError(
                "edited acceptance requires final quantity and reason",
                code="REVIEW_DECISION_INVALID",
                details={"finding_id": finding.id},
            )
        if (
            action is DemandReviewDecisionStatus.ACCEPTED
            and DemandReviewService._quantity_effect(finding)
            and DemandReviewService._suggested_quantity(finding) is None
        ):
            raise BusinessValidationError(
                "accepted quantity finding has no server suggestion",
                code="REVIEW_DECISION_INVALID",
                details={"finding_id": finding.id},
            )

    @staticmethod
    def _finding_snapshot(
        finding: DemandReviewFinding,
        *,
        status: DemandReviewDecisionStatus | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        return {
            "finding_id": finding.id,
            "decision_status": (
                status or finding.decision_status
            ).value,
            "version": finding.version if version is None else version,
            "effect_key": finding.effect_key,
        }

    @staticmethod
    def _review_summary(review: DemandReview) -> dict[str, Any]:
        return {
            "status": review.status.value,
            "version": review.version,
            "total_finding_count": review.total_finding_count,
            "blocking_finding_count": review.blocking_finding_count,
            "pending_finding_count": review.pending_finding_count,
            "pending_blocking_finding_count": (
                review.pending_blocking_finding_count
            ),
        }

    @staticmethod
    def _decision_event_type(
        before_status: DemandReviewStatus,
        after_status: DemandReviewStatus,
        *,
        batch: bool,
    ) -> DemandReviewEventType:
        if (
            after_status is DemandReviewStatus.READY_TO_DERIVE
            and before_status is not DemandReviewStatus.READY_TO_DERIVE
        ):
            return DemandReviewEventType.READY_TO_DERIVE
        return (
            DemandReviewEventType.BATCH_DECIDED
            if batch
            else DemandReviewEventType.DECIDED
        )

    def _lock_review_for_decision(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_version: int,
        affected_lines: list[int] | None = None,
    ) -> DemandReview:
        review = self.repository.get_for_update(
            session,
            actor.tenant_id,
            review_id,
        )
        if review is None:
            raise NotFoundError("demand_review", review_id)
        self._require_decision_state(review)
        self._require_review_version(
            review,
            expected_version,
            affected_lines=affected_lines,
        )
        return review

    def _append_decision(
        self,
        session: Session,
        actor: ActorContext,
        review: DemandReview,
        finding: DemandReviewFinding,
        *,
        action: DemandReviewDecisionStatus,
        final_quantity: Decimal | None,
        reason: str | None,
        request_hash: str,
        review_version_before: int,
        review_version_after: int,
    ) -> None:
        finding_version_before = finding.version
        finding_version_after = finding_version_before + 1
        suggested_quantity = self._suggested_quantity(finding)
        self.repository.append_decision(
            session,
            actor.tenant_id,
            review_id=review.id,
            finding_id=finding.id,
            data={
                "action": action.value,
                "suggested_quantity": suggested_quantity,
                "final_quantity": (
                    final_quantity
                    if action is DemandReviewDecisionStatus.EDIT_ACCEPTED
                    else None
                ),
                "reason": reason,
                "actor_user_id": actor.user_id,
                "actor_roles_json": [actor.role.value],
                "request_id": actor.request_id,
                "request_hash": request_hash,
                "review_version_before": review_version_before,
                "review_version_after": review_version_after,
                "finding_version_before": finding_version_before,
                "finding_version_after": finding_version_after,
                "before_snapshot_json": self._finding_snapshot(finding),
                "after_snapshot_json": self._finding_snapshot(
                    finding,
                    status=action,
                    version=finding_version_after,
                ),
            },
        )
        finding.decision_status = action
        finding.version = finding_version_after

    def _finalize_decision_command(
        self,
        session: Session,
        actor: ActorContext,
        review: DemandReview,
        *,
        before_status: DemandReviewStatus,
        before_summary: dict[str, Any],
        command_type: DemandReviewCommandType,
        idempotency_key: str,
        request_hash: str,
        batch: bool,
    ) -> DemandReviewRead:
        session.flush()
        findings = self.repository.list_findings(
            session,
            actor.tenant_id,
            review.id,
        )
        self._refresh_counts(review, findings)
        review.status = (
            DemandReviewStatus.READY_TO_DERIVE
            if review.pending_blocking_finding_count == 0
            else DemandReviewStatus.OPEN
        )
        session.flush()
        event = self.repository.append_event(
            session,
            actor.tenant_id,
            review_id=review.id,
            data={
                "event_type": self._decision_event_type(
                    before_status,
                    review.status,
                    batch=batch,
                ),
                "command_type": command_type,
                "actor_user_id": actor.user_id,
                "actor_roles_json": [actor.role.value],
                "request_id": actor.request_id,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "before_summary_json": before_summary,
                "after_summary_json": self._review_summary(review),
            },
        )
        response = self._read_model(session, actor, review)
        public_response = self._public_read(
            session,
            actor,
            review,
        )
        event.response_snapshot_json = self._response_envelope(
            response,
            public_response,
        )
        session.flush()
        session.commit()
        return response

    def decide_finding(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        finding_id: int,
        *,
        expected_review_version: int,
        expected_finding_version: int,
        action: DemandReviewDecisionStatus,
        final_quantity: Decimal | None,
        reason: str | None,
        idempotency_key: str,
    ) -> DemandReviewRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        try:
            request = DemandReviewDecisionRequest(
                expected_review_version=expected_review_version,
                expected_finding_version=expected_finding_version,
                action=action.value,
                final_quantity=final_quantity,
                reason=reason,
            )
        except ValidationError as exc:
            raise BusinessValidationError(
                "invalid demand review decision",
                code="REVIEW_DECISION_INVALID",
            ) from exc
        request_hash = self._decision_request_hash(
            review_id=review_id,
            finding_id=finding_id,
            request=request,
        )
        existing = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=DemandReviewCommandType.DECIDE_FINDING,
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay(existing, request_hash)

        review = self._lock_review_for_decision(
            session,
            actor,
            review_id,
            expected_version=request.expected_review_version,
            affected_lines=[finding_id],
        )
        locked = self.repository.findings_for_update(
            session,
            actor.tenant_id,
            review.id,
            finding_ids=(finding_id,),
        )
        if len(locked) != 1:
            raise NotFoundError("demand_review_finding", finding_id)
        finding = locked[0]
        self._require_finding_version(
            finding,
            request.expected_finding_version,
        )
        action_value = DemandReviewDecisionStatus(request.action)
        self._validate_action(
            actor,
            finding,
            action=action_value,
            final_quantity=request.final_quantity,
            reason=request.reason,
        )

        review_version_before = review.version
        before_status = review.status
        before_summary = self._review_summary(review)
        try:
            review.version = review_version_before + 1
            session.flush()
            self._append_decision(
                session,
                actor,
                review,
                finding,
                action=action_value,
                final_quantity=request.final_quantity,
                reason=request.reason,
                request_hash=request_hash,
                review_version_before=review_version_before,
                review_version_after=review.version,
            )
            return self._finalize_decision_command(
                session,
                actor,
                review,
                before_status=before_status,
                before_summary=before_summary,
                command_type=DemandReviewCommandType.DECIDE_FINDING,
                idempotency_key=clean_key,
                request_hash=request_hash,
                batch=False,
            )
        except IntegrityError as exc:
            session.rollback()
            winner = self.repository.find_command_event(
                session,
                actor.tenant_id,
                command_type=DemandReviewCommandType.DECIDE_FINDING,
                idempotency_key=clean_key,
            )
            if winner is None:
                raise exc
            return self._replay(winner, request_hash)
        except Exception:
            session.rollback()
            raise

    def batch_decide(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        commands: tuple[DemandReviewBatchDecisionItem, ...],
        idempotency_key: str,
    ) -> DemandReviewRead:
        clean_key = self._normalize_idempotency_key(idempotency_key)
        try:
            request = DemandReviewBatchDecisionRequest(
                expected_review_version=expected_review_version,
                decisions=commands,
            )
        except ValidationError as exc:
            raise BusinessValidationError(
                "invalid demand review batch decision",
                code="REVIEW_DECISION_INVALID",
            ) from exc
        request_hash = self._batch_request_hash(
            review_id=review_id,
            request=request,
        )
        existing = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=DemandReviewCommandType.BATCH_DECIDE,
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay(existing, request_hash)

        ordered_commands = tuple(
            sorted(request.decisions, key=lambda item: item.finding_id)
        )
        finding_ids = [command.finding_id for command in ordered_commands]
        review = self._lock_review_for_decision(
            session,
            actor,
            review_id,
            expected_version=request.expected_review_version,
            affected_lines=finding_ids,
        )
        findings = self.repository.findings_for_update(
            session,
            actor.tenant_id,
            review.id,
            finding_ids=tuple(finding_ids),
        )
        if len(findings) != len(finding_ids):
            actual_ids = {finding.id for finding in findings}
            missing_id = next(
                finding_id
                for finding_id in finding_ids
                if finding_id not in actual_ids
            )
            raise NotFoundError("demand_review_finding", missing_id)

        by_id = {finding.id: finding for finding in findings}
        validated: list[
            tuple[
                DemandReviewBatchDecisionItem,
                DemandReviewFinding,
                DemandReviewDecisionStatus,
            ]
        ] = []
        for command in ordered_commands:
            finding = by_id[command.finding_id]
            self._require_finding_version(
                finding,
                command.expected_finding_version,
            )
            action_value = DemandReviewDecisionStatus(command.action)
            self._validate_action(
                actor,
                finding,
                action=action_value,
                final_quantity=command.final_quantity,
                reason=command.reason,
            )
            validated.append((command, finding, action_value))

        review_version_before = review.version
        before_status = review.status
        before_summary = self._review_summary(review)
        try:
            review.version = review_version_before + 1
            session.flush()
            for command, finding, action_value in validated:
                self._append_decision(
                    session,
                    actor,
                    review,
                    finding,
                    action=action_value,
                    final_quantity=command.final_quantity,
                    reason=command.reason,
                    request_hash=request_hash,
                    review_version_before=review_version_before,
                    review_version_after=review.version,
                )
            return self._finalize_decision_command(
                session,
                actor,
                review,
                before_status=before_status,
                before_summary=before_summary,
                command_type=DemandReviewCommandType.BATCH_DECIDE,
                idempotency_key=clean_key,
                request_hash=request_hash,
                batch=True,
            )
        except IntegrityError as exc:
            session.rollback()
            winner = self.repository.find_command_event(
                session,
                actor.tenant_id,
                command_type=DemandReviewCommandType.BATCH_DECIDE,
                idempotency_key=clean_key,
            )
            if winner is None:
                raise exc
            return self._replay(winner, request_hash)
        except Exception:
            session.rollback()
            raise

    def void(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        idempotency_key: str,
    ) -> DemandReviewRead:
        require_role(actor, MaintenanceRole.ADMIN)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        try:
            request = DemandReviewTransitionRequest(
                expected_review_version=expected_review_version,
            )
        except ValidationError as exc:
            raise BusinessValidationError(
                "invalid demand review transition",
                code="REVIEW_VERSION_INVALID",
            ) from exc

        request_hash = self._void_request_hash(
            review_id=review_id,
            expected_review_version=request.expected_review_version,
        )
        existing = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=DemandReviewCommandType.VOID,
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._replay(existing, request_hash)

        try:
            review = self.repository.get_for_update(
                session,
                actor.tenant_id,
                review_id,
            )
            if review is None:
                raise NotFoundError("demand_review", review_id)
            self._require_review_version(
                review,
                request.expected_review_version,
            )
            if review.status not in {
                DemandReviewStatus.OPEN,
                DemandReviewStatus.READY_TO_DERIVE,
            }:
                raise ConflictError(
                    "demand review cannot be voided in its current state",
                    code="REVIEW_STATE_CONFLICT",
                    details={
                        "conflict_object": "demand_review",
                        "actual_status": review.status.value,
                        "retryable": False,
                    },
                )

            before_summary = self._review_summary(review)
            review.status = DemandReviewStatus.VOIDED
            review.version += 1
            session.flush()

            event = self.repository.append_event(
                session,
                actor.tenant_id,
                review_id=review.id,
                data={
                    "event_type": DemandReviewEventType.VOIDED,
                    "command_type": DemandReviewCommandType.VOID,
                    "actor_user_id": actor.user_id,
                    "actor_roles_json": [actor.role.value],
                    "request_id": actor.request_id,
                    "idempotency_key": clean_key,
                    "request_hash": request_hash,
                    "before_summary_json": before_summary,
                    "after_summary_json": self._review_summary(review),
                },
            )
            response = self._read_model(
                session,
                actor,
                review,
            )
            public_response = self._public_read(
                session,
                actor,
                review,
            )
            event.response_snapshot_json = self._response_envelope(
                response,
                public_response,
            )
            session.flush()
            session.commit()
            return response
        except IntegrityError as exc:
            session.rollback()
            winner = self.repository.find_command_event(
                session,
                actor.tenant_id,
                command_type=DemandReviewCommandType.VOID,
                idempotency_key=clean_key,
            )
            if winner is None:
                raise exc
            return self._replay(winner, request_hash)
        except Exception:
            session.rollback()
            raise

    def derive(
        self,
        session: Session,
        actor: ActorContext,
        review_id: int,
        *,
        expected_review_version: int,
        idempotency_key: str,
    ) -> DemandReviewDeriveRead:
        require_role(actor, MaintenanceRole.ADMIN)
        clean_key = self._normalize_idempotency_key(idempotency_key)
        if expected_review_version < 1:
            raise BusinessValidationError(
                "expected review version is invalid",
                code="REVIEW_VERSION_INVALID",
            )
        request_hash = self._derive_request_hash(
            review_id=review_id,
            expected_review_version=expected_review_version,
        )
        existing = self.repository.find_command_event(
            session,
            actor.tenant_id,
            command_type=DemandReviewCommandType.DERIVE,
            idempotency_key=clean_key,
        )
        if existing is not None:
            return self._derive_replay(existing, request_hash)

        try:
            with session.begin_nested():
                review = self.repository.get_for_update(
                    session,
                    actor.tenant_id,
                    review_id,
                )
                if review is None:
                    raise NotFoundError("demand_review", review_id)
                self._require_review_version(
                    review,
                    expected_review_version,
                )
                if review.status is not DemandReviewStatus.READY_TO_DERIVE:
                    raise ConflictError(
                        "demand review is not ready to derive",
                        code="REVIEW_STATE_CONFLICT",
                        details={
                            "conflict_object": "demand_review",
                            "actual_status": review.status.value,
                            "retryable": False,
                        },
                    )
                if review.pending_blocking_finding_count != 0:
                    raise ConflictError(
                        "demand review has unresolved findings",
                        code="REVIEW_FINDINGS_UNRESOLVED",
                        details={
                            "review_id": review.id,
                            "pending_blocking_finding_count": (
                                review.pending_blocking_finding_count
                            ),
                            "conflict_object": "demand_review",
                            "retryable": False,
                        },
                    )

                source = self.demand_list_repository.get_for_update(
                    session,
                    actor.tenant_id,
                    review.source_demand_list_id,
                )
                if source is None:
                    raise NotFoundError(
                        "demand_list",
                        review.source_demand_list_id,
                    )
                self._require_derivation_source(review, source)

                current_findings = self.repository.list_findings(
                    session,
                    actor.tenant_id,
                    review.id,
                )
                finding_ids = tuple(
                    sorted(finding.id for finding in current_findings)
                )
                findings = (
                    self.repository.findings_for_update(
                        session,
                        actor.tenant_id,
                        review.id,
                        finding_ids=finding_ids,
                    )
                    if finding_ids
                    else []
                )
                if any(
                    finding.blocking
                    and finding.decision_status
                    is DemandReviewDecisionStatus.PENDING
                    for finding in findings
                ):
                    raise ConflictError(
                        "demand review has unresolved findings",
                        code="REVIEW_FINDINGS_UNRESOLVED",
                        details={
                            "review_id": review.id,
                            "conflict_object": "demand_review",
                            "retryable": False,
                        },
                    )

                overrides = self._derive_item_overrides(
                    session,
                    review,
                    findings,
                )
                before_summary = {
                    **self._review_summary(review),
                    "derived_demand_list_id": (
                        review.derived_demand_list_id
                    ),
                }
                derived, _ = (
                    self.demand_list_service
                    .create_derived_draft_in_transaction(
                        session,
                        actor,
                        review.source_demand_list_id,
                        expected_source_version=(
                            review.source_demand_list_version
                        ),
                        require_current=True,
                        item_overrides=overrides,
                        derivation_context={
                            "origin": "formal_review",
                            "review_id": review.id,
                        },
                    )
                )

                review.status = DemandReviewStatus.DERIVED
                review.derived_demand_list_id = derived.id
                review.version += 1
                session.flush()

                after_summary = {
                    **self._review_summary(review),
                    "derived_demand_list_id": derived.id,
                }
                event = self.repository.append_event(
                    session,
                    actor.tenant_id,
                    review_id=review.id,
                    data={
                        "event_type": DemandReviewEventType.DERIVED,
                        "command_type": DemandReviewCommandType.DERIVE,
                        "actor_user_id": actor.user_id,
                        "actor_roles_json": [actor.role.value],
                        "request_id": actor.request_id,
                        "idempotency_key": clean_key,
                        "request_hash": request_hash,
                        "before_summary_json": before_summary,
                        "after_summary_json": after_summary,
                    },
                )
                response = DemandReviewDeriveRead(
                    review=self._read_model(
                        session,
                        actor,
                        review,
                    ),
                    derived_demand_list=(
                        self.demand_list_service.get(
                            session,
                            actor,
                            derived.id,
                        )
                    ),
                )
                public_response = self._public_read(
                    session,
                    actor,
                    review,
                )
                event.response_snapshot_json = self._response_envelope(
                    response,
                    public_response,
                )
                session.flush()

            session.commit()
            return response
        except IntegrityError as exc:
            winner = self.repository.find_command_event(
                session,
                actor.tenant_id,
                command_type=DemandReviewCommandType.DERIVE,
                idempotency_key=clean_key,
            )
            if winner is None:
                raise exc
            return self._derive_replay(winner, request_hash)

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

        source = self.demand_list_repository.get_for_update(
            session,
            actor.tenant_id,
            demand_list_id,
        )
        if source is None:
            session.rollback()
            raise NotFoundError(
                "demand_list",
                demand_list_id,
            )
        try:
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
        except Exception:
            session.rollback()
            raise

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
                    session.flush()

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
            public_response = self._public_read(
                session,
                actor,
                review,
            )
            final_event.response_snapshot_json = self._response_envelope(
                response,
                public_response,
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
