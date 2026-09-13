"""
Shared pytest fixtures for the auth/user-management test suite.

Integration/security tests run against a real PostgreSQL database (the one
`docker compose up -d postgres` provides, with Alembic migrations already
applied — see docs/DATABASE.md) rather than mocks: each test runs inside its
own outer transaction + SAVEPOINT, so calls to `Session.commit()` inside the
application code (e.g. `UserService.register_user`) only release the
savepoint, and the final rollback discards everything the test wrote,
leaving the database clean for the next test and for manual use afterward.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import ApprovalStatus, User, UserRole

DEFAULT_TEST_PASSWORD = "Str0ng!Pass1"


@pytest.fixture()
def db_session():
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the transactional `db_session`.

    Deliberately not used as a context manager (`with TestClient(app)`):
    that would run the app's lifespan (`app/main.py`), which blocks on
    Redis/Kafka startup retries that are irrelevant to these tests and slow
    to fail in an environment without those services running.
    """
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def make_user(db_session):
    """
    Factory fixture for creating a User directly via the ORM (bypassing the
    HTTP registration API), for tests that need a role no public endpoint
    can produce — e.g. ADMIN, which has no self-registration path by
    design (see app/schemas/auth.py) — or a specific approval_status.

    Returns a callable: make_user(role=..., approval_status=..., password=...) -> User
    """

    def _make_user(
        role: UserRole = UserRole.CUSTOMER,
        approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
        password: str = DEFAULT_TEST_PASSWORD,
        **overrides,
    ) -> User:
        unique = uuid.uuid4().hex[:10]
        digits = str(uuid.uuid4().int)[:7]
        user = User(
            name=overrides.pop("name", "Test User"),
            email=overrides.pop("email", f"user.{unique}@example.com"),
            phone=overrides.pop("phone", f"+1415{digits}"),
            password_hash=hash_password(password),
            role=role,
            approval_status=approval_status,
            **overrides,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture()
def auth_headers(client):
    """
    Factory fixture: auth_headers(email, password) -> logs in via the real
    POST /api/v1/auth/login endpoint and returns an Authorization header
    dict, so RBAC tests exercise genuine end-to-end token issuance and
    validation rather than fabricating a token by hand.
    """

    def _auth_headers(email: str, password: str = DEFAULT_TEST_PASSWORD) -> dict:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
