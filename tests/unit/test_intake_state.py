"""
Unit tests for STORY 4 — LangGraph Intake State.

Verifies:
- Task 1: State schema definition and type consistency.
- Task 2: Initial state creation, defaults, and customer context preservation.
- Task 3: Request data mapping and safe state updates without unintentional overwrites.
- Task 7: Handling of invalid state/input (empty text, missing audio, unknown input types).
- Task 8: Checkpoint integration, state recovery, and safe failure handling.
"""
import uuid
import pytest

from app.agents.graph.checkpoints import (
    PostgresCheckpointerConfig,
    get_checkpointer,
    get_memory_checkpointer,
    recover_workflow_state,
)
from app.agents.graph.state import (
    CustomerInfo,
    FieldMindWorkflowState,
    InputType,
    IntakeStatus,
    VoiceProcessingStatus,
    create_initial_intake_state,
    update_intake_state,
)


def test_intake_state_schema_types():
    """Task 1: Verify state schema type definitions and required attributes."""
    state: FieldMindWorkflowState = {
        "job_id": "test-job-123",
        "customer_id": "cust-456",
        "customer_info": {"name": "Alice Smith", "phone": "+14155550199"},
        "input_type": InputType.TEXT,
        "request_text": "Sink leaking water",
        "user_prompt": "Sink leaking water",
        "audio_ref": None,
        "media_ref": None,
        "audio_url": None,
        "audio_transcript": None,
        "voice_state": None,
        "current_step": "START",
        "status": IntakeStatus.INITIALIZED,
        "errors": [],
        "metadata": {"source": "web"},
    }

    assert state["job_id"] == "test-job-123"
    assert state["input_type"] == InputType.TEXT
    assert state["status"] == IntakeStatus.INITIALIZED
    assert state["customer_info"]["name"] == "Alice Smith"


def test_create_initial_intake_state_for_text():
    """Task 2: Verify initial state creation for a valid text request."""
    job_id = str(uuid.uuid4())
    customer_id = str(uuid.uuid4())
    customer_info = {"name": "Bob Jones", "phone": "+14155551234", "email": "bob@example.com"}

    state = create_initial_intake_state(
        job_id=job_id,
        input_type=InputType.TEXT,
        request_text="Ceiling fan is sparking when turned on",
        customer_id=customer_id,
        customer_info=customer_info,
        metadata={"priority": "high"},
    )

    assert state["job_id"] == job_id
    assert state["customer_id"] == customer_id
    assert state["customer_info"]["name"] == customer_info["name"]
    assert state["customer_info"]["phone"] == customer_info["phone"]
    assert state["customer_info"]["email"] == customer_info["email"]
    assert state["customer_info"]["customer_id"] == customer_id
    assert state["input_type"] == "TEXT"
    assert state["request_text"] == "Ceiling fan is sparking when turned on"
    assert state["user_prompt"] == "Ceiling fan is sparking when turned on"
    assert state["status"] == IntakeStatus.INITIALIZED.value
    assert state["current_step"] == "INTAKE_INITIALIZED"
    assert state["errors"] == []
    assert state["metadata"]["priority"] == "high"


def test_create_initial_intake_state_auto_detect_voice():
    """Task 2: Verify auto-detection of VOICE input type when audio_ref is provided."""
    state = create_initial_intake_state(
        audio_ref="s3://bucket/audio/leaking_roof.ogg",
    )

    assert state["job_id"] is not None
    assert state["input_type"] == "VOICE"
    assert state["audio_ref"] == "s3://bucket/audio/leaking_roof.ogg"
    assert state["status"] == IntakeStatus.INITIALIZED.value
    assert state["errors"] == []


def test_create_initial_intake_state_auto_detect_text():
    """Task 2: Verify auto-detection of TEXT input type when text is provided."""
    state = create_initial_intake_state(
        request_text="Kitchen pipe burst under sink",
    )

    assert state["job_id"] is not None
    assert state["input_type"] == "TEXT"
    assert state["request_text"] == "Kitchen pipe burst under sink"
    assert state["status"] == IntakeStatus.INITIALIZED.value
    assert state["errors"] == []


