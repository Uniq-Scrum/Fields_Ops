from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SERVICE_REQUEST_URL = "/api/service-requests"


def test_create_service_request_returns_acknowledgement() -> None:
    response = client.post(
        SERVICE_REQUEST_URL,
        json={"user_prompt": "The kitchen sink is leaking under the cabinet"},
    )

    assert response.status_code == 202
    body = response.json()
    assert UUID(body["job_id"])
    assert body["status"] == "received"
    assert body["message"] == "Your request was received."


def test_create_service_request_rejects_blank_description() -> None:
    response = client.post(SERVICE_REQUEST_URL, json={"user_prompt": "   "})

    assert response.status_code == 422
    assert "Describe the problem" in response.text


def test_create_service_request_rejects_description_over_limit() -> None:
    response = client.post(SERVICE_REQUEST_URL, json={"user_prompt": "a" * 1001})

    assert response.status_code == 422
