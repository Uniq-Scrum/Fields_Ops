"""
Pydantic schemas for Service Requests and Multi-Modal Customer Intake workflows.
"""
from typing import Any
import uuid

from pydantic import BaseModel, Field, model_validator


class VoiceProcessingStateResponse(BaseModel):
    """Voice processing lifecycle state output."""
    status: str
    media_ref: str
    media_format: str | None = None
    duration_seconds: float | None = None
    transcription: str | None = None
    word_confidence: float | None = None
    error_message: str | None = None


class CustomerIntakeRequest(BaseModel):
    """
    Unified multi-modal customer request payload.

    Accepts either natural language text or voice recording references
    to enter the LangGraph AI multi-agent workflow.
    """
    job_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the service job. Auto-generated if not provided.",
    )
    input_type: str | None = Field(
        default=None,
        description="Channel modality: 'TEXT' or 'VOICE'. Automatically inferred if omitted.",
    )
    request_text: str | None = Field(
        default=None,
        description="Customer repair description in text format.",
    )
    audio_ref: str | None = Field(
        default=None,
        description="Persisted media reference, S3 URI, or URL for audio notes.",
    )
    media_ref: str | None = Field(
        default=None,
        description="Alias for audio_ref for backwards compatibility.",
    )
    customer_id: str | None = Field(
        default=None,
        description="Identifier of the requesting customer if authenticated.",
    )
    customer_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Customer profile details (name, phone, email).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context such as client device, channel, or location coordinates.",
    )

    @model_validator(mode='after')
    def validate_request_content(self) -> "CustomerIntakeRequest":
        is_voice = bool(self.input_type == "VOICE" or self.audio_ref or self.media_ref)
        
        if self.input_type == "TEXT" or not is_voice:
            if not self.request_text or not self.request_text.strip():
                raise ValueError("request_text must be provided and cannot be empty or whitespace-only.")
        
        if self.request_text is not None and not self.request_text.strip():
            raise ValueError("request_text must not be empty or whitespace-only.")

        return self


class CustomerIntakeResponse(BaseModel):
    """Response returned upon connecting customer request to the LangGraph intake workflow."""
    job_id: str
    input_type: str
    status: str
    current_step: str
    request_text: str | None = None
    user_prompt: str | None = None
    audio_transcript: str | None = None
    voice_state: VoiceProcessingStateResponse | None = None
    errors: list[str] = Field(default_factory=list)


# --- Backwards compatibility wrappers for Voice-only intake ---
class VoiceIntakeRequest(BaseModel):
    """Validated incoming voice request payload (backwards-compatible)."""
    job_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the service job.",
    )
    customer_id: str | None = Field(
        default=None,
        description="Identifier of the requesting customer.",
    )
    media_ref: str = Field(
        ...,
        min_length=1,
        description="Persisted media reference or audio file path/URL.",
    )
    audio_url: str | None = Field(
        default=None,
        description="Public or pre-signed URL to the audio file.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context metadata.",
    )


class VoiceIntakeResponse(BaseModel):
    """Response returned upon connecting voice request to intake workflow."""
    job_id: str
    current_step: str
    audio_transcript: str | None = None
    voice_state: VoiceProcessingStateResponse | None = None
    errors: list[str] = Field(default_factory=list)
