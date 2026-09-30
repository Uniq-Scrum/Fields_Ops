"""
Unit and Integration tests for Whisper Audio Processing & Transcription Engine.

Verifies:
- Objective 1 & 2: Audio format detection (OGG, MP3, WAV, M4A, AAC, FLAC, WebM) & corrupt file detection.
- Objective 2: FFmpeg conversion pipeline and format compatibility checks.
- Objective 3 & 5: Transcription execution, Job ID correlation, and transcript validation (silence/empty detection).
- Objective 4: Resilient error handling without breaking request workflow.
- Objective 6: End-to-end handoff from transcription to intent diagnostic state.
"""
import os
import tempfile
import uuid
import pytest

from app.agents.graph.state import InputType, IntakeStatus, VoiceProcessingStatus
from app.agents.graph.workflow import run_intake_workflow
from app.integrations.whisper.client import (
    AudioFormat,
    AudioProcessor,
    CorruptAudioError,
    EmptyTranscriptionError,
    TranscriptionResult,
    UnsupportedAudioFormatError,
    WhisperClient,
    WhisperConfig,
    WhisperTranscriptionError,
    get_whisper_client,
    validate_transcript,
)


@pytest.fixture(autouse=True)
def reset_whisper():
    client = get_whisper_client()
    yield client
    client.set_custom_transcriber(None)


# --- 1. Audio Format Detection & Validation Tests ---

def test_audio_format_detection_by_extension():
    """Verify detection across all supported audio file extensions."""
    test_cases = [
        ("recording.ogg", AudioFormat.OGG),
        ("recording.opus", AudioFormat.OPUS),
        ("recording.mp3", AudioFormat.MP3),
        ("recording.wav", AudioFormat.WAV),
        ("recording.m4a", AudioFormat.M4A),
        ("recording.aac", AudioFormat.AAC),
        ("recording.flac", AudioFormat.FLAC),
        ("recording.webm", AudioFormat.WEBM),
        ("https://s3.bucket/path/voice_note.ogg?token=xyz", AudioFormat.OGG),
    ]
    for path, expected_fmt in test_cases:
        assert AudioProcessor.detect_format(path) == expected_fmt


def test_audio_format_detection_by_magic_bytes():
    """Verify format detection via binary magic headers."""
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"RIFF\x00\x00\x00\x00WAVE") == AudioFormat.WAV
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"OggS\x00\x02\x00\x00") == AudioFormat.OGG
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"ID3\x03\x00\x00\x00") == AudioFormat.MP3
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"fLaC\x00\x00\x00\x22") == AudioFormat.FLAC
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"\x00\x00\x00\x20ftypM4A ") == AudioFormat.M4A
    assert AudioProcessor.detect_format("unknown_file", header_bytes=b"\x1a\x45\xdf\xa3\x9f\x42") == AudioFormat.WEBM


def test_unsupported_audio_format_rejected():
    """Verify unsupported extensions raise UnsupportedAudioFormatError."""
    unsupported = ["document.pdf", "app.exe", "notes.txt", "archive.zip", "script.py"]
    for path in unsupported:
        with pytest.raises(UnsupportedAudioFormatError):
            AudioProcessor.detect_format(path)


