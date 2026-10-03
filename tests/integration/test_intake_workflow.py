"""
Integration tests for STORY 4 — LangGraph Multi-Modal Intake Workflow.

Verifies:
- Task 4: Connect Text Input to LangGraph.
- Task 5: Connect Voice Input to LangGraph.
- Task 6: Intake state transitions and conditional routing.
- Task 7: Negative cases and invalid input error handling.
- Task 8: Checkpoint persistence and state recovery across workflow runs.
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.agents.graph.checkpoints import get_memory_checkpointer, recover_workflow_state
from app.agents.graph.state import InputType, IntakeStatus, VoiceProcessingStatus
from app.agents.graph.workflow import build_intake_workflow, run_intake_workflow
from app.integrations.whisper.client import (
    TranscriptionResult,
    WhisperTranscriptionError,
    get_whisper_client,
)
from app.main import app
from app.schemas.service_request import CustomerIntakeRequest
from app.services.booking_service import BookingService


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_whisper_client():
    client = get_whisper_client()
    yield client
    client.set_custom_transcriber(None)


def test_text_request_intake_workflow_success():
    """Task 4: Verify valid text request executes through LangGraph intake workflow."""
    job_id = str(uuid.uuid4())
    customer_id = str(uuid.uuid4())
    request_text = "Main electrical breaker tripped and smells like burning plastic."

    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.TEXT,
        request_text=request_text,
        customer_id=customer_id,
        customer_info={"name": "Danielle", "phone": "+14155553322"},
        metadata={"channel": "web_portal"},
    )

    # Acceptance criteria checks
    assert final_state["job_id"] == job_id
    assert final_state["customer_id"] == customer_id
    assert final_state["input_type"] == "TEXT"
    assert final_state["request_text"] == request_text
    assert final_state["user_prompt"] == request_text
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert len(final_state["errors"]) == 0


def test_voice_request_intake_workflow_success():
    """Task 5: Verify valid voice request executes through LangGraph with Whisper transcription."""
    job_id = str(uuid.uuid4())
    audio_ref = "https://s3.amazonaws.com/fieldmind/audio/kitchen_flooding.wav"

    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref=audio_ref,
        customer_id=str(uuid.uuid4()),
        metadata={"channel": "whatsapp"},
    )

    assert final_state["job_id"] == job_id
    assert final_state["input_type"] == "VOICE"
    assert final_state["audio_ref"] == audio_ref
    assert final_state["voice_state"] is not None
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.TRANSCRIBED.value
    assert final_state["voice_state"]["media_format"] == "wav"
    assert final_state["audio_transcript"] is not None
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert len(final_state["errors"]) == 0


def test_voice_request_with_custom_whisper_integration(reset_whisper_client):
    """Task 5: Verify Whisper handoff with custom transcript in intake workflow."""
    custom_transcript = "Emergency: Tree branch broke the main electrical line outside."
    reset_whisper_client.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text=custom_transcript,
            duration_seconds=5.5,
            language="en",
            confidence=0.97,
        )
    )

    job_id = str(uuid.uuid4())
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref="s3://bucket/audio/power_line.mp3",
    )

    assert final_state["audio_transcript"] == custom_transcript
    assert final_state["user_prompt"] == custom_transcript
    assert final_state["voice_state"]["duration_seconds"] == 5.5
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"


def test_invalid_text_short_length_rejected():
    """Task 7: Verify request text below minimum length is rejected."""
    job_id = str(uuid.uuid4())
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.TEXT,
        request_text="hi",
    )

    assert final_state["status"] == IntakeStatus.FAILED.value
    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert any("too short" in err for err in final_state["errors"])


def test_invalid_voice_format_rejected():
    """Task 7: Verify unsupported audio format fails validation and halts downstream AI."""
    job_id = str(uuid.uuid4())
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref="s3://bucket/audio/malicious_file.exe",
    )

    assert final_state["status"] == IntakeStatus.FAILED.value
    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert any("Unsupported audio format '.exe'" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED.value


def test_whisper_runtime_failure_captured():
    """Task 7: Verify Whisper transcription exceptions are caught without crashing workflow."""
    client = get_whisper_client()
    client.set_custom_transcriber(lambda ref: (_ for _ in ()).throw(WhisperTranscriptionError("Whisper server 503")))

    job_id = str(uuid.uuid4())
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref="audio/test.ogg",
    )

    assert final_state["status"] == IntakeStatus.FAILED.value
    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert any("Whisper server 503" in err for err in final_state["errors"])


def test_checkpoint_persistence_and_recovery_in_workflow():
    """Task 8: Verify workflow execution state is checkpointer-persisted and recoverable."""
    checkpointer = get_memory_checkpointer()
    job_id = str(uuid.uuid4())
    thread_id = f"job-{job_id}"

    # Run workflow with explicit checkpointer
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.TEXT,
        request_text="Bathroom water valve is jammed shut.",
        checkpointer=checkpointer,
    )

    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"

    # Recover state from checkpoint using thread_id
    recovered = recover_workflow_state(thread_id, checkpointer=checkpointer)
    assert recovered is not None
    assert recovered["job_id"] == job_id
    assert recovered["user_prompt"] == "Bathroom water valve is jammed shut."
    assert recovered["current_step"] == "READY_FOR_INTENT_EXTRACTION"


def test_booking_service_customer_intake_text():
    """Task 4: Verify BookingService domain handling for customer text intake."""
    job_id = str(uuid.uuid4())
    req = CustomerIntakeRequest(
        job_id=job_id,
        input_type="TEXT",
        request_text="Water heater leaking rusty water in basement.",
        customer_info={"name": "George"},
    )

    resp = BookingService.process_customer_intake(req)

    assert resp.job_id == job_id
    assert resp.input_type == "TEXT"
    assert resp.current_step == "READY_FOR_INTENT_EXTRACTION"
    assert resp.user_prompt == "Water heater leaking rusty water in basement."
    assert resp.errors == []


def test_api_customer_intake_endpoint_text(test_client):
    """Task 4: Verify HTTP POST /api/v1/requests/intake for text request."""
    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "input_type": "TEXT",
        "request_text": "Emergency: Gas leak odor detected near stove valve.",
        "customer_id": str(uuid.uuid4()),
        "metadata": {"source": "mobile_app"},
    }

    response = test_client.post("/api/v1/requests/intake", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == job_id
    assert data["input_type"] == "TEXT"
    assert data["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert data["user_prompt"] == payload["request_text"]
    assert data["errors"] == []


def test_api_customer_intake_endpoint_voice(test_client):
    """Task 5: Verify HTTP POST /api/v1/requests/intake for voice request."""
    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "input_type": "VOICE",
        "audio_ref": "https://s3.amazonaws.com/fieldmind/audio/broken_pipe.ogg",
        "customer_id": str(uuid.uuid4()),
    }

    response = test_client.post("/api/v1/requests/intake", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == job_id
    assert data["input_type"] == "VOICE"
    assert data["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert data["audio_transcript"] is not None
    assert data["voice_state"]["status"] == "TRANSCRIBED"
    assert data["errors"] == []


def test_api_customer_intake_endpoint_invalid_payload(test_client):
    """Task 7: Verify HTTP POST /api/v1/requests/intake returns 422 on invalid schema."""
    response = test_client.post("/api/v1/requests/intake", json={"input_type": 12345})
    assert response.status_code == 422
