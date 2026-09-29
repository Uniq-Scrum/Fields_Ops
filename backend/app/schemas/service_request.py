"""
Pydantic schemas for Service Requests and Voice Intake workflows.
"""
from typing import Any
import uuid

from pydantic import BaseModel, Field


class VoiceIntakeRequest(BaseModel):
    """
    Validated incoming voice request payload.

    Receives the customer's voice recording reference (WhatsApp audio note,
    mobile app upload, or S3 object URI) to enter the AI intake pipeline.
    """
    job_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the service job. Auto-generated if not provided.",
    )
    customer_id: str | None = Field(
        default=None,
        description="Identifier of the requesting customer if authenticated.",
    )
    media_ref: str = Field(
        ...,
        min_length=1,
        description="Persisted media reference, local audio file path, or object storage URL.",
    )
    audio_url: str | None = Field(
        default=None,
        description="Public or pre-signed URL to the audio file if distinct from media_ref.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context such as client device, language preference, or channel.",
    )


class VoiceProcessingStateResponse(BaseModel):
    """Voice processing lifecycle state output."""
    status: str
    media_ref: str
    media_format: str | None = None
    duration_seconds: float | None = None
    transcription: str | None = None
    word_confidence: float | None = None
    error_message: str | None = None


class VoiceIntakeResponse(BaseModel):
    """Response returned upon connecting the voice request to the LangGraph intake workflow."""
    job_id: str
    current_step: str
    audio_transcript: str | None = None
    voice_state: VoiceProcessingStateResponse | None = None
    errors: list[str] = Field(default_factory=list)
