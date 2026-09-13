"""
Integration tests for the registration APIs:
  POST /api/v1/auth/register             (customer)
  POST /api/v1/auth/register/technician  (technician)

Runs against a real PostgreSQL database (see tests/conftest.py) — no
repository/session mocking — so unique-constraint enforcement, the
FieldOfficer foreign key, and trigger-maintained timestamps are exercised
for real.
"""
import uuid

from sqlalchemy import select

from app.core.security import verify_password
from app.models.field_officer import FieldOfficer
from app.models.user import ApprovalStatus, User, UserRole

CUSTOMER_REGISTER_URL = "/api/v1/auth/register"
TECHNICIAN_REGISTER_URL = "/api/v1/auth/register/technician"


def _customer_payload(**overrides) -> dict:
    unique = uuid.uuid4().hex[:10]
    digits = str(uuid.uuid4().int)[:7]
    base = {
        "name": "Jane Doe",
        "email": f"jane.{unique}@example.com",
        "phone": f"+1415{digits}",
        "password": "Str0ng!Pass1",
    }
    base.update(overrides)
    return base


def _technician_payload(**overrides) -> dict:
    unique = uuid.uuid4().hex[:10]
    digits = str(uuid.uuid4().int)[:7]
    base = {
        "name": "Tom Tech",
        "email": f"tom.{unique}@example.com",
        "phone": f"+1415{digits}",
        "password": "Str0ng!Pass1",
        "skills": ["electrical", "plumbing"],
        "is_available": True,
    }
    base.update(overrides)
    return base


# --- Customer registration ---


def test_register_customer_success_and_auto_approved(client, db_session):
    resp = client.post(CUSTOMER_REGISTER_URL, json=_customer_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "CUSTOMER"
    assert body["approval_status"] == "APPROVED"
    assert "password" not in body
    assert "password_hash" not in body

    user = db_session.execute(
        select(User).where(User.email == body["email"])
    ).scalar_one()
    assert user.approval_status == ApprovalStatus.APPROVED
    assert user.role == UserRole.CUSTOMER


def test_register_customer_client_supplied_approval_status_is_ignored(client):
    payload = _customer_payload()
    payload["approval_status"] = "REJECTED"

    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    assert resp.json()["approval_status"] == "APPROVED"


def test_register_customer_client_supplied_role_field_is_ignored(client, db_session):
    """Even if a client sends role=ADMIN in the body, the customer endpoint
    always creates a CUSTOMER — there is no field on the schema for a
    client to change this."""
    payload = _customer_payload()
    payload["role"] = "ADMIN"

    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    assert resp.json()["role"] == "CUSTOMER"

    user = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalar_one()
    assert user.role == UserRole.CUSTOMER


def test_duplicate_email_rejected_with_conflict(client, db_session):
    payload = _customer_payload()
    first = client.post(CUSTOMER_REGISTER_URL, json=payload)
    assert first.status_code == 201

    duplicate = dict(payload)
    duplicate["phone"] = _customer_payload()["phone"]
    second = client.post(CUSTOMER_REGISTER_URL, json=duplicate)

    assert second.status_code == 409
    assert "detail" in second.json()

    count = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalars().all()
    assert len(count) == 1


def test_duplicate_phone_rejected_with_conflict(client, db_session):
    payload = _customer_payload()
    first = client.post(CUSTOMER_REGISTER_URL, json=payload)
    assert first.status_code == 201

    duplicate = _customer_payload(phone=payload["phone"])
    second = client.post(CUSTOMER_REGISTER_URL, json=duplicate)

    assert second.status_code == 409

    count = db_session.execute(
        select(User).where(User.phone == payload["phone"])
    ).scalars().all()
    assert len(count) == 1


def test_missing_required_field_rejected_with_422(client):
    payload = _customer_payload()
    del payload["password"]

    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)

    assert resp.status_code == 422


def test_password_is_hashed_not_plaintext_in_database(client, db_session):
    payload = _customer_payload()
    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)
    assert resp.status_code == 201

    user = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalar_one()

    assert user.password_hash != payload["password"]
    assert user.password_hash.startswith("$2b$")
    assert verify_password(payload["password"], user.password_hash) is True
    assert verify_password("wrong-password", user.password_hash) is False


def test_created_and_updated_timestamps_present_on_creation(client, db_session):
    payload = _customer_payload()
    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)
    assert resp.status_code == 201

    user = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalar_one()

    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.created_at == user.updated_at


def test_updated_at_changes_on_update(client, db_session):
    payload = _customer_payload()
    resp = client.post(CUSTOMER_REGISTER_URL, json=payload)
    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["id"])

    user = db_session.get(User, user_id)
    original_updated_at = user.updated_at

    user.name = "Jane Updated"
    db_session.commit()
    db_session.refresh(user)

    assert user.updated_at > original_updated_at
    assert user.name == "Jane Updated"


