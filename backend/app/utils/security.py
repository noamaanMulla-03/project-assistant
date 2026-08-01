# ── Security Utilities ────────────────────────────────────────────────────────
# Password hashing (bcrypt via passlib) and JWT creation / validation (python-jose).

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password Hashing ──────────────────────────────────────────────────────────
# passlib CryptContext handles bcrypt rounds and automatic scheme upgrades.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if *plain_password* matches *hashed_password*."""
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT ───────────────────────────────────────────────────────────────────────


def _create_token(user_id: str, jti: str, expires_delta: timedelta) -> str:
    """Internal helper: create a JWT with standard claims."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # Subject — user UUID
        "jti": jti,  # JWT ID — unique per token (for blacklisting)
        "iat": now,  # Issued at
        "exp": now + expires_delta,  # Expiration
        "type": "access" if expires_delta.total_seconds() < 3600 else "refresh",
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_access_token(user_id: str) -> tuple[str, str]:
    """Create a short-lived access token.

    Returns:
        (encoded_token, jti) — the jti allows the caller to track the token.
    """
    jti = uuid.uuid4().hex
    token = _create_token(
        user_id=user_id,
        jti=jti,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return token, jti


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """Create a long-lived refresh token.

    Returns:
        (encoded_token, jti, expires_at) — expires_at is used for blacklist expiry.
    """
    jti = uuid.uuid4().hex
    delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expires_at = datetime.now(UTC) + delta
    token = _create_token(user_id=user_id, jti=jti, expires_delta=delta)
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises ``JWTError`` on any failure."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "jti", "exp", "type"]},
    )