def test_corrupt_empty_audio_file_detected():
    """Verify 0-byte audio file raises CorruptAudioError."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    try:
        with pytest.raises(CorruptAudioError, match="corrupt or empty"):
            AudioProcessor.validate_audio_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# --- 2. FFmpeg Conversion Pipeline Tests ---

def test_ffmpeg_conversion_fallback_without_binary():
    """Verify that when FFmpeg is unavailable, audio is passed directly with format validation."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Write valid minimal WAV header
        f.write(b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"fmt " + b"\x10\x00\x00\x00" + b"\x01\x00\x01\x00" + b"\x80\x3e\x00\x00" + b"\x00\x7d\x00\x00" + b"\x02\x00\x10\x00" + b"data" + b"\x00\x00\x00\x00")
        f.flush()
        temp_path = f.name

    try:
        result_path = AudioProcessor.convert_to_pcm_wav(temp_path)
        assert os.path.exists(result_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# --- 3. Transcript Quality & Validation Tests ---

def test_validate_transcript_valid():
    """Verify valid spoken transcript passes validation."""
    valid_text = "Water heater pilot light is out and gas smell is present."
    assert validate_transcript(valid_text) == valid_text


def test_validate_transcript_empty_or_whitespace():
    """Verify empty or whitespace-only transcript is rejected."""
    with pytest.raises(EmptyTranscriptionError):
        validate_transcript("")
    with pytest.raises(EmptyTranscriptionError):
        validate_transcript("   \n\t  ")


def test_validate_transcript_too_short():
    """Verify transcript below minimum length is rejected."""
    with pytest.raises(EmptyTranscriptionError, match="too short"):
        validate_transcript("a", min_chars=3)


def test_validate_transcript_silence_hallucination_rejected():
    """Verify common Whisper silence/hallucination tokens are detected and rejected."""
    hallucinations = ["[silence]", "[MUSIC]", "[Applause]", "....", "Thank you for watching.", "subtitles by John"]
    for token in hallucinations:
        with pytest.raises(EmptyTranscriptionError, match="non-speech artefact"):
            validate_transcript(token)


# --- 4. Whisper Client & Job ID Correlation Tests ---

def test_whisper_transcription_job_id_correlation(reset_whisper):
    """Verify transcription result accurately correlates with the Request / Job ID."""
    job_id = f"job-{uuid.uuid4()}"
    custom_text = "Kitchen sink drain pipe is disconnected under the cabinet."

    reset_whisper.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text=custom_text,
            duration_seconds=3.8,
            language="en",
            confidence=0.96,
            model_name="test-whisper",
            job_id=job_id,
        )
    )

    result = reset_whisper.transcribe("audio/sink.ogg", job_id=job_id)

    assert result.text == custom_text
    assert result.job_id == job_id
    assert result.confidence == 0.96
    assert result.model_name == "test-whisper"


def test_whisper_transcription_empty_output_detected(reset_whisper):
    """Verify that an empty transcript returned by transcriber raises EmptyTranscriptionError."""
    reset_whisper.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text="   ",
            duration_seconds=2.0,
            language="en",
            confidence=0.1,
        )
    )

    with pytest.raises(EmptyTranscriptionError):
        reset_whisper.transcribe("audio/silent.wav")


# --- 5. LangGraph Full Audio ➔ Whisper ➔ Intent Pipeline Tests ---

def test_workflow_audio_to_intent_success_pipeline(reset_whisper):
    """
    Verify complete pipeline:
    Audio Request ➔ LangGraph ➔ Whisper ➔ Transcript Validation ➔ Intent Diagnostics Handoff.
    """
    job_id = str(uuid.uuid4())
    customer_id = str(uuid.uuid4())
    spoken_text = "Emergency: Main bathroom pipe burst and water flooding down the hallway."

    reset_whisper.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text=spoken_text,
            duration_seconds=6.2,
            language="en",
            confidence=0.99,
        )
    )

    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref="https://s3.amazonaws.com/fieldmind/audio/emergency_pipe.mp3",
        customer_id=customer_id,
    )

    # Acceptance criteria verification
    assert final_state["job_id"] == job_id
    assert final_state["customer_id"] == customer_id
    assert final_state["audio_transcript"] == spoken_text
    assert final_state["user_prompt"] == spoken_text
    assert final_state["status"] == IntakeStatus.READY_FOR_DIAGNOSTICS.value
    assert final_state["current_step"] == "READY_FOR_INTENT_EXTRACTION"
    assert final_state["metadata"]["transcript_job_id"] == job_id
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.TRANSCRIBED.value
    assert len(final_state["errors"]) == 0


def test_workflow_halts_on_corrupt_audio():
    """Verify corrupt audio halts the workflow and prevents downstream AI execution."""
    job_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name  # 0 bytes

    try:
        final_state = run_intake_workflow(
            job_id=job_id,
            input_type=InputType.VOICE,
            audio_ref=temp_path,
        )

        assert final_state["status"] == IntakeStatus.FAILED.value
        assert final_state["current_step"] == "WORKFLOW_FAILED"
        assert any("corrupt or empty" in err for err in final_state["errors"])
        assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED.value
        assert "audio_transcript" not in final_state or final_state["audio_transcript"] is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_workflow_halts_on_empty_transcription(reset_whisper):
    """Verify empty/silent audio transcription stops workflow and logs failure."""
    reset_whisper.set_custom_transcriber(
        lambda ref: TranscriptionResult(
            text="[silence]",
            duration_seconds=3.0,
            language="en",
            confidence=0.0,
        )
    )

    job_id = str(uuid.uuid4())
    final_state = run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref="s3://bucket/audio/silence.ogg",
    )

    assert final_state["status"] == IntakeStatus.FAILED.value
    assert final_state["current_step"] == "WORKFLOW_FAILED"
    assert any("non-speech artefact" in err for err in final_state["errors"])
    assert final_state["voice_state"]["status"] == VoiceProcessingStatus.FAILED.value
