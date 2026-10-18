"""
Integration tests for the LangGraph Voice Intake Workflow.

Verifies acceptance criteria:
1. Valid voice request enters the intake workflow.
2. Job ID is available in the workflow state.
3. Audio/media reference is available to the workflow.
4. Voice processing state is created.
5. Audio can proceed to Whisper transcription.
6. Workflow failures are captured appropriately.
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.agents.graph.state import VoiceProcessingStatus
from app.agents.graph.workflow import run_voice_intake_workflow
from app.agents.intake.voice import initialize_voice_intake, transcribe_voice
from app.integrations.whisper.client import (
    TranscriptionResult,
    WhisperClient,
    WhisperTranscriptionError,
    get_whisper_client,
)
from app.main import app
from app.schemas.service_request import VoiceIntakeRequest
from app.services.booking_service import BookingService


@pytest.fixture
def test_client():
    """FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_whisper_client():
    """Ensure global whisper client custom transcriber is cleared after each test."""
    client = get_whisper_client()
    yield client
    client.set_custom_transcriber(None)


def test_valid_voice_request_full_workflow():
    """
    Test that a valid voice request enters the intake workflow, establishes
    the voice processing state, proceeds to Whisper transcription, and hands off
    to downstream intent diagnostics.
    """
    job_id = f"job-{uuid.uuid4()}"
    media_ref = "https://s3.amazonaws.com/fieldmind/audio/pipe_burst_urgent.ogg"
    customer_id = str(uuid.uuid4())

    final_state = run_voice_intake_workflow(
        job_id=job_id,
        media_ref=media_ref,
        customer_id=customer_id,
        metadata={"channel": "whatsapp", "locale": "en-US"},
    )

    # 1. Job ID available in workflow state
    assert final_state["job_id"] == job_id
    assert final_state["customer_id"] == customer_id

    # 2. Audio/media reference available to workflow
    assert final_state["media_ref"] == media_ref
    assert final_state["audio_url"] == media_ref

    # 3. Voice processing state created and completed
    voice_state = final_state.get("voice_state")
    assert voice_state is not None
    assert voice_state["status"] == VoiceProcessingStatus.TRANSCRIBED
    assert voice_state["media_ref"] == media_ref
    assert voice_state["media_format"] == "ogg"
    assert voice_state["duration_seconds"] == 4.5
    assert voice_state["word_confidence"] == 0.98

    # 4. Audio proceeded to Whisper transcription
    assert final_state["audio_transcript"] is not None
    assert "pipe burst" in final_state["audio_transcript"].lower()
    assert final_state["user_prompt"] == final_state["audio_transcript"]

    # 5. Intent handoff reached without failures
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert len(final_state.get("errors", [])) == 0


def test_voice_request_with_custom_whisper_transcriber(reset_whisper_client):
    """
    Test custom transcription handoff through WhisperClient into workflow state.
    """
    custom_text = "Urgent: Air conditioner unit is leaking water into the circuit breaker."
    reset_whisper_client.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text=custom_text,
            duration_seconds=7.2,
            language="en",
            confidence=0.99,
        )
    )

    job_id = str(uuid.uuid4())
    final_state = run_voice_intake_workflow(
        job_id=job_id,
        media_ref="s3://fieldmind-bucket/audio/ac_leak.mp3",
    )

    assert final_state["job_id"] == job_id
    assert final_state["audio_transcript"] == custom_text
    assert final_state["voice_state"]["transcription"] == custom_text
    assert final_state["voice_state"]["duration_seconds"] == 7.2
    assert final_state["voice_state"]["word_confidence"] == 0.99
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"


def test_workflow_failure_captured_for_missing_job_id():
    """
    Test that a voice request with a missing or empty Job ID is rejected and
    captured in workflow failure state.
    """
    final_state = run_voice_intake_workflow(
        job_id="",
        media_ref="audio/recording.wav",
    )

    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert len(final_state["errors"]) >= 1
    assert any("Job ID is missing" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED


def test_workflow_failure_captured_for_missing_media_ref():
    """
    Test that a voice request with an empty audio/media reference is rejected
    and captured in workflow failure state.
    """
    job_id = str(uuid.uuid4())
    final_state = run_voice_intake_workflow(
        job_id=job_id,
        media_ref="",
    )

    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert len(final_state["errors"]) >= 1
    assert any("Audio/media reference is missing" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED


def test_workflow_failure_captured_for_unsupported_audio_format():
    """
    Test that an unsupported audio format (e.g. .pdf or .txt) fails validation
    and is gracefully recorded in state without crashing the agent.
    """
    job_id = str(uuid.uuid4())
    final_state = run_voice_intake_workflow(
        job_id=job_id,
        media_ref="documents/invoice.pdf",
    )

    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert len(final_state["errors"]) >= 1
    assert any("Unsupported audio format '.pdf'" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED


def test_workflow_failure_captured_when_whisper_fails(reset_whisper_client):
    """
    Test that runtime Whisper transcription exceptions (e.g. network/model error)
    are captured appropriately in workflow state.
    """
    def broken_transcriber(ref: str):
        raise WhisperTranscriptionError("OpenAI Whisper API timeout")

    reset_whisper_client.set_custom_transcriber(broken_transcriber)

    job_id = str(uuid.uuid4())
    final_state = run_voice_intake_workflow(
        job_id=job_id,
        media_ref="audio/circuit_breaker.wav",
    )

    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert len(final_state["errors"]) >= 1
    assert any("OpenAI Whisper API timeout" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED
    assert "OpenAI Whisper API timeout" in final_state["voice_state"]["error_message"]


def test_booking_service_voice_intake_integration():
    """
    Test BookingService domain integration for voice intake.
    """
    job_id = str(uuid.uuid4())
    request = VoiceIntakeRequest(
        job_id=job_id,
        media_ref="https://storage.googleapis.com/audio/kitchen_sink.m4a",
        customer_id=str(uuid.uuid4()),
        metadata={"priority": "high"},
    )

    response = BookingService.process_voice_intake(request)

    assert response.job_id == job_id
    assert response.current_step == "READY_FOR_INTENT_EXTRACTION"
    assert response.audio_transcript is not None
    assert response.voice_state is not None
    assert response.voice_state.status == "TRANSCRIBED"
    assert response.voice_state.media_format == "m4a"
    assert len(response.errors) == 0


def test_api_voice_intake_endpoint_success(test_client):
    """
    Test HTTP POST /api/v1/requests/voice-intake successfully triggers the workflow.
    """
    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "media_ref": "https://s3.amazonaws.com/fieldmind/audio/sink_leak.ogg",
        "customer_id": str(uuid.uuid4()),
        "metadata": {"source": "mobile_app"},
    }

    response = test_client.post("/api/v1/requests/voice-intake", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == job_id
    assert data["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert data["audio_transcript"] is not None
    assert data["voice_state"]["status"] == "TRANSCRIBED"
    assert data["voice_state"]["media_format"] == "ogg"
    assert data["errors"] == []


def test_api_voice_intake_endpoint_invalid_payload(test_client):
    """
    Test HTTP POST /api/v1/requests/voice-intake returns 422 for missing media_ref.
    """
    response = test_client.post("/api/v1/requests/voice-intake", json={"job_id": "123"})
    assert response.status_code == 422
