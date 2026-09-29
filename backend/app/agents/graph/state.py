"""
State definitions and transition utilities for the FieldMind AI LangGraph multi-agent workflow.

Defines the central schema `FieldMindWorkflowState` managed by LangGraph,
persisted across checkpoints, and transitioned through the intake,
transcription, intent parsing, dispatch, and settlement pipeline.
"""
from enum import Enum
import operator
from typing import Annotated, Any, TypedDict
import uuid


class InputType(str, Enum):
    """Channel/modality through which the customer request was submitted."""
    TEXT = "TEXT"
    VOICE = "VOICE"


class IntakeStatus(str, Enum):
    """Lifecycle statuses for the LangGraph intake workflow."""
    PENDING = "PENDING"
    INITIALIZED = "INITIALIZED"
    PROCESSING = "PROCESSING"
    READY_FOR_DIAGNOSTICS = "READY_FOR_DIAGNOSTICS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VoiceProcessingStatus(str, Enum):
    """Lifecycle statuses for the voice intake and transcription stage."""
    PENDING = "PENDING"
    INITIALIZED = "INITIALIZED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    FAILED = "FAILED"


class CustomerInfo(TypedDict, total=False):
    """Customer profile details associated with the service request."""
    customer_id: str | None
    name: str | None
    phone: str | None
    email: str | None


class VoiceProcessingState(TypedDict, total=False):
    """
    Detailed sub-state tracking the audio ingestion and Whisper transcription.

    Holds the persisted media reference, audio format, transcription output,
    duration metrics, and error context if processing fails.
    """
    status: VoiceProcessingStatus | str
    media_ref: str
    media_format: str | None
    duration_seconds: float | None
    transcription: str | None
    word_confidence: float | None
    error_message: str | None


class FieldMindWorkflowState(TypedDict, total=False):
    """
    Central state container passed between LangGraph agent nodes.

    Attributes:
        job_id: Unique identifier for the service request / job (Required).
        customer_id: Unique UUID string of the customer if authenticated.
        customer_info: Normalized customer contact and identity record.
        input_type: Modality of incoming request (TEXT or VOICE).
        request_text: Raw incoming text query from the customer (for text intake).
        user_prompt: Synthesized or transcribed natural-language user query for downstream AI.
        audio_ref: Persisted media reference / storage key for audio notes.
        media_ref: Backward-compatible alias for audio_ref.
        audio_url: Direct accessible URL to the audio file if applicable.
        audio_transcript: Extracted raw transcript from Whisper.
        voice_state: Structured sub-state tracking voice processing and transcription.
        current_step: Current active stage in the multi-agent graph.
        status: High-level lifecycle status of the workflow intake.
        errors: Aggregated list of workflow failure messages.
        metadata: Extensible key-value metadata for tracing, tenancy, and telemetry.
    """
    job_id: str
    customer_id: str | None
    customer_info: CustomerInfo | dict[str, Any] | None
    input_type: InputType | str
    request_text: str | None
    user_prompt: str | None
    audio_ref: str | None
    media_ref: str | None
    audio_url: str | None
    audio_transcript: str | None
    voice_state: VoiceProcessingState | None
    current_step: str
    status: IntakeStatus | str
    errors: Annotated[list[str], operator.add]
    metadata: dict[str, Any]


