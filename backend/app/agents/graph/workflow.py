"""
LangGraph workflow definition for FieldMind AI Intake & State Management.

Implements STORY 4:
- Supports both TEXT and VOICE modalities.
- Manages initial intake state creation, state transitions, validation, and error boundaries.
- Executes Whisper audio transcription handoff for voice requests.
- Integrates with checkpoint persistence and state recovery.
"""
import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.graph.checkpoints import get_memory_checkpointer
from app.agents.graph.state import (
    FieldMindWorkflowState,
    InputType,
    IntakeStatus,
    VoiceProcessingStatus,
    create_initial_intake_state,
)
from app.agents.intake.intent import prepare_intent_diagnostics
from app.agents.intake.text import process_text_intake
from app.agents.intake.voice import initialize_voice_intake, transcribe_voice

logger = logging.getLogger(__name__)


def initial_router_node(state: FieldMindWorkflowState) -> dict[str, Any]:
    """
    Evaluate incoming state and determine the modality routing path.

    Validates that:
    - job_id is present and non-empty.
    - input_type is recognized (TEXT or VOICE).
    """
    job_id = state.get("job_id")
    input_type = state.get("input_type")
    errors: list[str] = list(state.get("errors", []))

    if not job_id or not str(job_id).strip():
        msg = "Missing or empty job_id in intake state"
        logger.error(msg)
        errors.append(msg)

    # Validate input type
    val = input_type.value if hasattr(input_type, "value") else str(input_type or "")
    normalized_type = val.split(".")[-1].upper().strip() if input_type else None
    if normalized_type not in {InputType.TEXT.value, InputType.VOICE.value}:
        msg = f"Unrecognized input_type '{input_type}'. Must be TEXT or VOICE."
        logger.error(msg)
        errors.append(msg)

    if errors:
        return {
            "status": IntakeStatus.FAILED.value,
            "current_step": "INTAKE_VALIDATION_FAILED",
            "errors": errors,
        }

    return {
        "input_type": normalized_type,
        "status": IntakeStatus.PROCESSING.value,
        "current_step": "INPUT_TYPE_ROUTED",
        "errors": [],
    }


def handle_workflow_failure(state: FieldMindWorkflowState) -> dict[str, Any]:
    """Capture and record workflow failure state cleanly."""
    errors = state.get("errors", [])
    logger.error("LangGraph intake workflow captured failure: %s", errors)
    return {
        "status": IntakeStatus.FAILED.value,
        "current_step": "WORKFLOW_FAILED",
    }


# Routing Condition Functions
def route_by_input_type(state: FieldMindWorkflowState) -> str:
    """Branch from initial router to TEXT, VOICE, or error handling."""
    if state.get("errors") or state.get("status") in {IntakeStatus.FAILED, IntakeStatus.FAILED.value}:
        return "workflow_failure"

    input_type = str(state.get("input_type", "")).upper()
    if input_type == InputType.TEXT.value:
        return "process_text"
    elif input_type == InputType.VOICE.value:
        return "initialize_voice"
    return "workflow_failure"


def route_after_text(state: FieldMindWorkflowState) -> str:
    """Route text processing to intent handoff or failure."""
    if state.get("errors") or state.get("status") in {IntakeStatus.FAILED, IntakeStatus.FAILED.value}:
        return "workflow_failure"
    return "intent_handoff"


def route_after_voice_init(state: FieldMindWorkflowState) -> str:
    """Route to Whisper transcription if voice initialization succeeded."""
    voice_state = state.get("voice_state") or {}
    if (
        state.get("errors")
        or state.get("status") in {IntakeStatus.FAILED, IntakeStatus.FAILED.value}
        or voice_state.get("status") in {VoiceProcessingStatus.FAILED, VoiceProcessingStatus.FAILED.value}
    ):
        return "workflow_failure"
    return "transcribe_voice"


