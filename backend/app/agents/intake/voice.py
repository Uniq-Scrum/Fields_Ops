"""
Voice Intake agent nodes for LangGraph.

Responsible for:
1. Validating incoming voice requests and their persisted media references.
2. Initializing the structured voice processing state.
3. Handing off audio to Whisper for transcription and capturing any processing failures.
"""
import logging
from pathlib import Path
from typing import Any

from app.agents.graph.state import (
    FieldMindWorkflowState,
    VoiceProcessingState,
    VoiceProcessingStatus,
)
from app.integrations.whisper.client import (
    InvalidAudioFileError,
    WhisperClient,
    WhisperError,
    get_whisper_client,
)

logger = logging.getLogger(__name__)


def initialize_voice_intake(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Validate the incoming voice request, verify job_id and media reference,
    and create the initial voice processing state.

    Acceptance criteria satisfied:
    - Valid voice request enters the intake workflow.
    - Job ID is available in the workflow state.
    - Audio/media reference is available to the workflow.
    - Voice processing state is created.
    - Workflow failures are captured appropriately.
    """
    job_id = state.get("job_id")
    media_ref = state.get("media_ref") or state.get("audio_url")

    errors: list[str] = []

    # 1. Verify Job ID
    if not job_id or not str(job_id).strip():
        msg = "Job ID is missing or invalid in workflow state"
        logger.error(msg)
        errors.append(msg)

    # 2. Verify Audio / Media Reference
    if not media_ref or not str(media_ref).strip():
        msg = "Audio/media reference is missing or empty"
        logger.error(msg)
        errors.append(msg)

    if errors:
        failed_voice_state: VoiceProcessingState = {
            "status": VoiceProcessingStatus.FAILED,
            "media_ref": str(media_ref or ""),
            "media_format": None,
            "duration_seconds": None,
            "transcription": None,
            "word_confidence": None,
            "error_message": "; ".join(errors),
        }
        return {
            "voice_state": failed_voice_state,
            "current_step": "VOICE_INTAKE_FAILED",
            "errors": errors,
        }

    # Normalize media reference format
    clean_media_ref = str(media_ref).strip()
    raw_ext = Path(clean_media_ref.split("?")[0]).suffix.lower()
    media_format = raw_ext.lstrip(".") if raw_ext else "audio"

    initial_voice_state: VoiceProcessingState = {
        "status": VoiceProcessingStatus.INITIALIZED,
        "media_ref": clean_media_ref,
        "media_format": media_format,
        "duration_seconds": None,
        "transcription": None,
        "word_confidence": None,
        "error_message": None,
    }

    logger.info("Initialized voice intake state for job_id=%s, media_ref=%s", job_id, clean_media_ref)

    return {
        "job_id": str(job_id),
        "media_ref": clean_media_ref,
        "audio_url": clean_media_ref if clean_media_ref.startswith(("http://", "https://")) else state.get("audio_url"),
        "voice_state": initial_voice_state,
        "current_step": "VOICE_INITIALIZED",
        "errors": [],
    }


def transcribe_voice(
    state: FieldMindWorkflowState,
    client: WhisperClient | None = None,
) -> dict[str, Any]:
    """
    Execute Whisper transcription on the established audio media reference.

    Acceptance criteria satisfied:
    - Audio can proceed to Whisper transcription.
    - Transcription result updates state and audio_transcript.
    - Workflow failures during transcription are captured appropriately.
    """
    # Guard: if errors already occurred or voice state failed, do not proceed
    current_errors = state.get("errors", [])
    voice_state = state.get("voice_state") or {}

    if current_errors or voice_state.get("status") == VoiceProcessingStatus.FAILED:
        logger.warning("Skipping transcription due to existing workflow errors: %s", current_errors)
        return {
            "current_step": "VOICE_TRANSCRIPTION_SKIPPED",
        }

    media_ref = state.get("media_ref") or voice_state.get("media_ref")
    if not media_ref:
        err_msg = "Cannot transcribe: no media reference available"
        logger.error(err_msg)
        return {
            "voice_state": {
                **voice_state,
                "status": VoiceProcessingStatus.FAILED,
                "error_message": err_msg,
            },
            "current_step": "VOICE_TRANSCRIPTION_FAILED",
            "errors": [err_msg],
        }

    whisper = client or get_whisper_client()

    try:
        logger.info("Executing Whisper transcription for job_id=%s", state.get("job_id"))
        result = whisper.transcribe(media_ref)

        updated_voice_state: VoiceProcessingState = {
            **voice_state,
            "status": VoiceProcessingStatus.TRANSCRIBED,
            "media_ref": media_ref,
            "transcription": result.text,
            "duration_seconds": result.duration_seconds,
            "word_confidence": result.confidence,
            "error_message": None,
        }

        return {
            "voice_state": updated_voice_state,
            "audio_transcript": result.text,
            "user_prompt": result.text,
            "current_step": "VOICE_TRANSCRIBED",
            "errors": [],
        }

    except (InvalidAudioFileError, WhisperError, Exception) as exc:
        err_msg = f"Transcription failure: {exc}"
        logger.error("Failed transcribing job_id=%s: %s", state.get("job_id"), exc)

        failed_voice_state: VoiceProcessingState = {
            **voice_state,
            "status": VoiceProcessingStatus.FAILED,
            "error_message": err_msg,
        }

        return {
            "voice_state": failed_voice_state,
            "current_step": "VOICE_TRANSCRIPTION_FAILED",
            "errors": [err_msg],
        }
