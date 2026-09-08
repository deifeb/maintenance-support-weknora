from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.models.enums import AIConfirmationStatus
from app.repositories.ai_execution_repository import (
    AIExecutionRepository,
    ai_execution_repository,
    canonical_digest,
)
from app.security.actor import ActorContext


class AIConfirmationService:
    def __init__(
        self,
        *,
        repository: AIExecutionRepository | None = None,
    ) -> None:
        self.repository = (
            repository or ai_execution_repository
        )

    def create(
        self,
        session: Session,
        actor: ActorContext,
        *,
        session_id: int,
        operation_name: str,
        confirmation_level: str,
        input_payload: dict,
        risk_level: str,
        data_externalization: bool = False,
        plan_step_id: int | None = None,
    ):
        token = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(
                seconds=(
                    get_settings()
                    .ai_confirmation_ttl_seconds
                )
            )
        )
        try:
            row = self.repository.create_confirmation(
                session,
                actor.tenant_id,
                session_id=session_id,
                plan_step_id=plan_step_id,
                operation_name=operation_name,
                confirmation_level=confirmation_level,
                input_preview=input_payload,
                input_digest=canonical_digest(
                    input_payload
                ),
                confirmation_token_hash=(
                    hashlib.sha256(
                        token.encode()
                    ).hexdigest()
                ),
                risk_level=risk_level,
                data_externalization=(
                    data_externalization
                ),
                expires_at=expires_at,
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc
        session.commit()
        session.refresh(row)
        return row, token

    def latest_pending(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
    ):
        try:
            rows = (
                self.repository
                .list_pending_confirmations(
                    session,
                    actor.tenant_id,
                    session_id,
                )
            )
        except LookupError as exc:
            raise NotFoundError(
                "ai_session",
                session_id,
            ) from exc
        return rows[-1] if rows else None

    def approve(
        self,
        session: Session,
        actor: ActorContext,
        confirmation_id: int,
        *,
        token: str,
        expected_input_digest: str,
        comment: str | None = None,
    ):
        row = self.repository.get_confirmation(
            session,
            actor.tenant_id,
            confirmation_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_confirmation",
                confirmation_id,
            )
        if (
            row.status
            is not AIConfirmationStatus.PENDING
        ):
            raise BusinessValidationError(
                "confirmation is not pending",
                code="CONFIRMATION_NOT_PENDING",
            )
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(
                    tzinfo=timezone.utc
                )
            if expires_at <= now:
                row.status = (
                    AIConfirmationStatus.EXPIRED
                )
                session.commit()
                raise BusinessValidationError(
                    "confirmation has expired",
                    code="CONFIRMATION_EXPIRED",
                )
        if row.input_digest != expected_input_digest:
            raise BusinessValidationError(
                "confirmation input changed",
                code="CONFIRMATION_INPUT_CHANGED",
            )
        token_hash = hashlib.sha256(
            token.encode()
        ).hexdigest()
        if token_hash != row.confirmation_token_hash:
            raise BusinessValidationError(
                "invalid confirmation token",
                code="CONFIRMATION_TOKEN_INVALID",
            )
        row.status = AIConfirmationStatus.APPROVED
        row.resolved_at = now
        row.resolved_by = actor.user_id
        row.comment = comment
        session.commit()
        session.refresh(row)
        return row

    def reject(
        self,
        session: Session,
        actor: ActorContext,
        confirmation_id: int,
        *,
        comment: str | None = None,
    ):
        row = self.repository.get_confirmation(
            session,
            actor.tenant_id,
            confirmation_id,
        )
        if row is None:
            raise NotFoundError(
                "ai_confirmation",
                confirmation_id,
            )
        if (
            row.status
            is not AIConfirmationStatus.PENDING
        ):
            raise BusinessValidationError(
                "confirmation is not pending",
                code="CONFIRMATION_NOT_PENDING",
            )
        row.status = AIConfirmationStatus.REJECTED
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = actor.user_id
        row.comment = comment
        session.commit()
        session.refresh(row)
        return row


ai_confirmation_service = AIConfirmationService()
