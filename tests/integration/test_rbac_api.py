"""
Integration tests for role-based access control across the three
RBAC-gated example endpoints:

  GET /api/v1/users/me                    any authenticated role
  GET /api/v1/technicians/me               TECHNICIAN only
  GET /api/v1/admin/technicians/pending    ADMIN only

Users are created directly via the `make_user` ORM factory fixture (not
through the public registration API) so ADMIN — which has no public
self-registration path by design — can be tested too. Tokens are obtained
through the real POST /api/v1/auth/login endpoint via `auth_headers`, so
these are genuine end-to-end authorization checks, not fabricated tokens.
"""
from app.models.user import ApprovalStatus, UserRole

USERS_ME_URL = "/api/v1/users/me"
TECHNICIANS_ME_URL = "/api/v1/technicians/me"
ADMIN_PENDING_URL = "/api/v1/admin/technicians/pending"


# --- Missing / invalid authentication -> 401 on every protected route ---


def test_users_me_without_token_401(client):
    assert client.get(USERS_ME_URL).status_code == 401


def test_technicians_me_without_token_401(client):
    assert client.get(TECHNICIANS_ME_URL).status_code == 401


def test_admin_pending_without_token_401(client):
    assert client.get(ADMIN_PENDING_URL).status_code == 401


def test_admin_pending_with_invalid_token_401(client):
    resp = client.get(ADMIN_PENDING_URL, headers={"Authorization": "Bearer garbage.token.value"})
    assert resp.status_code == 401


# --- GET /api/v1/users/me — any authenticated role ---


def test_users_me_accessible_by_customer(make_user, auth_headers, client):
    user = make_user(role=UserRole.CUSTOMER, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(USERS_ME_URL, headers=auth_headers(user.email))
    assert resp.status_code == 200
    assert resp.json()["role"] == "CUSTOMER"


def test_users_me_accessible_by_technician(make_user, auth_headers, client):
    user = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.PENDING)
    resp = client.get(USERS_ME_URL, headers=auth_headers(user.email))
    assert resp.status_code == 200
    assert resp.json()["role"] == "TECHNICIAN"


def test_users_me_accessible_by_admin(make_user, auth_headers, client):
    user = make_user(role=UserRole.ADMIN, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(USERS_ME_URL, headers=auth_headers(user.email))
    assert resp.status_code == 200
    assert resp.json()["role"] == "ADMIN"


# --- GET /api/v1/technicians/me — TECHNICIAN only ---


def test_technicians_me_accessible_by_technician(make_user, auth_headers, client, db_session):
    from app.models.field_officer import FieldOfficer

    user = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.PENDING)
    db_session.add(FieldOfficer(user_id=user.id, skills=["hvac"], is_available=False))
    db_session.commit()

    resp = client.get(TECHNICIANS_ME_URL, headers=auth_headers(user.email))

    assert resp.status_code == 200
    assert resp.json()["skills"] == ["hvac"]


def test_technicians_me_rejected_for_customer_403(make_user, auth_headers, client):
    user = make_user(role=UserRole.CUSTOMER, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(TECHNICIANS_ME_URL, headers=auth_headers(user.email))
    assert resp.status_code == 403


def test_technicians_me_rejected_for_admin_403(make_user, auth_headers, client):
    user = make_user(role=UserRole.ADMIN, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(TECHNICIANS_ME_URL, headers=auth_headers(user.email))
    assert resp.status_code == 403


# --- GET /api/v1/admin/technicians/pending — ADMIN only ---


def test_admin_pending_accessible_by_admin(make_user, auth_headers, client, db_session):
    from app.models.field_officer import FieldOfficer

    admin = make_user(role=UserRole.ADMIN, approval_status=ApprovalStatus.APPROVED)
    tech = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.PENDING)
    db_session.add(
        FieldOfficer(user_id=tech.id, skills=["welding"], approval_status=ApprovalStatus.PENDING)
    )
    db_session.commit()

    resp = client.get(ADMIN_PENDING_URL, headers=auth_headers(admin.email))

    assert resp.status_code == 200
    ids = [row["user_id"] for row in resp.json()]
    assert str(tech.id) in ids


def test_admin_pending_rejected_for_customer_403(make_user, auth_headers, client):
    user = make_user(role=UserRole.CUSTOMER, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(ADMIN_PENDING_URL, headers=auth_headers(user.email))
    assert resp.status_code == 403


def test_admin_pending_rejected_for_technician_403(make_user, auth_headers, client):
    user = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.APPROVED)
    resp = client.get(ADMIN_PENDING_URL, headers=auth_headers(user.email))
    assert resp.status_code == 403


def test_admin_pending_excludes_approved_technicians(make_user, auth_headers, client, db_session):
    from app.models.field_officer import FieldOfficer

    admin = make_user(role=UserRole.ADMIN, approval_status=ApprovalStatus.APPROVED)
    approved_tech = make_user(role=UserRole.TECHNICIAN, approval_status=ApprovalStatus.APPROVED)
    db_session.add(
        FieldOfficer(
            user_id=approved_tech.id, skills=["carpentry"], approval_status=ApprovalStatus.APPROVED
        )
    )
    db_session.commit()

    resp = client.get(ADMIN_PENDING_URL, headers=auth_headers(admin.email))

    assert resp.status_code == 200
    ids = [row["user_id"] for row in resp.json()]
    assert str(approved_tech.id) not in ids
