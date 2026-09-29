"""
Intent diagnostic handoff node for LangGraph.

Prepares the transcribed natural language request for structured Pydantic
schema parsing (Category, Required Skills, Urgency, Scope).
"""
import logging
from typing import Any

from app.agents.graph.state import FieldMindWorkflowState

logger = logging.getLogger(__name__)


def prepare_intent_diagnostics(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Handoff node connecting the transcribed audio to intent parsing.

    Ensures valid transcript exists before proceeding to LLM diagnostic extraction.
    """
    transcript = state.get("audio_transcript") or state.get("user_prompt")
    errors = state.get("errors", [])

    if errors or not transcript:
        logger.warning(
            "Intent diagnostics bypassed: transcript missing or workflow in error state. Errors: %s",
            errors,
        )
        return {
            "current_step": "INTENT_HANDOFF_SKIPPED",
        }

    logger.info("Proceeding to intent parsing with transcript: %s", transcript[:60])
    return {
        "current_step": "READY_FOR_INTENT_EXTRACTION",
        "metadata": {
            **(state.get("metadata") or {}),
            "intent_intake_received": True,
        },
    }
