"""
Voice Intake agent nodes for LangGraph.

Responsible for:
1. Detecting audio format, checking integrity, and initializing voice processing state.
2. Handing off audio to Whisper for transcription with Job ID correlation.
3. Validating the generated transcript (detecting empty output, silence hallucinations).
4. Ensuring invalid/corrupt audio does not proceed to downstream AI processing.
"""
import logging
from typing import Any

from app.agents.graph.state import (
    FieldMindWorkflowState,
    IntakeStatus,
    VoiceProcessingState,
    VoiceProcessingStatus,
)
from app.integrations.whisper.client import (
    AudioProcessor,
    CorruptAudioError,
    EmptyTranscriptionError,
    InvalidAudioFileError,
    UnsupportedAudioFormatError,
    WhisperClient,
    WhisperError,
    get_whisper_client,
)

logger = logging.getLogger(__name__)


def initialize_voice_intake(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Validate incoming voice request, verify Job ID and audio reference,
    detect audio format, and establish the voice processing state.

    Acceptance criteria satisfied:
    - Supported audio formats detected (.ogg, .mp3, .wav, .m4a, .aac, .flac, .webm).
    - Corrupt or missing audio is detected and rejected.
    - Job ID and media reference are preserved.
    - Initial voice processing state is created.
    """
    job_id = state.get("job_id")
    media_ref = state.get("audio_ref") or state.get("media_ref") or state.get("audio_url")
    errors: list[str] = list(state.get("errors", []))

    # 1. Verify Job ID
    if not job_id or not str(job_id).strip():
        msg = "Job ID is missing or invalid in voice intake state"
        logger.error(msg)
        errors.append(msg)

    # 2. Verify Audio Reference
    if not media_ref or not str(media_ref).strip():
        msg = "Audio reference is missing (Audio/media reference is missing for VOICE input type)."
        logger.error(msg)
        errors.append(msg)

    clean_media_ref = str(media_ref).strip() if media_ref else ""

    # 3. Detect Format & Validate File Integrity
    detected_format: str | None = None
    if clean_media_ref:
        try:
            fmt = AudioProcessor.detect_format(clean_media_ref)
            detected_format = fmt.value
            AudioProcessor.validate_audio_file(clean_media_ref)
        except (UnsupportedAudioFormatError, CorruptAudioError, InvalidAudioFileError) as exc:
            msg = str(exc)
            logger.error("Audio validation failed for job_id=%s: %s", job_id, msg)
            errors.append(msg)

    if errors:
        failed_voice_state: VoiceProcessingState = {
            "status": VoiceProcessingStatus.FAILED.value,
            "media_ref": clean_media_ref,
            "media_format": detected_format,
            "duration_seconds": None,
            "transcription": None,
            "word_confidence": None,
            "error_message": "; ".join(errors),
        }
        return {
            "voice_state": failed_voice_state,
            "status": IntakeStatus.FAILED.value,
            "current_step": "VOICE_INTAKE_FAILED",
            "errors": errors,
        }

    initial_voice_state: VoiceProcessingState = {
        "status": VoiceProcessingStatus.INITIALIZED.value,
        "media_ref": clean_media_ref,
        "media_format": detected_format,
        "duration_seconds": None,
        "transcription": None,
        "word_confidence": None,
        "error_message": None,
    }

    logger.info("Initialized voice intake state for job_id=%s, format=%s", job_id, detected_format)

    return {
        "job_id": str(job_id),
        "audio_ref": clean_media_ref,
        "media_ref": clean_media_ref,
        "audio_url": clean_media_ref if clean_media_ref.startswith(("http://", "https://")) else state.get("audio_url"),
        "voice_state": initial_voice_state,
        "status": IntakeStatus.PROCESSING.value,
        "current_step": "VOICE_INITIALIZED",
        "errors": [],
    }


def transcribe_voice(
    state: FieldMindWorkflowState,
    client: WhisperClient | None = None,
) -> dict[str, Any]:
    """
    Execute Whisper transcription on the validated audio media reference,
    validate transcript quality, and associate output with Job ID.

    Acceptance criteria satisfied:
    - Valid audio is sent to Whisper.
    - Transcript text is returned and validated for empty/silence output.
    - Transcript is associated with the correct Job ID.
    - Exceptions are caught and recorded without breaking the workflow.
    - Invalid audio halts downstream AI processing.
    """
    current_errors = state.get("errors", [])
    voice_state = state.get("voice_state") or {}
    job_id = state.get("job_id")

    if current_errors or voice_state.get("status") in {VoiceProcessingStatus.FAILED, VoiceProcessingStatus.FAILED.value}:
        logger.warning("Skipping transcription for job_id=%s due to existing errors: %s", job_id, current_errors)
        return {
            "status": IntakeStatus.FAILED.value,
            "current_step": "VOICE_TRANSCRIPTION_SKIPPED",
        }

    media_ref = state.get("audio_ref") or state.get("media_ref") or voice_state.get("media_ref")
    if not media_ref:
        err_msg = "Cannot transcribe: no media reference available"
        logger.error(err_msg)
        return {
            "voice_state": {
                **voice_state,
                "status": VoiceProcessingStatus.FAILED.value,
                "error_message": err_msg,
            },
            "status": IntakeStatus.FAILED.value,
            "current_step": "VOICE_TRANSCRIPTION_FAILED",
            "errors": [err_msg],
        }

    whisper = client or get_whisper_client()

    try:
        logger.info("Executing Whisper transcription for job_id=%s (media=%s)", job_id, media_ref)
        result = whisper.transcribe(media_ref, job_id=job_id)

        updated_voice_state: VoiceProcessingState = {
            **voice_state,
            "status": VoiceProcessingStatus.TRANSCRIBED.value,
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
            "status": IntakeStatus.READY_FOR_DIAGNOSTICS.value,
            "current_step": "VOICE_TRANSCRIBED",
            "errors": [],
            "metadata": {
                **(state.get("metadata") or {}),
                "whisper_model": result.model_name,
                "whisper_language": result.language,
            },
        }

    except (
        EmptyTranscriptionError,
        CorruptAudioError,
        UnsupportedAudioFormatError,
        InvalidAudioFileError,
        WhisperError,
        Exception,
    ) as exc:
        err_msg = f"Transcription failure: {exc}"
        logger.error("Failed transcribing job_id=%s: %s", job_id, exc)

        failed_voice_state: VoiceProcessingState = {
            **voice_state,
            "status": VoiceProcessingStatus.FAILED.value,
            "error_message": err_msg,
        }

        return {
            "voice_state": failed_voice_state,
            "status": IntakeStatus.FAILED.value,
            "current_step": "VOICE_TRANSCRIPTION_FAILED",
            "errors": [err_msg],
        }
