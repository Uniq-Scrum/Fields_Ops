"""
FastAPI routes for Service Requests and AI Intake.

Provides endpoints to ingest customer repair requests across Text and Voice modalities,
initiating the LangGraph multi-agent orchestration pipeline.
"""
from fastapi import APIRouter, status

from app.schemas.service_request import (
    CustomerIntakeRequest,
    CustomerIntakeResponse,
    VoiceIntakeRequest,
    VoiceIntakeResponse,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/api/v1/requests", tags=["service-requests"])


@router.post(
    "/intake",
    response_model=CustomerIntakeResponse,
    status_code=status.HTTP_200_OK,
    summary="Unified multi-modal customer request intake (Text or Voice)",
    description=(
        "Receives a customer repair request in either natural-language text or "
        "persisted voice audio format. Initializes LangGraph intake state, routes "
        "to the appropriate ingestion node, runs Whisper transcription if voice, "
        "and prepares state for intent diagnostics."
    ),
)
def handle_customer_intake(request: CustomerIntakeRequest) -> CustomerIntakeResponse:
    """Unified entrypoint connecting Text or Voice customer requests to LangGraph."""
    return BookingService.process_customer_intake(request)


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
    """Dedicated voice entrypoint connecting audio media to the AI intake workflow."""
    return BookingService.process_voice_intake(request)