def create_initial_intake_state(
    job_id: str | None = None,
    input_type: InputType | str | None = None,
    request_text: str | None = None,
    audio_ref: str | None = None,
    customer_id: str | None = None,
    customer_info: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> FieldMindWorkflowState:
    """
    Initialize a new graph state when a customer request enters LangGraph.

    Enforces validation:
    - Ensures job_id is available (generates UUID if None/empty).
    - Detects or validates input_type (TEXT vs VOICE).
    - Preserves customer information and request metadata.
    - Sets initial status to INITIALIZED.
    - Handles missing or invalid required data gracefully.

    Returns:
        A fully initialized FieldMindWorkflowState dictionary.
    """
    errors: list[str] = []

    # 1. Job / Request ID
    if job_id is not None and not str(job_id).strip():
        errors.append("Job ID is missing or invalid in workflow state.")
        assigned_job_id = ""
    else:
        assigned_job_id = str(job_id).strip() if job_id else str(uuid.uuid4())

    # 2. Normalize and identify input type
    normalized_input_type: InputType | None = None
    if input_type is not None:
        val = input_type.value if hasattr(input_type, "value") else str(input_type)
        raw_type = val.split(".")[-1].upper().strip()
        if raw_type in {InputType.TEXT.value, "TEXT"}:
            normalized_input_type = InputType.TEXT
        elif raw_type in {InputType.VOICE.value, "VOICE"}:
            normalized_input_type = InputType.VOICE
        else:
            errors.append(f"Invalid input_type '{input_type}'. Must be TEXT or VOICE.")
    else:
        # Auto-detect if not explicitly provided
        if audio_ref and str(audio_ref).strip():
            normalized_input_type = InputType.VOICE
        elif request_text and str(request_text).strip():
            normalized_input_type = InputType.TEXT
        else:
            errors.append("Could not determine input_type: neither valid text nor audio_ref provided.")

    # 3. Validate content availability based on input type
    clean_text = str(request_text).strip() if request_text else None
    clean_audio_ref = str(audio_ref).strip() if audio_ref else None

    if normalized_input_type == InputType.TEXT and not clean_text:
        errors.append("Request text is empty for TEXT input type.")
    elif normalized_input_type == InputType.VOICE and not clean_audio_ref:
        errors.append("Audio reference is missing (Audio/media reference is missing for VOICE input type).")

    # 4. Normalize customer info
    cust_id = customer_id or (customer_info.get("customer_id") if customer_info else None)
    cust_record: CustomerInfo = {
        "customer_id": cust_id,
        "name": customer_info.get("name") if customer_info else None,
        "phone": customer_info.get("phone") if customer_info else None,
        "email": customer_info.get("email") if customer_info else None,
    }

    initial_status = IntakeStatus.FAILED if errors else IntakeStatus.INITIALIZED
    current_step = "INTAKE_FAILED" if errors else "INTAKE_INITIALIZED"

    failed_voice_state: VoiceProcessingState | None = None
    if normalized_input_type == InputType.VOICE and errors:
        failed_voice_state = {
            "status": VoiceProcessingStatus.FAILED.value,
            "media_ref": str(clean_audio_ref or ""),
            "media_format": None,
            "duration_seconds": None,
            "transcription": None,
            "word_confidence": None,
            "error_message": "; ".join(errors),
        }

    state: FieldMindWorkflowState = {
        "job_id": assigned_job_id,
        "customer_id": cust_id,
        "customer_info": cust_record,
        "input_type": normalized_input_type.value if normalized_input_type else "UNKNOWN",
        "request_text": clean_text,
        "user_prompt": clean_text if normalized_input_type == InputType.TEXT else None,
        "audio_ref": clean_audio_ref,
        "media_ref": clean_audio_ref,
        "audio_url": clean_audio_ref if clean_audio_ref and clean_audio_ref.startswith(("http://", "https://")) else None,
        "audio_transcript": None,
        "voice_state": failed_voice_state,
        "current_step": current_step,
        "status": initial_status.value,
        "errors": errors,
        "metadata": metadata or {},
    }

    return state


def update_intake_state(
    current_state: FieldMindWorkflowState,
    update_data: dict[str, Any],
) -> FieldMindWorkflowState:
    """
    Safely update the LangGraph state with new data without overwriting
    unrelated fields or dropping accumulated errors.

    Args:
        current_state: The existing workflow state dictionary.
        update_data: Dictionary of new/updated keys to merge.

    Returns:
        A new FieldMindWorkflowState dictionary containing the merged data.
    """
    merged: FieldMindWorkflowState = dict(current_state)  # shallow copy

    # Special handling for errors: combine lists rather than replacing
    if "errors" in update_data:
        existing_errors = list(current_state.get("errors", []))
        new_errors = update_data["errors"]
        if isinstance(new_errors, list):
            for err in new_errors:
                if err and err not in existing_errors:
                    existing_errors.append(err)
        elif isinstance(new_errors, str) and new_errors:
            if new_errors not in existing_errors:
                existing_errors.append(new_errors)
        merged["errors"] = existing_errors

    # Special handling for metadata: deep merge dicts
    if "metadata" in update_data and isinstance(update_data["metadata"], dict):
        merged_meta = dict(current_state.get("metadata") or {})
        merged_meta.update(update_data["metadata"])
        merged["metadata"] = merged_meta

    # Special handling for customer_info: merge dicts
    if "customer_info" in update_data and isinstance(update_data["customer_info"], dict):
        merged_cust = dict(current_state.get("customer_info") or {})
        merged_cust.update(update_data["customer_info"])
        merged["customer_info"] = merged_cust

    # Special handling for voice_state: merge dicts
    if "voice_state" in update_data and isinstance(update_data["voice_state"], dict):
        merged_voice = dict(current_state.get("voice_state") or {})
        merged_voice.update(update_data["voice_state"])
        merged["voice_state"] = merged_voice

    # Apply all other keys
    for k, v in update_data.items():
        if k not in {"errors", "metadata", "customer_info", "voice_state"}:
            merged[k] = v

    return merged
