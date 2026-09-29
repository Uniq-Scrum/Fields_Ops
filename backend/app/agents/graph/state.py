"""
State definitions for the FieldMind AI LangGraph multi-agent workflow.

Defines the central schema `FieldMindWorkflowState` managed by LangGraph,
persisted across checkpoints, and transitioned through the intake,
transcription, intent parsing, dispatch, and settlement pipeline.
"""
from enum import Enum
import operator
from typing import Annotated, Any, TypedDict


class VoiceProcessingStatus(str, Enum):
    """Lifecycle statuses for the voice intake and transcription stage."""
    PENDING = "PENDING"
    INITIALIZED = "INITIALIZED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    FAILED = "FAILED"


class VoiceProcessingState(TypedDict, total=False):
    """
    Detailed sub-state tracking the audio ingestion and Whisper transcription.

    Holds the persisted media reference, audio format, transcription output,
    duration metrics, and error context if processing fails.
    """
    status: VoiceProcessingStatus
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
        job_id: Unique identifier for the service request / job.
        customer_id: Identifier of the requesting customer.
        user_prompt: Synthesized or transcribed natural-language user query.
        media_ref: Persisted media reference (S3 URI, local path, or webhook payload ref).
        audio_url: Direct accessible URL to the audio file if applicable.
        voice_state: Structured sub-state tracking voice processing and transcription.
        audio_transcript: Extracted raw transcript from Whisper.
        current_step: Current active stage in the multi-agent graph.
        errors: Aggregated list of workflow failure messages.
        metadata: Extensible key-value metadata for tracing, tenancy, and telemetry.
    """
    job_id: str
    customer_id: str | None
    user_prompt: str | None
    media_ref: str | None
    audio_url: str | None
    voice_state: VoiceProcessingState | None
    audio_transcript: str | None
    current_step: str
    errors: Annotated[list[str], operator.add]
    metadata: dict[str, Any]
