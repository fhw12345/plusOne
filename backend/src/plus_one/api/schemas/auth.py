"""Auth request/response schemas (batch-2m).

All ``extra="forbid"`` so unknown keys surface as validation errors
rather than getting silently dropped.
"""

from __future__ import annotations

import re
from uuid import UUID  # noqa: TC003 — used at runtime as Pydantic field type

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")


def _normalize_email(value: str) -> str:
    """Lowercased, syntactically-valid email — ``test_environment=True``
    so reserved TLDs (``.test``) accepted (e2e parity)."""
    try:
        result = validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized.lower()


def _validate_password_strength(value: str) -> str:
    """PRD §6 register rules: len >= 10, at least one letter + one digit."""
    if len(value) < 10:  # noqa: PLR2004
        raise ValueError("password too short")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("password needs a letter")
    if not re.search(r"\d", value):
        raise ValueError("password needs a digit")
    return value


class RegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32)
    email: str
    password: str = Field(min_length=10, max_length=200)

    @field_validator("username", mode="before")
    @classmethod
    def _vu(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("username must be a string")
        lo = v.strip().lower()
        if not _USERNAME_RE.match(lo):
            raise ValueError("invalid username")
        return lo

    @field_validator("email", mode="before")
    @classmethod
    def _ve(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("email must be a string")
        return _normalize_email(v)

    @field_validator("password", mode="after")
    @classmethod
    def _vp(cls, v: str) -> str:
        return _validate_password_strength(v)


class VerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    code: str = Field(min_length=4, max_length=12)

    @field_validator("email", mode="before")
    @classmethod
    def _ve(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("email must be a string")
        return _normalize_email(v)


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class RequestCodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str

    @field_validator("email", mode="before")
    @classmethod
    def _ve(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("email must be a string")
        return _normalize_email(v)


class LoginWithCodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    code: str = Field(min_length=4, max_length=12)

    @field_validator("email", mode="before")
    @classmethod
    def _ve(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("email must be a string")
        return _normalize_email(v)


class UserPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: str
    username: str
    is_admin: bool


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 standard label, not a secret
    expires_in_minutes: int
    user: UserPayload


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    email: str


class UserMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: str
    username: str
    is_admin: bool
