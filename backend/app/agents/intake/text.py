"""
Text Intake agent node for LangGraph.

Processes and validates customer text requests, normalizing text input,
preserving customer context, and preparing the state for intent diagnostics.
"""
import logging
from typing import Any

from app.agents.graph.state import (
    FieldMindWorkflowState,
    IntakeStatus,
)

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 3
MAX_TEXT_LENGTH = 4000


def process_text_intake(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Validate and process a customer text request.

    Acceptance criteria:
    - Valid text request enters LangGraph.
    - Request/Job ID is preserved.
    - Customer information is available in state.
    - Normalized text is stored in `request_text` and `user_prompt`.
    - Invalid text (empty, whitespace-only, too short) is detected and rejected.
    """
    job_id = state.get("job_id")
    raw_text = state.get("request_text") or state.get("user_prompt")
    errors: list[str] = list(state.get("errors", []))

    logger.info("Processing text intake for job_id=%s", job_id)

    # Validate presence of Job ID
    if not job_id or not str(job_id).strip():
        msg = "Job ID is missing or invalid in text intake state"
        logger.error(msg)
        errors.append(msg)

    # Validate text content
    if raw_text is None or not isinstance(raw_text, str) or not raw_text.strip():
        msg = "Customer request text is empty or missing"
        logger.error(msg)
        errors.append(msg)
    else:
        cleaned_text = raw_text.strip()
        if len(cleaned_text) < MIN_TEXT_LENGTH:
            msg = f"Request text too short (minimum {MIN_TEXT_LENGTH} characters required)"
            logger.warning(msg)
            errors.append(msg)
        elif len(cleaned_text) > MAX_TEXT_LENGTH:
            msg = f"Request text exceeds maximum permitted length of {MAX_TEXT_LENGTH} characters"
            logger.warning(msg)
            errors.append(msg)

    if errors:
        return {
            "status": IntakeStatus.FAILED.value,
            "current_step": "TEXT_INTAKE_FAILED",
            "errors": errors,
        }

    cleaned_text = str(raw_text).strip()

    return {
        "job_id": str(job_id),
        "request_text": cleaned_text,
        "user_prompt": cleaned_text,
        "status": IntakeStatus.READY_FOR_DIAGNOSTICS.value,
        "current_step": "TEXT_INTAKE_PROCESSED",
        "errors": [],
    }
