"""
schemas/agent_state.py — LangGraph AgentState TypedDict.

WHY TypedDict AND NOT BaseModel?
    LangGraph requires its state to be a TypedDict (or dataclass).
    It internally does shallow merges of state updates — it takes whatever
    dict a node returns and merges it into the current state.
    
    BaseModel is heavier (validation overhead on every node transition)
    and LangGraph doesn't natively support it as state type.
    TypedDict is pure Python typing — zero runtime cost.

WHAT IS Annotated[list, operator.add]?
    By default, LangGraph state merge REPLACES a field.
    If node A sets messages=["hello"] and node B sets messages=["world"],
    the final state has messages=["world"] — A's value is lost.
    
    Annotating with operator.add tells LangGraph to APPEND instead of replace.
    This is how message history and step logs accumulate correctly.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from schemas.task import AgentStep, EvidenceChunk, OutputFormat, SubtaskResult


class AgentState(TypedDict, total=False):
    """
    The shared state dictionary that flows through every LangGraph node.
    
    `total=False` means ALL fields are optional in the TypedDict.
    This is required because each node only updates the fields it touches —
    the rest keep their previous values. Without total=False, mypy would
    complain that we're not providing every field in every node's return dict.
    
    FIELD GROUPS:
    - Input fields: set once at the start, never modified
    - Planning fields: set by the PLAN node
    - Execution fields: updated by each sub-agent node
    - Control fields: used by the ROUTE node for loop control
    - Output fields: set by AGGREGATE and VALIDATE nodes
    """

    # ── Input (set once, read-only after) ─────────────────────────────────────
    task_id: str                      # UUID linking this run to the DB record
    original_task: str                # The raw user task string
    output_format: OutputFormat       # Desired output format
    user_context: str | None          # Optional extra context from user

    # ── Planning (set by PLAN node) ────────────────────────────────────────────
    plan: list[str]                   # Ordered list of subtask strings
    total_subtasks: int               # len(plan) — cached for convenience

    # ── Execution (accumulated across sub-agent nodes) ─────────────────────────
    # Annotated[list, operator.add] = append-only, never replace
    subtask_results: Annotated[list[SubtaskResult], operator.add]
    evidence_chunks: Annotated[list[EvidenceChunk], operator.add]

    # ── Control Flow (used by ROUTE node) ──────────────────────────────────────
    current_subtask_index: int        # Which plan step we're on (0-indexed)
    current_subtask: str              # The actual subtask text for the current step
    steps_taken: int                  # Total node executions (guards against loops)
    errors: Annotated[list[str], operator.add]  # Error log — append only

    # ── Long-term Memory ───────────────────────────────────────────────────────
    # Retrieved at the start from FAISS — similar past task summaries
    retrieved_memories: list[str]

    # ── Agent Step Log (streamed to frontend) ──────────────────────────────────
    agent_steps: Annotated[list[AgentStep], operator.add]

    # ── Output (set by AGGREGATE + VALIDATE nodes) ─────────────────────────────
    aggregated_content: str           # Raw combined output before formatting
    final_output: str | None          # Final formatted output — None until done
    confidence_score: float           # 0.0-1.0, set by VALIDATE node
    total_tokens_used: int            # Running sum across all LLM calls

    # ── Termination ────────────────────────────────────────────────────────────
    is_complete: bool                 # Set True by VALIDATE or on max_steps hit
    termination_reason: str           # "completed" | "max_steps" | "error"
