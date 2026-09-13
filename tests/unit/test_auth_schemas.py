"""Unit tests for app.schemas.auth registration/login schemas — pure validation, no DB."""
import pytest
from pydantic import ValidationError

from app.schemas.auth import CustomerRegisterRequest, LoginRequest, TechnicianRegisterRequest

VALID_CUSTOMER_PAYLOAD = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+14155550123",
    "password": "Str0ng!Pass",
}

VALID_TECHNICIAN_PAYLOAD = {
    **VALID_CUSTOMER_PAYLOAD,
    "skills": ["electrical", "plumbing"],
    "is_available": True,
}


# --- CustomerRegisterRequest ---


def test_valid_customer_payload_parses():
    req = CustomerRegisterRequest(**VALID_CUSTOMER_PAYLOAD)
    assert req.email == "jane@example.com"


def test_customer_request_has_no_role_field():
    """The endpoint this backs is customer-only — there is nothing to override."""
    assert "role" not in CustomerRegisterRequest.model_fields
    assert "approval_status" not in CustomerRegisterRequest.model_fields


def test_customer_name_is_stripped():
    req = CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "name": "  Jane Doe  "})
    assert req.name == "Jane Doe"


def test_customer_name_too_short_rejected():
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "name": "J"})


def test_customer_invalid_email_rejected():
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "email": "not-an-email"})


@pytest.mark.parametrize(
    "phone",
    ["not-a-phone", "12345", "+0123456789", "abc1234567"],
)
def test_customer_invalid_phone_rejected(phone):
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "phone": phone})


@pytest.mark.parametrize(
    "password",
    [
        "short1!",  # too short
        "alllowercase1!",  # no uppercase
        "ALLUPPERCASE1!",  # no lowercase
        "NoDigitsHere!",  # no digit
        "NoSpecialChar1",  # no special character
    ],
)
def test_customer_weak_password_rejected(password):
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "password": password})


def test_customer_strong_password_accepted():
    req = CustomerRegisterRequest(**{**VALID_CUSTOMER_PAYLOAD, "password": "Str0ng!Pass123"})
    assert req.password == "Str0ng!Pass123"


# --- TechnicianRegisterRequest ---


def test_valid_technician_payload_parses():
    req = TechnicianRegisterRequest(**VALID_TECHNICIAN_PAYLOAD)
    assert req.skills == ["electrical", "plumbing"]
    assert req.is_available is True


def test_technician_request_has_no_approval_field():
    """A technician can never self-approve through this schema."""
    assert "approval_status" not in TechnicianRegisterRequest.model_fields
    assert "role" not in TechnicianRegisterRequest.model_fields


def test_technician_skills_default_to_empty_list():
    payload = {k: v for k, v in VALID_TECHNICIAN_PAYLOAD.items() if k not in ("skills", "is_available")}
    req = TechnicianRegisterRequest(**payload)
    assert req.skills == []
    assert req.is_available is False


def test_technician_skills_are_stripped_and_blanks_dropped():
    req = TechnicianRegisterRequest(**{**VALID_TECHNICIAN_PAYLOAD, "skills": ["  hvac ", "", "  "]})
    assert req.skills == ["hvac"]


def test_technician_too_many_skills_rejected():
    with pytest.raises(ValidationError):
        TechnicianRegisterRequest(**{**VALID_TECHNICIAN_PAYLOAD, "skills": [f"skill-{i}" for i in range(51)]})


def test_technician_skill_too_long_rejected():
    with pytest.raises(ValidationError):
        TechnicianRegisterRequest(**{**VALID_TECHNICIAN_PAYLOAD, "skills": ["x" * 101]})


def test_technician_invalid_email_rejected():
    with pytest.raises(ValidationError):
        TechnicianRegisterRequest(**{**VALID_TECHNICIAN_PAYLOAD, "email": "not-an-email"})


def test_technician_weak_password_rejected():
    with pytest.raises(ValidationError):
        TechnicianRegisterRequest(**{**VALID_TECHNICIAN_PAYLOAD, "password": "weak"})


# --- LoginRequest ---


def test_valid_login_payload_parses():
    req = LoginRequest(email="jane@example.com", password="anything")
    assert req.email == "jane@example.com"


def test_login_invalid_email_rejected():
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="anything")