def route_after_transcription(state: FieldMindWorkflowState) -> str:
    """Route transcribed audio to intent handoff or failure."""
    voice_state = state.get("voice_state") or {}
    if (
        state.get("errors")
        or state.get("status") in {IntakeStatus.FAILED, IntakeStatus.FAILED.value}
        or voice_state.get("status") in {VoiceProcessingStatus.FAILED, VoiceProcessingStatus.FAILED.value}
    ):
        return "workflow_failure"
    return "intent_handoff"


def build_intake_workflow(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """
    Construct and compile the full LangGraph intake workflow supporting
    both Text and Voice requests with persistent checkpointing.

    Topology:
        START -> initial_router ────┬──> [TEXT]  ──> process_text ──┬──> intent_handoff ──> END
                                    │                               │
                                    ├──> [VOICE] ──> init_voice ────┤
                                    │                      │        │
                                    │                      ▼        │
                                    │               transcribe ─────┤
                                    │                               │
                                    └──> [ERROR] ──> workflow_failure ────────────────────> END
    """
    workflow = StateGraph(FieldMindWorkflowState)

    # Register workflow nodes
    workflow.add_node("initial_router", initial_router_node)
    workflow.add_node("process_text", process_text_intake)
    workflow.add_node("initialize_voice", initialize_voice_intake)
    workflow.add_node("transcribe_voice", transcribe_voice)
    workflow.add_node("intent_handoff", prepare_intent_diagnostics)
    workflow.add_node("workflow_failure", handle_workflow_failure)

    # Define edges & transitions
    workflow.add_edge(START, "initial_router")

    workflow.add_conditional_edges(
        "initial_router",
        route_by_input_type,
        {
            "process_text": "process_text",
            "initialize_voice": "initialize_voice",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_conditional_edges(
        "process_text",
        route_after_text,
        {
            "intent_handoff": "intent_handoff",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_conditional_edges(
        "initialize_voice",
        route_after_voice_init,
        {
            "transcribe_voice": "transcribe_voice",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_conditional_edges(
        "transcribe_voice",
        route_after_transcription,
        {
            "intent_handoff": "intent_handoff",
            "workflow_failure": "workflow_failure",
        },
    )

    workflow.add_edge("intent_handoff", END)
    workflow.add_edge("workflow_failure", END)

    return workflow.compile(checkpointer=checkpointer)


# Default compiled intake workflow with in-memory checkpointer
intake_workflow = build_intake_workflow(checkpointer=get_memory_checkpointer())


def run_intake_workflow(
    job_id: str | None = None,
    input_type: InputType | str | None = None,
    request_text: str | None = None,
    audio_ref: str | None = None,
    customer_id: str | None = None,
    customer_info: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> FieldMindWorkflowState:
    """
    Entrypoint function creating the initial state and executing the intake workflow.

    Args:
        job_id: Unique job / request ID (auto-generated if None).
        input_type: TEXT or VOICE.
        request_text: Raw customer query for text requests.
        audio_ref: Storage reference or URL for voice audio notes.
        customer_id: Identifier of the requesting customer.
        customer_info: Customer contact dictionary.
        metadata: Request context metadata.
        checkpointer: Optional custom LangGraph checkpointer.

    Returns:
        The resulting FieldMindWorkflowState after complete workflow execution.
    """
    initial_state = create_initial_intake_state(
        job_id=job_id,
        input_type=input_type,
        request_text=request_text,
        audio_ref=audio_ref,
        customer_id=customer_id,
        customer_info=customer_info,
        metadata=metadata,
    )

    active_graph = build_intake_workflow(checkpointer=checkpointer) if checkpointer else intake_workflow
    config = {"configurable": {"thread_id": f"job-{initial_state['job_id']}"}}

    final_state = active_graph.invoke(initial_state, config=config)
    return final_state


def run_voice_intake_workflow(
    job_id: str,
    media_ref: str,
    customer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> FieldMindWorkflowState:
    """Backwards-compatible convenience wrapper for voice-only executions."""
    return run_intake_workflow(
        job_id=job_id,
        input_type=InputType.VOICE,
        audio_ref=media_ref,
        customer_id=customer_id,
        metadata=metadata,
        checkpointer=checkpointer,
    )
