# ── Auth Schemas ──────────────────────────────────────────────────────────────
# Pydantic models for request validation and response serialisation.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# ── Request Schemas ───────────────────────────────────────────────────────────


class UserRegister(BaseModel):
    """Payload for ``POST /auth/register``."""

    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password — minimum 8 characters",
    )
    full_name: str = Field(
        min_length=1,
        max_length=200,
        description="User's full name",
    )

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: str) -> str:
        """Enforce a basic strength policy: at least one digit or special char."""
        if v.isalpha() or v.isalnum() and v.islower():
            raise ValueError(
                "Password must contain at least one digit or special character"
            )
        return v


class UserLogin(BaseModel):
    """Payload for ``POST /auth/login``."""

    email: EmailStr
    password: str


# ── Response Schemas ──────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Returned after a successful login or token refresh."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user profile returned by ``GET /auth/me``."""

    id: UUID
    email: str
    full_name: str
    created_at: datetime

    model_config = {"from_attributes": True}  # Enable ORM-mode hydration


class MessageResponse(BaseModel):
    """Generic success / info message."""

    message: str
