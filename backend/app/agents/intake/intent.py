"""
Intent diagnostic handoff node for LangGraph.

Prepares the transcribed natural language request for structured Pydantic
schema parsing (Category, Required Skills, Urgency, Scope), ensuring the
validated transcript and Job ID context are forwarded to downstream AI models.
"""
import logging
from typing import Any

from app.agents.graph.state import FieldMindWorkflowState, IntakeStatus

logger = logging.getLogger(__name__)


def prepare_intent_diagnostics(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Handoff node connecting the transcribed audio to intent parsing.

    Acceptance criteria satisfied:
    - Valid transcript is verified before proceeding to downstream AI.
    - Transcript remains associated with the correct request / Job ID.
    - Transcription node transitions to the next AI node.
    - Invalid or missing transcript does not proceed.
    - Workflow errors are handled cleanly.
    """
    transcript = state.get("audio_transcript") or state.get("user_prompt")
    errors = state.get("errors", [])
    job_id = state.get("job_id")

    if errors or not transcript:
        logger.warning(
            "Intent diagnostics bypassed for job_id=%s: transcript missing or workflow in error state. Errors: %s",
            job_id,
            errors,
        )
        return {
            "status": IntakeStatus.FAILED.value,
            "current_step": "INTENT_HANDOFF_SKIPPED",
        }

    logger.info("Proceeding to intent parsing for job_id=%s with transcript: %s", job_id, transcript[:60])
    return {
        "status": IntakeStatus.READY_FOR_DIAGNOSTICS.value,
        "current_step": "READY_FOR_INTENT_EXTRACTION",
        "metadata": {
            **(state.get("metadata") or {}),
            "intent_intake_received": True,
            "transcript_job_id": job_id,
            "validated_transcript_length": len(transcript),
        },
    }
