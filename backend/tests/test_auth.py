# ── Auth Tests ────────────────────────────────────────────────────────────────
# Tests for registration, login, token refresh, and logout.
# Uses mocked DB sessions (matching the existing test_routers.py pattern)
# and calls router functions directly.

import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.routers.auth import login, logout, refresh, register
from app.schemas.auth import TokenResponse, UserLogin, UserRegister
from app.services.auth import DuplicateEmailError, InvalidCredentialsError

# ═══════════════════════════════════════════════════════════════════════════════
#  Registration Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_success(mock_db: AsyncMock):
    """Happy path: registering a new user returns a success message."""
    payload = UserRegister(
        email="new@example.com",
        password="Str0ng!Pass",
        full_name="New User",
    )

    # Mock register_user to succeed (no exception)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.routers.auth.register_user",
            AsyncMock(return_value=MagicMock()),
        )
        response = await register(data=payload, db=mock_db)

    assert response.message == "Registration successful. You may now log in."


@pytest.mark.asyncio
async def test_register_duplicate_email(mock_db: AsyncMock):
    """Duplicate email returns 409 Conflict."""
    payload = UserRegister(
        email="exists@example.com",
        password="Str0ng!Pass",
        full_name="Duplicate",
    )

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.routers.auth.register_user",
            AsyncMock(
                side_effect=DuplicateEmailError(
                    "A user with this email already exists."
                )
            ),
        )
        with pytest.raises(HTTPException) as exc:
            await register(data=payload, db=mock_db)

    assert exc.value.status_code == status.HTTP_409_CONFLICT


# ═══════════════════════════════════════════════════════════════════════════════
#  Login Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_login_success(mock_db: AsyncMock, sample_user):
    """Valid credentials return access + refresh tokens."""
    payload = UserLogin(email="test@example.com", password="Str0ng!Pass")

    # Mock the response to set cookies
    mock_response = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.routers.auth.authenticate_user",
            AsyncMock(return_value=sample_user),
        )
        m.setattr(
            "app.routers.auth.generate_tokens",
            lambda u: {
                "access_token": "access_mock",
                "refresh_token": "refresh_mock",
                "refresh_jti": "jti_mock",
                "refresh_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
            },
        )
        token_resp = await login(data=payload, response=mock_response, db=mock_db)

    assert token_resp.access_token == "access_mock"
    assert token_resp.token_type == "bearer"
    # Verify refresh cookie was set
    mock_response.set_cookie.assert_called_once()


@pytest.mark.asyncio
async def test_login_invalid_credentials(mock_db: AsyncMock):
    """Wrong password returns 401 Unauthorized."""
    payload = UserLogin(email="test@example.com", password="WrongPass1")

    mock_response = MagicMock()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.routers.auth.authenticate_user",
            AsyncMock(
                side_effect=InvalidCredentialsError("Invalid email or password.")
            ),
        )
        with pytest.raises(HTTPException) as exc:
            await login(data=payload, response=mock_response, db=mock_db)

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


# ═══════════════════════════════════════════════════════════════════════════════
#  Token Refresh Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_refresh_missing_cookie():
    """Refresh without a cookie returns 401."""
    with pytest.raises(HTTPException) as exc:
        await refresh(
            request=MagicMock(cookies={}), response=MagicMock(), db=AsyncMock()
        )

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


# ═══════════════════════════════════════════════════════════════════════════════
#  Logout Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_logout_clears_cookie(mock_db: AsyncMock):
    """Logout clears the refresh cookie and returns a success message."""
    mock_request = MagicMock()
    mock_request.cookies = {"refresh_token": "mock.header.sig"}

    mock_response = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.routers.auth.decode_token",
            lambda t: {"jti": "jti_mock", "exp": 1735689600},
        )
        m.setattr(
            "app.routers.auth.blacklist_token",
            AsyncMock(),
        )
        msg = await logout(request=mock_request, response=mock_response, db=mock_db)

    assert msg.message == "Logged out successfully."
    mock_response.delete_cookie.assert_called_once()
