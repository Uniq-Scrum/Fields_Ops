import pytest
from pydantic import ValidationError

from app.schemas.service_request import CustomerIntakeRequest


def test_valid_text_request():
    request = CustomerIntakeRequest(
        input_type="TEXT",
        request_text="My engine is making a weird noise."
    )
    assert request.request_text == "My engine is making a weird noise."


def test_empty_text_request_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerIntakeRequest(
            input_type="TEXT",
            request_text=""
        )
    assert "request_text must be provided and cannot be empty or whitespace-only" in str(exc_info.value)


def test_whitespace_only_text_request_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerIntakeRequest(
            input_type="TEXT",
            request_text="   \n \t  "
        )
    assert "request_text must be provided and cannot be empty or whitespace-only" in str(exc_info.value)


def test_missing_text_request_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerIntakeRequest(
            input_type="TEXT"
        )
    assert "request_text must be provided and cannot be empty or whitespace-only" in str(exc_info.value)


def test_default_input_type_missing_text_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerIntakeRequest()
    assert "request_text must be provided and cannot be empty or whitespace-only" in str(exc_info.value)


def test_valid_voice_request():
    request = CustomerIntakeRequest(
        input_type="VOICE",
        audio_ref="s3://bucket/audio.mp3"
    )
    assert request.audio_ref == "s3://bucket/audio.mp3"


def test_voice_request_with_whitespace_text_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerIntakeRequest(
            input_type="VOICE",
            audio_ref="s3://bucket/audio.mp3",
            request_text="   "
        )
    assert "request_text must not be empty or whitespace-only" in str(exc_info.value)

def test_missing_input_type_with_audio_ref_valid():
    request = CustomerIntakeRequest(
        audio_ref="s3://bucket/audio.mp3"
    )
    assert request.audio_ref == "s3://bucket/audio.mp3"
