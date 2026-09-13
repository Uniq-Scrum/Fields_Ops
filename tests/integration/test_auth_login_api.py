"""
Integration tests for POST /api/v1/auth/login and GET /api/v1/auth/me
against a real PostgreSQL-backed user (see tests/conftest.py).
"""
import uuid
from datetime import timedelta

from app.core.security import create_access_token, decode_access_token
from app.models.user import ApprovalStatus, UserRole

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
REGISTER_URL = "/api/v1/auth/register"

PASSWORD = "Str0ng!Pass1"


def _register_customer(client, **overrides) -> dict:
    unique = uuid.uuid4().hex[:10]
    digits = str(uuid.uuid4().int)[:7]
    payload = {
        "name": "Jane Doe",
        "email": f"jane.{unique}@example.com",
        "phone": f"+1415{digits}",
        "password": PASSWORD,
    }
    payload.update(overrides)
    resp = client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 201, resp.text
    return {**payload, **resp.json()}


# --- Login ---


def test_login_success_returns_token(client):
    user = _register_customer(client)

    resp = client.post(LOGIN_URL, json={"email": user["email"], "password": PASSWORD})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["expires_in"] > 0


def test_login_token_identifies_correct_user_and_role(client):
    user = _register_customer(client)

    resp = client.post(LOGIN_URL, json={"email": user["email"], "password": PASSWORD})
    token = resp.json()["access_token"]

    payload = decode_access_token(token)
    assert payload["sub"] == user["id"]
    assert payload["role"] == "CUSTOMER"


def test_login_nonexistent_email_rejected_401(client):
    resp = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401


def test_login_wrong_password_rejected_401(client):
    user = _register_customer(client)
    resp = client.post(LOGIN_URL, json={"email": user["email"], "password": "WrongOne1!"})
    assert resp.status_code == 401


def test_login_rejected_account_gets_403(client, make_user, auth_headers):
    user = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.REJECTED, password=PASSWORD)

    resp = client.post(LOGIN_URL, json={"email": user.email, "password": PASSWORD})

    assert resp.status_code == 403


def test_login_pending_technician_can_still_log_in(client, make_user):
    """PENDING is not the same as REJECTED — a technician awaiting approval
    can still authenticate (e.g. to check their own status via /me)."""
    user = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.PENDING, password=PASSWORD)

    resp = client.post(LOGIN_URL, json={"email": user.email, "password": PASSWORD})

    assert resp.status_code == 200


def test_login_missing_fields_rejected_422(client):
    resp = client.post(LOGIN_URL, json={"email": "jane@example.com"})
    assert resp.status_code == 422


# --- GET /api/v1/auth/me ---


def test_me_with_valid_token_returns_profile(client):
    user = _register_customer(client)
    login_resp = client.post(LOGIN_URL, json={"email": user["email"], "password": PASSWORD})
    token = login_resp.json()["access_token"]

    resp = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]
    assert resp.json()["email"] == user["email"]


def test_me_without_token_rejected_401(client):
    resp = client.get(ME_URL)
    assert resp.status_code == 401


def test_me_with_malformed_token_rejected_401(client):
    resp = client.get(ME_URL, headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_me_with_expired_token_rejected_401(client):
    user = _register_customer(client)
    expired_token = create_access_token(
        subject=user["id"], role="CUSTOMER", expires_delta=timedelta(seconds=-1)
    )

    resp = client.get(ME_URL, headers={"Authorization": f"Bearer {expired_token}"})

    assert resp.status_code == 401


def test_me_with_token_for_deleted_user_rejected_401(client, db_session):
    user = _register_customer(client)
    token = create_access_token(subject=user["id"], role="CUSTOMER")

    from app.models.user import User

    db_obj = db_session.get(User, uuid.UUID(user["id"]))
    db_session.delete(db_obj)
    db_session.commit()

    resp = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_with_tampered_token_rejected_401(client):
    user = _register_customer(client)
    login_resp = client.post(LOGIN_URL, json={"email": user["email"], "password": PASSWORD})
    token = login_resp.json()["access_token"]
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")

    resp = client.get(ME_URL, headers={"Authorization": f"Bearer {tampered}"})

    assert resp.status_code == 401
