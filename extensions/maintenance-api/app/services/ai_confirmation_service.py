import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError, NotFoundError
from app.models import AIConfirmationRequest
from app.models.enums import AIConfirmationLevel, AIConfirmationStatus
from app.repositories.ai_execution_repository import canonical_digest


class AIConfirmationService:
    def create(
        self,
        session: Session,
        *,
        session_id: int,
        operation_name: str,
        confirmation_level: str,
        input_payload: dict,
        risk_level: str,
        data_externalization: bool = False,
    ):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=get_settings().ai_confirmation_ttl_seconds
        )
        row = AIConfirmationRequest(
            session_id=session_id,
            operation_name=operation_name,
            confirmation_level=AIConfirmationLevel(confirmation_level),
            status=AIConfirmationStatus.PENDING,
            input_preview_json=input_payload,
            input_digest=canonical_digest(input_payload),
            confirmation_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            risk_level=risk_level,
            data_externalization=data_externalization,
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row, token

    def approve(
        self,
        session: Session,
        confirmation_id: int,
        *,
        token: str,
        expected_input_digest: str,
        resolved_by: str | None = None,
        comment: str | None = None,
    ):
        row = session.get(AIConfirmationRequest, confirmation_id)
        if row is None:
            raise NotFoundError("ai_confirmation", confirmation_id)
        if row.status is not AIConfirmationStatus.PENDING:
            raise BusinessValidationError(
                "confirmation is not pending",
                code="CONFIRMATION_NOT_PENDING",
            )
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                row.status = AIConfirmationStatus.EXPIRED
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
        if hashlib.sha256(token.encode()).hexdigest() != row.confirmation_token_hash:
            raise BusinessValidationError(
                "invalid confirmation token",
                code="CONFIRMATION_TOKEN_INVALID",
            )
        row.status = AIConfirmationStatus.APPROVED
        row.resolved_at = now
        row.resolved_by = resolved_by
        row.comment = comment
        session.commit()
        session.refresh(row)
        return row

    def reject(
        self,
        session: Session,
        confirmation_id: int,
        *,
        resolved_by: str | None = None,
        comment: str | None = None,
    ):
        row = session.get(AIConfirmationRequest, confirmation_id)
        if row is None:
            raise NotFoundError("ai_confirmation", confirmation_id)
        if row.status is not AIConfirmationStatus.PENDING:
            raise BusinessValidationError(
                "confirmation is not pending",
                code="CONFIRMATION_NOT_PENDING",
            )
        row.status = AIConfirmationStatus.REJECTED
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = resolved_by
        row.comment = comment
        session.commit()
        session.refresh(row)
        return row


ai_confirmation_service = AIConfirmationService()
