# ── Auth Router ───────────────────────────────────────────────────────────────
# Endpoints: register, login, refresh, logout, me.
#
# Cookie strategy:
#   - ``refresh_token`` — httpOnly, Secure, SameSite=strict cookie (path=/auth)
#     Used to obtain new access tokens silently.
#   - ``access_token`` — returned in response body.  The client stores it in
#     memory and attaches it via ``Authorization: Bearer <token>`` header.

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    MessageResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth import (
    DuplicateEmailError,
    InvalidCredentialsError,
    authenticate_user,
    blacklist_token,
    generate_tokens,
    is_token_blacklisted,
    register_user,
)
from app.utils.security import decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Cookie helpers ────────────────────────────────────────────────────────────
_REFRESH_COOKIE_KEY = "refresh_token"
_REFRESH_COOKIE_PATH = "/auth"
_REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach an httpOnly refresh-token cookie to the response."""
    response.set_cookie(
        key=_REFRESH_COOKIE_KEY,
        value=token,
        httponly=True,
        secure=True,  # Set False if testing over plain HTTP locally
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        max_age=_REFRESH_COOKIE_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh-token cookie (used on logout)."""
    response.delete_cookie(
        key=_REFRESH_COOKIE_KEY,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /auth/register
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Create a new account.  Returns a success message on completion."""
    try:
        await register_user(db, data)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return MessageResponse(message="Registration successful. You may now log in.")


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /auth/login
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive tokens",
)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password.

    Returns an access token in the body and sets the refresh token as an
    httpOnly cookie.
    """
    try:
        user = await authenticate_user(db, data.email, data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = generate_tokens(user)
    _set_refresh_cookie(response, tokens["refresh_token"])
    return TokenResponse(access_token=tokens["access_token"])


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /auth/refresh
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh an expired access token",
)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh-token cookie for a new pair of tokens.

    The old refresh token is rotated (blacklisted) so it cannot be reused.
    """
    # Read the httpOnly refresh-token cookie from the request
    token = request.cookies.get(_REFRESH_COOKIE_KEY)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing.",
        )

    # Decode and validate the token
    try:
        payload = decode_token(token)
    except JWTError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    jti: str | None = payload.get("jti")
    user_id: str | None = payload.get("sub")

    if jti is None or user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    # Reject if the token has been revoked (reuse detection)
    if await is_token_blacklisted(db, jti):
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.  Please log in again.",
        )

    # Blacklist the *old* refresh token (rotation)
    await blacklist_token(
        db,
        jti,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )

    # Fetch the user to ensure they still exist
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
        )

    # Issue fresh tokens
    tokens = generate_tokens(user)
    _set_refresh_cookie(response, tokens["refresh_token"])
    return TokenResponse(access_token=tokens["access_token"])


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /auth/logout
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and revoke the refresh token",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current refresh token and clear the cookie."""
    token = request.cookies.get(_REFRESH_COOKIE_KEY)
    if token is not None:
        try:
            payload = decode_token(token)
            jti = payload.get("jti")
            if jti is not None:
                # Only blacklist if not already revoked (avoids duplicate-key error
                # after refresh rotation or repeated logout attempts)
                if not await is_token_blacklisted(db, jti):
                    await blacklist_token(
                        db,
                        jti,
                        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                    )
        except JWTError:
            pass  # Token already invalid — nothing to revoke

    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully.")


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /auth/me
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user's profile",
)
async def me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
