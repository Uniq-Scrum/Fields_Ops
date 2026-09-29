"""
LangGraph checkpoint persistence provider.

Supports in-memory checkpointing for development and testing, with extensible
bindings for PostgreSQL checkpoint persistence.
"""
from typing import Any
from langgraph.checkpoint.memory import MemorySaver


def get_memory_checkpointer() -> MemorySaver:
    """Return an in-memory checkpointer suitable for workflow testing and transient execution."""
    return MemorySaver()
