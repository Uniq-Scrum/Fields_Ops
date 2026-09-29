"""
Booking and Service Request domain service.

Coordinates the intake of customer service requests, passing voice notes
and metadata into the LangGraph AI multi-agent workflow.
"""
import logging
from typing import Any

from app.agents.graph.workflow import run_voice_intake_workflow
from app.schemas.service_request import (
    VoiceIntakeRequest,
    VoiceIntakeResponse,
    VoiceProcessingStateResponse,
)

logger = logging.getLogger(__name__)


class BookingService:
    """Service orchestrating customer bookings and voice intake processing."""

    @staticmethod
    def process_voice_intake(request: VoiceIntakeRequest) -> VoiceIntakeResponse:
        """
        Pass the validated voice request into the LangGraph intake workflow,
        initializing the voice processing state and proceeding through Whisper.

        Args:
            request: Validated VoiceIntakeRequest with job_id and media_ref.

        Returns:
            VoiceIntakeResponse with workflow state and transcription results.
        """
        logger.info(
            "Connecting voice request to LangGraph intake workflow: job_id=%s, media_ref=%s",
            request.job_id,
            request.media_ref,
        )

        final_state = run_voice_intake_workflow(
            job_id=request.job_id,
            media_ref=request.media_ref,
            customer_id=request.customer_id,
            metadata=request.metadata,
        )

        voice_substate = final_state.get("voice_state") or {}
        raw_status = voice_substate.get("status")
        status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status or "UNKNOWN")

        voice_state_resp = (
            VoiceProcessingStateResponse(
                status=status_val,
                media_ref=voice_substate.get("media_ref", request.media_ref),
                media_format=voice_substate.get("media_format"),
                duration_seconds=voice_substate.get("duration_seconds"),
                transcription=voice_substate.get("transcription"),
                word_confidence=voice_substate.get("word_confidence"),
                error_message=voice_substate.get("error_message"),
            )
            if voice_substate
            else None
        )

        return VoiceIntakeResponse(
            job_id=final_state.get("job_id", request.job_id),
            current_step=final_state.get("current_step", "UNKNOWN"),
            audio_transcript=final_state.get("audio_transcript"),
            voice_state=voice_state_resp,
            errors=final_state.get("errors", []),
        )
