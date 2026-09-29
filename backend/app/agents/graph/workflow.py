"""
LangGraph workflow definition for FieldMind AI Intake & Voice Processing.

Orchestrates the lifecycle from initial voice request ingestion, through
validation, state creation, Whisper transcription handoff, and downstream
intent diagnostic preparation.
"""
import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.graph.checkpoints import get_memory_checkpointer
from app.agents.graph.state import (
    FieldMindWorkflowState,
    VoiceProcessingStatus,
)
from app.agents.intake.intent import prepare_intent_diagnostics
from app.agents.intake.voice import initialize_voice_intake, transcribe_voice

logger = logging.getLogger(__name__)


def handle_workflow_failure(state: FieldMindWorkflowState) -> dict[str, Any]:
    """Capture and record workflow failure state cleanly."""
    errors = state.get("errors", [])
    logger.error("LangGraph intake workflow captured failure: %s", errors)
    return {
        "current_step": "WORKFLOW_FAILED",
    }


def should_transcribe(state: FieldMindWorkflowState) -> str:
    """Route to Whisper transcription if voice state initialized without errors."""
    voice_state = state.get("voice_state") or {}
    if voice_state.get("status") == VoiceProcessingStatus.FAILED or state.get("errors"):
        return "workflow_failure"
    return "transcribe_voice"


def should_proceed_to_intent(state: FieldMindWorkflowState) -> str:
    """Route to intent processing if audio was transcribed successfully."""
    voice_state = state.get("voice_state") or {}
    if voice_state.get("status") == VoiceProcessingStatus.FAILED or state.get("errors"):
        return "workflow_failure"
    return "intent_handoff"


def build_intake_workflow(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """
    Construct and compile the LangGraph voice intake workflow.

    Workflow topology:
        START -> initialize_voice -> (check errors)
                     ├─ [valid] ──> transcribe_voice -> (check errors)
                     │                  ├─ [valid] ──> intent_handoff ──> END
                     │                  └─ [failed] ─> workflow_failure ─> END
                     └─ [failed] ─> workflow_failure ─> END
    """
    workflow = StateGraph(FieldMindWorkflowState)

    # Register workflow nodes
    workflow.add_node("initialize_voice", initialize_voice_intake)
    workflow.add_node("transcribe_voice", transcribe_voice)
    workflow.add_node("intent_handoff", prepare_intent_diagnostics)
    workflow.add_node("workflow_failure", handle_workflow_failure)

    # Define execution graph edges
    workflow.add_edge(START, "initialize_voice")

    workflow.add_conditional_edges(
        "initialize_voice",
        should_transcribe,
        {
            "transcribe_voice": "transcribe_voice",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_conditional_edges(
        "transcribe_voice",
        should_proceed_to_intent,
        {
            "intent_handoff": "intent_handoff",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_edge("intent_handoff", END)
    workflow.add_edge("workflow_failure", END)

    return workflow.compile(checkpointer=checkpointer)


# Default compiled intake workflow with memory checkpointing
intake_workflow = build_intake_workflow(checkpointer=get_memory_checkpointer())


def run_voice_intake_workflow(
    job_id: str,
    media_ref: str,
    customer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> FieldMindWorkflowState:
    """
    Execute the intake workflow for a validated voice request.

    Args:
        job_id: Unique identifier for the job.
        media_ref: Audio file reference or URL.
        customer_id: Optional UUID of the requesting customer.
        metadata: Optional dictionary of request metadata.
        checkpointer: Optional custom LangGraph checkpointer.

    Returns:
        The resulting FieldMindWorkflowState after workflow execution.
    """
    initial_state: FieldMindWorkflowState = {
        "job_id": job_id,
        "customer_id": customer_id,
        "media_ref": media_ref,
        "audio_url": media_ref if str(media_ref).startswith(("http://", "https://")) else None,
        "errors": [],
        "metadata": metadata or {},
    }

    graph = build_intake_workflow(checkpointer=checkpointer) if checkpointer else intake_workflow
    config = {"configurable": {"thread_id": f"job-{job_id}"}}

    final_state = graph.invoke(initial_state, config=config)
    return final_state
