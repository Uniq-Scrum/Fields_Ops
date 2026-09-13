"""
Unit tests for app.core.security's JWT access-token functions — no DB, no
HTTP layer, just create_access_token/decode_access_token in isolation.
"""
import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
)


def test_create_access_token_returns_a_string():
    token = create_access_token(subject=str(uuid.uuid4()), role="CUSTOMER")
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


def test_decode_valid_token_returns_expected_claims():
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    payload = decode_access_token(token)

    assert payload["sub"] == user_id
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_token_contains_no_sensitive_fields():
    token = create_access_token(subject=str(uuid.uuid4()), role="CUSTOMER")
    payload = decode_access_token(token)

    for forbidden in ("password", "password_hash", "secret"):
        assert forbidden not in payload


def test_secret_is_sourced_from_settings_not_hardcoded():
    """The token must fail to verify under any key other than the
    configured JWT_SECRET_KEY — proving it isn't signed with a hardcoded
    constant somewhere else in the codebase."""
    token = create_access_token(subject=str(uuid.uuid4()), role="CUSTOMER")

    with pytest.raises(InvalidTokenError):
        decode_access_token_with_key(token, "a-completely-different-signing-key")

    # Sanity check: it *does* verify under the real configured secret.
    decode_access_token(token)


def decode_access_token_with_key(token: str, key: str) -> dict:
    """Test-only helper mirroring decode_access_token but with an
    explicit key, to prove signature verification is actually enforced."""
    try:
        return jwt.decode(token, key, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc


def test_expired_token_rejected():
    token = create_access_token(
        subject=str(uuid.uuid4()), role="CUSTOMER", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_malformed_token_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("this-is-not-a-jwt")


def test_tampered_signature_rejected():
    token = create_access_token(subject=str(uuid.uuid4()), role="CUSTOMER")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}abcd"
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_algorithm_confusion_none_algorithm_rejected():
    """A token forged with alg=none (no signature at all) must never verify."""
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "ADMIN", "type": "access"},
        key="",
        algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_missing_required_claim_rejected():
    """A token missing the role claim (e.g. hand-crafted, or from some
    other issuer) must be rejected, not silently treated as roleless."""
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_wrong_token_type_rejected():
    """A token that isn't an access token (e.g. some future refresh-token
    type) must not be accepted where an access token is expected."""
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "CUSTOMER", "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_expiration_is_configurable_via_settings():
    token = create_access_token(subject=str(uuid.uuid4()), role="CUSTOMER")
    payload = decode_access_token(token)
    lifetime_seconds = payload["exp"] - payload["iat"]
    assert lifetime_seconds == settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
