"""
Security-focused tests: plaintext passwords must never reach the database
or an API response, under any registration or login path, and a JWT must
never carry a password/secret.
"""
import uuid

import jwt as pyjwt
from sqlalchemy import select, text

from app.core.config import settings
from app.core.security import verify_password
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
PLAINTEXT_PASSWORD = "Str0ng!Pass1"


def _payload(**overrides) -> dict:
    unique = uuid.uuid4().hex[:10]
    digits = str(uuid.uuid4().int)[:7]
    base = {
        "name": "Security Test",
        "email": f"sec.{unique}@example.com",
        "phone": f"+1415{digits}",
        "password": PLAINTEXT_PASSWORD,
    }
    base.update(overrides)
    return base


def test_plaintext_password_never_persisted(client, db_session):
    payload = _payload()
    resp = client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 201

    # Search every text-ish column on the row for the raw plaintext value —
    # not just password_hash — so a bug that logged/stored it anywhere on
    # the row would still be caught.
    row = db_session.execute(
        text("SELECT * FROM users WHERE email = :email"),
        {"email": payload["email"]},
    ).mappings().one()

    for column, value in row.items():
        assert value != PLAINTEXT_PASSWORD, f"plaintext password found in column {column!r}"


def test_registration_response_never_includes_password_fields(client):
    resp = client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 201
    body = resp.json()

    assert "password" not in body
    assert "password_hash" not in body
    assert PLAINTEXT_PASSWORD not in resp.text


def test_incorrect_password_does_not_authenticate(client, db_session):
    payload = _payload()
    resp = client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 201

    user = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalar_one()

    assert verify_password("DefinitelyWrongPassword1!", user.password_hash) is False


def test_login_with_wrong_password_returns_no_token(client):
    payload = _payload()
    assert client.post(REGISTER_URL, json=payload).status_code == 201

    resp = client.post(LOGIN_URL, json={"email": payload["email"], "password": "WrongPassword1!"})

    assert resp.status_code == 401
    assert "access_token" not in resp.json()


def test_login_error_does_not_reveal_whether_email_exists(client):
    payload = _payload()
    assert client.post(REGISTER_URL, json=payload).status_code == 201

    wrong_password_resp = client.post(
        LOGIN_URL, json={"email": payload["email"], "password": "WrongPassword1!"}
    )
    unknown_email_resp = client.post(
        LOGIN_URL, json={"email": "nobody-registered@example.com", "password": "WrongPassword1!"}
    )

    assert wrong_password_resp.status_code == unknown_email_resp.status_code == 401
    assert wrong_password_resp.json() == unknown_email_resp.json()


def test_successful_login_response_never_includes_password_fields(client):
    payload = _payload()
    assert client.post(REGISTER_URL, json=payload).status_code == 201

    resp = client.post(LOGIN_URL, json={"email": payload["email"], "password": payload["password"]})

    assert resp.status_code == 200
    body = resp.json()
    assert "password" not in body
    assert "password_hash" not in body
    assert PLAINTEXT_PASSWORD not in resp.text


def test_jwt_payload_never_contains_password_or_secret(client):
    payload = _payload()
    assert client.post(REGISTER_URL, json=payload).status_code == 201

    resp = client.post(LOGIN_URL, json={"email": payload["email"], "password": payload["password"]})
    token = resp.json()["access_token"]

    # Decode without verification just to inspect the claim set — this is a
    # test asserting what we chose to put IN the token, not a security check
    # of the token itself (which is covered in tests/unit/test_jwt.py).
    claims = pyjwt.decode(token, options={"verify_signature": False})

    serialized = str(claims).lower()
    assert "password" not in serialized
    assert PLAINTEXT_PASSWORD.lower() not in serialized
    assert settings.JWT_SECRET_KEY.lower() not in serialized


def test_auth_error_responses_never_leak_internal_details(client):
    resp = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "whatever1A!"})

    body_text = resp.text.lower()
    assert "traceback" not in body_text
    assert settings.JWT_SECRET_KEY.lower() not in body_text
    assert "psycopg2" not in body_text
    assert "sqlalchemy" not in body_text
