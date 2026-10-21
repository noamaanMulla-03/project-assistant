# ── Auth Service ──────────────────────────────────────────────────────────────
# Business logic for registration, login, token refresh, and logout.
# Kept separate from the router so it can be tested independently.

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.auth import UserRegister
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


class AuthError(Exception):
    """Base exception for auth-related errors."""


class DuplicateEmailError(AuthError):
    """Raised when trying to register an email that already exists."""


class InvalidCredentialsError(AuthError):
    """Raised when login email/password don't match."""


# ── Registration ──────────────────────────────────────────────────────────────


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    """Create a new user account.

    Raises:
        DuplicateEmailError: If *data.email* is already registered.
    """
    # Check for duplicate email (case-insensitive via DB collation)
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise DuplicateEmailError("A user with this email already exists.")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    await db.flush()  # Populate user.id without committing the transaction
    return user


# ── Login ─────────────────────────────────────────────────────────────────────


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Validate credentials and return the user.

    Raises:
        InvalidCredentialsError: On any mismatch (same error for both bad email
            and bad password — avoids user enumeration).
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("Invalid email or password.")

    return user


def generate_tokens(user: User) -> dict:
    """Return access token + refresh token info for *user*."""
    access_token, _ = create_access_token(str(user.id))
    refresh_token, refresh_jti, refresh_expires = create_refresh_token(str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "refresh_jti": refresh_jti,
        "refresh_expires_at": refresh_expires,
    }


# ── Token Blacklist ───────────────────────────────────────────────────────────


async def blacklist_token(db: AsyncSession, jti: str, expires_at: datetime) -> bool:
    """Atomically revoke a token; return False if it was already revoked."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            "INSERT INTO token_blacklist (id, jti, expires_at) "
            "VALUES (gen_random_uuid(), :jti, :expires_at) "
            "ON CONFLICT (jti) DO NOTHING RETURNING id"
        ),
        {"jti": jti, "expires_at": expires_at},
    )
    return result.scalar_one_or_none() is not None
