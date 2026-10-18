"""
Booking and Service Request domain service.

Coordinates the intake of customer service requests across Text and Voice modalities,
passing normalized requests and metadata into the LangGraph AI multi-agent workflow.
"""
import logging
from typing import Any

from app.agents.graph.workflow import run_intake_workflow, run_voice_intake_workflow
from app.schemas.service_request import (
    CustomerIntakeRequest,
    CustomerIntakeResponse,
    VoiceIntakeRequest,
    VoiceIntakeResponse,
    VoiceProcessingStateResponse,
)

logger = logging.getLogger(__name__)


class BookingService:
    """Service orchestrating customer bookings and multi-modal intake processing."""

    @staticmethod
    def process_customer_intake(request: CustomerIntakeRequest) -> CustomerIntakeResponse:
        """
        Pass a validated customer request (Text or Voice) into the LangGraph intake workflow.

        Args:
            request: Validated CustomerIntakeRequest.

        Returns:
            CustomerIntakeResponse with complete workflow state and processing outcomes.
        """
        logger.info(
            "Ingesting customer request into LangGraph: job_id=%s, input_type=%s",
            request.job_id,
            request.input_type,
        )

        audio_ref = request.audio_ref or request.media_ref

        final_state = run_intake_workflow(
            job_id=request.job_id,
            input_type=request.input_type,
            request_text=request.request_text,
            audio_ref=audio_ref,
            customer_id=request.customer_id,
            customer_info=request.customer_info,
            metadata=request.metadata,
        )

        voice_substate = final_state.get("voice_state") or {}
        raw_voice_status = voice_substate.get("status")
        voice_status_val = (
            raw_voice_status.value
            if hasattr(raw_voice_status, "value")
            else str(raw_voice_status or "UNKNOWN")
        )

        voice_state_resp = (
            VoiceProcessingStateResponse(
                status=voice_status_val,
                media_ref=voice_substate.get("media_ref", audio_ref or ""),
                media_format=voice_substate.get("media_format"),
                duration_seconds=voice_substate.get("duration_seconds"),
                transcription=voice_substate.get("transcription"),
                word_confidence=voice_substate.get("word_confidence"),
                error_message=voice_substate.get("error_message"),
            )
            if voice_substate
            else None
        )

        raw_intake_status = final_state.get("status", "UNKNOWN")
        intake_status_val = (
            raw_intake_status.value
            if hasattr(raw_intake_status, "value")
            else str(raw_intake_status)
        )

        return CustomerIntakeResponse(
            job_id=final_state.get("job_id", request.job_id),
            input_type=str(final_state.get("input_type", "UNKNOWN")),
            status=intake_status_val,
            current_step=final_state.get("current_step", "UNKNOWN"),
            request_text=final_state.get("request_text"),
            user_prompt=final_state.get("user_prompt"),
            audio_transcript=final_state.get("audio_transcript"),
            voice_state=voice_state_resp,
            errors=final_state.get("errors", []),
        )

    @staticmethod
    def process_voice_intake(request: VoiceIntakeRequest) -> VoiceIntakeResponse:
        """
        Backwards-compatible voice intake pipeline entrypoint.
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
