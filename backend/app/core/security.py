"""
Security primitives: password hashing and JWT access tokens.

Single approved entry point for turning a plaintext password into a stored
hash, and for checking a plaintext password against one. Nothing else in
the codebase should hash or compare passwords directly — route through
`hash_password` / `verify_password` so the algorithm and its configuration
stay centralized and auditable in one place.

Uses bcrypt (via passlib's CryptContext) rather than a hand-rolled scheme:
bcrypt is a deliberately slow, salted, adaptive hash designed for password
storage — never use a fast general-purpose hash (MD5/SHA family) for this.

`deprecated="auto"` lets a future scheme be added to `schemes` ahead of
bcrypt without invalidating existing hashes: passlib verifies with whichever
scheme produced the stored hash and flags it as needing a rehash, without
this module having to track hash formats itself.

Also the single approved entry point for issuing/validating JWT access
tokens (`create_access_token` / `decode_access_token`) — see that section
below for details.
"""
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage. Never persist the plaintext itself."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Check a plaintext password against a stored hash.

    Returns False on any mismatch, including a malformed/corrupt stored hash
    — verification must fail closed, never raise, for arbitrary stored input.
    """
    try:
        return _pwd_context.verify(plain_password, password_hash)
    except (ValueError, TypeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if a stored hash should be recomputed (e.g. after a cost-factor bump)."""
    return _pwd_context.needs_update(password_hash)


# =============================================================================
# JWT access tokens
#
# Single approved entry point for issuing and validating access tokens —
# nothing else in the codebase should call `jwt.encode`/`jwt.decode`
# directly, so the algorithm, claim set, and error handling stay
# centralized here.
#
# The token payload intentionally carries only non-sensitive identity
# claims (subject, role, issued-at, expiry) — never a password, password
# hash, or anything else that would matter if the token were intercepted.
# Authorization decisions still re-load the user from the database (see
# app/api/deps.py) rather than trusting the embedded `role` claim as the
# final word — the claim is informational, not authoritative.
# =============================================================================

ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """Base class for all JWT validation failures."""


class TokenExpiredError(TokenError):
    """The token's `exp` claim is in the past."""


class InvalidTokenError(TokenError):
    """The token is malformed, has a bad signature, uses an unexpected
    algorithm, is missing a required claim, or is not an access token."""


def create_access_token(*, subject: str, role: str, expires_delta: timedelta | None = None) -> str:
    """
    Issue a signed JWT access token.

    `subject` is the user's id (as a string) and `role` their UserRole
    value at the moment of issuance — both non-sensitive identifiers, never
    a password or anything else that would matter if leaked.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": subject,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Validate and decode a JWT access token.

    `algorithms=[settings.JWT_ALGORITHM]` is passed explicitly (never derived
    from the token's own header) — this is what actually prevents an
    algorithm-confusion attack (e.g. a token claiming `alg=none`, or one
    signed with an unexpected key type): PyJWT only accepts a token whose
    header algorithm is in this caller-supplied allow-list.

    Raises TokenExpiredError / InvalidTokenError; never lets a raw
    `jwt.PyJWTError` (or its message, which can include internal parsing
    detail) escape to a caller.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError()

    return payload