# --- Technician registration ---


def test_register_technician_starts_pending_and_creates_field_officer(client, db_session):
    resp = client.post(TECHNICIAN_REGISTER_URL, json=_technician_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "TECHNICIAN"
    assert body["approval_status"] == "PENDING"
    assert body["skills"] == ["electrical", "plumbing"]
    assert body["is_available"] is True
    assert body["field_officer_approval_status"] == "PENDING"
    assert "password" not in body
    assert "password_hash" not in body

    user_id = uuid.UUID(body["id"])
    field_officer = db_session.execute(
        select(FieldOfficer).where(FieldOfficer.user_id == user_id)
    ).scalar_one()
    assert field_officer.skills == ["electrical", "plumbing"]
    assert field_officer.is_available is True
    assert field_officer.approval_status == ApprovalStatus.PENDING


def test_register_technician_defaults_skills_empty_and_unavailable(client, db_session):
    payload = _technician_payload()
    del payload["skills"]
    del payload["is_available"]

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["skills"] == []
    assert body["is_available"] is False


def test_technician_cannot_self_approve_user_level(client, db_session):
    payload = _technician_payload()
    payload["approval_status"] = "APPROVED"

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    assert resp.json()["approval_status"] == "PENDING"

    user_id = uuid.UUID(resp.json()["id"])
    user = db_session.get(User, user_id)
    assert user.approval_status == ApprovalStatus.PENDING


def test_technician_cannot_self_approve_field_officer_level(client, db_session):
    payload = _technician_payload()
    payload["field_officer_approval_status"] = "APPROVED"

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["id"])
    field_officer = db_session.execute(
        select(FieldOfficer).where(FieldOfficer.user_id == user_id)
    ).scalar_one()
    assert field_officer.approval_status == ApprovalStatus.PENDING


def test_technician_cannot_pick_own_role(client, db_session):
    payload = _technician_payload()
    payload["role"] = "ADMIN"

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["id"])
    user = db_session.get(User, user_id)
    assert user.role == UserRole.TECHNICIAN


def test_technician_duplicate_email_rejected_with_conflict(client, db_session):
    payload = _technician_payload()
    first = client.post(TECHNICIAN_REGISTER_URL, json=payload)
    assert first.status_code == 201

    duplicate = dict(payload)
    duplicate["phone"] = _technician_payload()["phone"]
    second = client.post(TECHNICIAN_REGISTER_URL, json=duplicate)

    assert second.status_code == 409

    users = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalars().all()
    assert len(users) == 1


def test_technician_registration_is_atomic_no_orphan_user_or_field_officer(client, db_session):
    """A duplicate technician registration must leave neither an orphan
    User nor an orphan FieldOfficer behind — the whole transaction rolls
    back together."""
    payload = _technician_payload()
    first = client.post(TECHNICIAN_REGISTER_URL, json=payload)
    assert first.status_code == 201
    first_user_id = uuid.UUID(first.json()["id"])

    duplicate = dict(payload)  # same email -> IntegrityError on the second insert
    duplicate["phone"] = _technician_payload()["phone"]
    second = client.post(TECHNICIAN_REGISTER_URL, json=duplicate)
    assert second.status_code == 409

    users = db_session.execute(
        select(User).where(User.email == payload["email"])
    ).scalars().all()
    assert len(users) == 1
    assert users[0].id == first_user_id

    field_officers = db_session.execute(
        select(FieldOfficer).where(FieldOfficer.user_id == first_user_id)
    ).scalars().all()
    assert len(field_officers) == 1


def test_technician_invalid_role_rejected_with_422(client):
    """The technician schema has no `role` field to submit an invalid
    enum value against, but an invalid `skills` type must still 422."""
    payload = _technician_payload()
    payload["skills"] = "not-a-list"

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 422


def test_technician_weak_password_rejected_with_422(client):
    payload = _technician_payload(password="weak")

    resp = client.post(TECHNICIAN_REGISTER_URL, json=payload)

    assert resp.status_code == 422


def test_deleting_user_cascades_to_field_officer(client, db_session):
    resp = client.post(TECHNICIAN_REGISTER_URL, json=_technician_payload())
    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["id"])

    field_officer = db_session.execute(
        select(FieldOfficer).where(FieldOfficer.user_id == user_id)
    ).scalar_one()
    field_officer_id = field_officer.id

    user = db_session.get(User, user_id)
    db_session.delete(user)
    db_session.commit()

    orphan = db_session.get(FieldOfficer, field_officer_id)
    assert orphan is None
