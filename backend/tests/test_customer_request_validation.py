import pytest
from pydantic import ValidationError

from app.schemas.customer_request import CustomerRequestPayload, Location


def test_valid_text_request():
    payload = CustomerRequestPayload(
        text_input="My sink is leaking",
        location=Location(latitude=40.7128, longitude=-74.0060)
    )
    assert payload.text_input == "My sink is leaking"
    assert payload.audio_url is None
    assert payload.location.latitude == 40.7128
    assert payload.location.longitude == -74.0060


def test_valid_audio_request():
    payload = CustomerRequestPayload(
        audio_url="https://example.com/audio/request123.mp3",
        location=Location(latitude=34.0522, longitude=-118.2437, address="123 Main St")
    )
    assert payload.text_input is None
    assert str(payload.audio_url) == "https://example.com/audio/request123.mp3"
    assert payload.location.address == "123 Main St"


def test_missing_text_and_audio_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerRequestPayload(location=Location(latitude=0, longitude=0))
    
    assert "Either text_input or audio_url must be provided" in str(exc_info.value)


def test_blank_text_input_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerRequestPayload(text_input="   ")
    
    assert "text_input must not be blank" in str(exc_info.value)


def test_invalid_audio_url_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerRequestPayload(audio_url="not-a-url")
    
    assert "Input should be a valid URL" in str(exc_info.value) or "validation error" in str(exc_info.value).lower()


def test_invalid_location_latitude_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerRequestPayload(
            text_input="Fix my AC",
            location={"latitude": 100.0, "longitude": 0.0}
        )
    
    assert "Input should be less than or equal to 90" in str(exc_info.value)


def test_invalid_location_longitude_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CustomerRequestPayload(
            text_input="Fix my AC",
            location={"latitude": 0.0, "longitude": -200.0}
        )
    
    assert "Input should be greater than or equal to -180" in str(exc_info.value)


def test_missing_location_allowed():
    payload = CustomerRequestPayload(text_input="I need a plumber")
    assert payload.text_input == "I need a plumber"
    assert payload.location is None
