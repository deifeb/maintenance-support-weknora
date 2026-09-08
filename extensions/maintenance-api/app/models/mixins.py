from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantScopedMixin:
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )


class VersionedMixin:
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ActiveMixin:
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
