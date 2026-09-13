"""
Authentication request/response schemas.

`CustomerRegisterRequest` and `TechnicianRegisterRequest` are the entire
trust boundary for their respective registration endpoints: neither has a
`role` or `approval_status` field, so there is no way for a client to pick
their own role or mark themselves as already-approved/privileged. Which
role and approval state a new account gets is decided exclusively by
`app/services/user_service.py`, never by the request body.
"""
import re

import phonenumbers
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import ApprovalStatus
from app.schemas.user import UserResponse
from app.utils.constants import (
    MAX_SKILLS_PER_TECHNICIAN,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SKILL_MAX_LENGTH,
)

_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


class _ContactCredentialsMixin(BaseModel):
    """Name/email/phone/password fields and validation shared by every
    registration flow, regardless of the resulting role."""

    name: str
    email: EmailStr
    phone: str
    password: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 255):
            raise ValueError("name must be between 2 and 255 characters")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        v = v.strip()
        # No default region is assumed — a bare national number is
        # ambiguous across countries, so the leading "+<country code>" is
        # mandatory. phonenumbers then checks the number against that
        # region's actual numbering plan (length, valid prefixes), so
        # numbers from every supported region/country are validated
        # correctly rather than against one fixed length range.
        try:
            parsed = phonenumbers.parse(v, None)
        except phonenumbers.NumberParseException:
            raise ValueError(
                "phone must be in international format, e.g. +14155552671"
            )
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(
                "phone must be in international format, e.g. +14155552671"
            )
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not (PASSWORD_MIN_LENGTH <= len(v) <= PASSWORD_MAX_LENGTH):
            raise ValueError(
                f"password must be between {PASSWORD_MIN_LENGTH} and "
                f"{PASSWORD_MAX_LENGTH} characters"
            )
        if not _UPPER_RE.search(v):
            raise ValueError("password must contain at least one uppercase letter")
        if not _LOWER_RE.search(v):
            raise ValueError("password must contain at least one lowercase letter")
        if not _DIGIT_RE.search(v):
            raise ValueError("password must contain at least one digit")
        if not _SPECIAL_RE.search(v):
            raise ValueError("password must contain at least one special character")
        return v


class CustomerRegisterRequest(_ContactCredentialsMixin):
    """POST /api/v1/auth/register — always creates a CUSTOMER account.

    There is no `role` field: this endpoint is customer registration only,
    so there is nothing for a client to override to register as anything
    else. See `UserService.register_customer`.
    """


class TechnicianRegisterRequest(_ContactCredentialsMixin):
    """POST /api/v1/auth/register/technician — always creates a TECHNICIAN
    account pending admin approval.

    `skills`/`is_available` are the only technician-specific fields a
    client may set. There is deliberately no `approval_status` (or
    equivalent) field anywhere on this schema — every technician starts
    PENDING (`UserService.register_technician`); nothing here lets a client
    self-approve.
    """

    skills: list[str] = Field(default_factory=list)
    is_available: bool = False

    @field_validator("skills")
    @classmethod
    def _validate_skills(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_SKILLS_PER_TECHNICIAN:
            raise ValueError(f"at most {MAX_SKILLS_PER_TECHNICIAN} skills are allowed")
        cleaned: list[str] = []
        for skill in v:
            skill = skill.strip()
            if not skill:
                continue
            if len(skill) > SKILL_MAX_LENGTH:
                raise ValueError(f"each skill must be at most {SKILL_MAX_LENGTH} characters")
            cleaned.append(skill)
        return cleaned


class TechnicianRegisterResponse(UserResponse):
    """Response for technician registration: the User fields plus the
    FieldOfficer profile created atomically alongside it in the same
    transaction (see `UserService.register_technician`)."""

    skills: list[str]
    is_available: bool
    field_officer_approval_status: ApprovalStatus


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login request body."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Successful authentication response.

    Contains only what a client needs to use the token — never a password,
    password hash, or other internal user/database detail.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
