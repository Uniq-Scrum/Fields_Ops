"""Unit tests for app.core.security — password hashing and verification."""
import pytest

from app.core.security import hash_password, needs_rehash, verify_password


def test_hash_password_returns_bcrypt_hash():
    hashed = hash_password("CorrectHorseBatteryStaple1!")
    assert hashed != "CorrectHorseBatteryStaple1!"
    assert hashed.startswith("$2b$")


def test_hash_password_is_salted_and_nondeterministic():
    h1 = hash_password("CorrectHorseBatteryStaple1!")
    h2 = hash_password("CorrectHorseBatteryStaple1!")
    assert h1 != h2


def test_verify_password_correct():
    hashed = hash_password("CorrectHorseBatteryStaple1!")
    assert verify_password("CorrectHorseBatteryStaple1!", hashed) is True


def test_verify_password_incorrect():
    hashed = hash_password("CorrectHorseBatteryStaple1!")
    assert verify_password("wrong-password", hashed) is False


@pytest.mark.parametrize(
    "malformed",
    ["", "not-a-bcrypt-hash", "$2b$12$tooshort"],
)
def test_verify_password_fails_closed_on_malformed_hash(malformed):
    """Verification must never raise on bad stored input — only return False."""
    assert verify_password("anything", malformed) is False


def test_needs_rehash_false_for_freshly_hashed_password():
    hashed = hash_password("CorrectHorseBatteryStaple1!")
    assert needs_rehash(hashed) is False
