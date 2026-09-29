"""
FastAPI routes for Service Requests and AI Intake.

Provides endpoints to ingest customer repair requests and trigger
the LangGraph multi-agent orchestration pipeline.
"""
from fastapi import APIRouter, status

from app.schemas.service_request import (
    VoiceIntakeRequest,
    VoiceIntakeResponse,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/api/v1/requests", tags=["service-requests"])


@router.post(
    "/voice-intake",
    response_model=VoiceIntakeResponse,
    status_code=status.HTTP_200_OK,
    summary="Connect a validated voice request to the LangGraph AI intake workflow",
    description=(
        "Receives a voice request with its persisted media reference, "
        "initializes the voice processing state in LangGraph, and executes "
        "Whisper audio transcription toward intent extraction."
    ),
)
def handle_voice_intake(request: VoiceIntakeRequest) -> VoiceIntakeResponse:
    """Entrypoint connecting validated voice media to the AI intake workflow."""
    return BookingService.process_voice_intake(request)