def test_update_intake_state_preserves_existing_data():
    """Task 3: Verify update_intake_state safely merges data without unintentional overwrite."""
    initial_state = create_initial_intake_state(
        job_id="job-999",
        input_type=InputType.TEXT,
        request_text="AC not cooling",
        customer_id="cust-111",
        customer_info={"name": "Carol", "phone": "+14155559876"},
        metadata={"region": "west"},
    )

    # Apply partial update
    updated_state = update_intake_state(
        initial_state,
        {
            "current_step": "PROCESSING_DIAGNOSTICS",
            "metadata": {"assigned_queue": "tier_1"},
            "user_prompt": "Normalized: AC unit not cooling airflow",
        },
    )

    # Verify original fields were preserved
    assert updated_state["job_id"] == "job-999"
    assert updated_state["customer_id"] == "cust-111"
    assert updated_state["customer_info"]["name"] == "Carol"
    assert updated_state["request_text"] == "AC not cooling"

    # Verify updated fields and deep-merged metadata
    assert updated_state["current_step"] == "PROCESSING_DIAGNOSTICS"
    assert updated_state["user_prompt"] == "Normalized: AC unit not cooling airflow"
    assert updated_state["metadata"]["region"] == "west"
    assert updated_state["metadata"]["assigned_queue"] == "tier_1"


def test_update_intake_state_accumulates_errors():
    """Task 3: Verify error messages accumulate rather than overwriting existing errors."""
    initial_state = create_initial_intake_state(
        job_id="job-err",
        input_type=InputType.TEXT,
        request_text="Valid request",
    )
    initial_state["errors"] = ["Initial warning"]

    updated = update_intake_state(
        initial_state,
        {"errors": ["Secondary failure"]},
    )

    assert "Initial warning" in updated["errors"]
    assert "Secondary failure" in updated["errors"]
    assert len(updated["errors"]) == 2


def test_invalid_input_type_rejected():
    """Task 7: Verify unrecognized input_type is rejected with error in state."""
    state = create_initial_intake_state(
        input_type="VIDEO",
        request_text="Video stream input",
    )

    assert state["status"] == IntakeStatus.FAILED.value
    assert state["current_step"] == "INTAKE_FAILED"
    assert any("Invalid input_type" in err for err in state["errors"])


def test_empty_text_request_handled():
    """Task 7: Verify empty or whitespace-only text request is captured in error state."""
    state = create_initial_intake_state(
        input_type=InputType.TEXT,
        request_text="   ",
    )

    assert state["status"] == IntakeStatus.FAILED.value
    assert state["current_step"] == "INTAKE_FAILED"
    assert any("Request text is empty" in err for err in state["errors"])


def test_missing_audio_ref_for_voice_handled():
    """Task 7: Verify missing audio reference for voice request is captured in error state."""
    state = create_initial_intake_state(
        input_type=InputType.VOICE,
        audio_ref="",
    )

    assert state["status"] == IntakeStatus.FAILED.value
    assert state["current_step"] == "INTAKE_FAILED"
    assert any("Audio reference is missing" in err for err in state["errors"])


def test_checkpoint_recovery_with_memory_saver():
    """Task 8: Verify checkpoint state association and recovery by thread ID."""
    from app.agents.graph.workflow import run_intake_workflow

    saver = get_memory_checkpointer()
    job_id = "recovery-test-01"
    thread_id = f"job-{job_id}"

    # Execute workflow with checkpointer
    state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.TEXT,
        request_text="Electrical fuse blown in kitchen",
        checkpointer=saver,
    )
    assert state["current_step"] == "READY_FOR_INTENT_EXTRACTION"

    # Recover state by thread ID
    recovered = recover_workflow_state(thread_id, checkpointer=saver)
    assert recovered is not None
    assert recovered["job_id"] == job_id
    assert recovered["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert recovered["status"] == IntakeStatus.READY_FOR_DIAGNOSTICS.value
    assert recovered["request_text"] == "Electrical fuse blown in kitchen"


def test_checkpoint_recovery_nonexistent_thread():
    """Task 8: Verify graceful None return for nonexistent checkpoint thread."""
    saver = get_memory_checkpointer()
    recovered = recover_workflow_state("job-does-not-exist", checkpointer=saver)
    assert recovered is None


def test_postgres_checkpoint_config():
    """Task 8: Verify PostgreSQL checkpoint configuration structure."""
    config = PostgresCheckpointerConfig()
    info = config.get_connection_info()
    assert "host" in info
    assert "port" in info
    assert "database" in info
    assert info["database"] == "fieldmind"
