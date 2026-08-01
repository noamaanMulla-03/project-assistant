# ── User & Token Models ───────────────────────────────────────────────────────
# SQLAlchemy ORM models for user accounts and refresh-token blacklist.

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """Application user account."""

    __tablename__ = "users"

    # ── Columns ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})>"


class TokenBlacklist(Base):
    """Stores revoked JWT refresh tokens so they cannot be reused.

    A scheduled cleanup job (or periodic task) should purge rows where
    ``expires_at < now()``.
    """

    __tablename__ = "token_blacklist"

    # ── Columns ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    jti: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="JWT ID (jti claim) — UUID4 string",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the original token would have expired — safe to purge after",
    )

    def __repr__(self) -> str:
        return f"<TokenBlacklist(jti={self.jti!r}, expires_at={self.expires_at})>"
