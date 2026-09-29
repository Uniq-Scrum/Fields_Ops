"""API tests for customer text repair-request intake."""
import os
from types import SimpleNamespace
from uuid import UUID
from uuid import uuid4

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-api-tests-32")

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.user import UserRole


def _customer():
    return SimpleNamespace(id=UUID("3d5d4a3a-4344-4b78-bdec-aeb185c7b893"), role=UserRole.CUSTOMER)


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, instance):
        self.added.append(instance)

    def flush(self):
        for instance in self.added:
            if instance.id is None:
                instance.id = uuid4()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_text_request_is_persisted_and_acknowledged():
    app.dependency_overrides[get_current_user] = _customer
    db = FakeSession()
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/api/v1/service-requests",
            json={"request_text": "  My kitchen sink is leaking.  "},
        )

        assert response.status_code == 201
        assert response.json() == {
            "request_id": str(db.added[0].id),
            "status": "received",
        }
        assert len(db.added) == 1
        assert db.added[0].request_text == "My kitchen sink is leaking."
        assert db.added[0].customer_id == UUID("3d5d4a3a-4344-4b78-bdec-aeb185c7b893")
        assert db.added[0].status == "RECEIVED"
        assert db.committed is True
    finally:
        app.dependency_overrides.clear()


def test_blank_text_request_is_rejected():
    app.dependency_overrides[get_current_user] = _customer
    db = FakeSession()
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/api/v1/service-requests", json={"request_text": "   "}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert db.added == []
    assert db.committed is False


def test_text_request_requires_customer_authentication():
    response = TestClient(app).post(
        "/api/v1/service-requests",
        json={"request_text": "My kitchen sink is leaking."},
    )

    assert response.status_code == 401
