"""
agents/orchestrator.py — The LangGraph StateGraph supervisor orchestrator.

This file defines the complete agent workflow as an explicit graph.
Every node, every edge, every routing decision is visible here.

GRAPH STRUCTURE:
    memory_load → plan → route ──▶ researcher → summariser ─┐
                           ▲                                 │
                           └─────────────────────────────────┘
                                    (loop for each subtask)
                  route ──▶ writer → validate → END

NODES:
    memory_load  — retrieve similar past tasks from FAISS
    plan         — LLM breaks task into ordered subtask list
    route        — pure Python: decides researcher loop vs writer vs end
    researcher   — gathers evidence (web search + memory retrieval)
    summariser   — compresses evidence into structured summary
    writer       — formats final output in requested format
    validate     — quality check, sets confidence score, marks complete
"""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from agents.providers import get_llm_with_fallback
from agents.researcher import researcher_node
from agents.summariser import summariser_node
from agents.writer import writer_node
from config import settings
from memory.long_term import LongTermMemory
from memory.short_term import make_step
from schemas.agent_state import AgentState
from schemas.task import AgentStep

logger = structlog.get_logger(__name__)

# Module-level memory store — shared across all runs
_memory_store: LongTermMemory | None = None


def get_memory_store() -> LongTermMemory:
    global _memory_store
    if _memory_store is None:
        _memory_store = LongTermMemory()
    return _memory_store


# ── NODE 1: Memory Load ────────────────────────────────────────────────────────

async def memory_load_node(state: AgentState) -> dict:
    """
    Retrieve similar past task summaries from FAISS long-term memory.
    
    These are injected into the PLAN node's system prompt so the orchestrator
    LLM knows "we've done something similar before — here's what we found."
    This is what makes the agent smarter over time.
    """
    task = state.get("original_task", "")
    step = make_step(state, "MEMORY_LOAD", "Retrieving relevant memories from past tasks")

    try:
        store = get_memory_store()
        memories = store.retrieve(query=task, top_k=3)
        memory_texts = [text for text, score in memories if score > 0.4]

        logger.info("Memory load complete", memories_found=len(memory_texts))

        return {
            "retrieved_memories": memory_texts,
            "agent_steps": [step],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }
    except Exception as e:
        logger.warning("Memory load failed (non-critical)", error=str(e))
        return {
            "retrieved_memories": [],
            "agent_steps": [step],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


# ── NODE 2: Plan ───────────────────────────────────────────────────────────────

PLAN_SYSTEM_PROMPT = """You are an AI Orchestrator. Your job is to break down a user task
into a clear, ordered list of research subtasks.

Rules:
- Maximum 4 subtasks (keep scope tight)
- Each subtask must be independently executable by a researcher
- Subtasks must be ordered logically (gather info before synthesising)
- Be specific — vague subtasks produce vague results
- Do NOT include writing/formatting as a subtask (that is handled separately)

If relevant past context is provided, use it to avoid redundant research.

Respond ONLY with a JSON object:
{
  "plan": [
    "Subtask 1: specific research question",
    "Subtask 2: specific research question"
  ],
  "reasoning": "One sentence explaining your planning approach"
}"""


async def plan_node(state: AgentState) -> dict:
    """
    The LLM writes an execution plan — an ordered list of research subtasks.
    
    This is the core of the "supervisor pattern": the supervisor (this node)
    decides WHAT needs to be done before any sub-agent does any work.
    """
    task = state.get("original_task", "")
    memories = state.get("retrieved_memories", [])
    step = make_step(state, "PLAN", f"Creating execution plan for: {task[:60]}")

    try:
        # Inject past memories if we have them
        memory_context = ""
        if memories:
            memory_context = (
                "\n\nRelevant context from past tasks:\n" +
                "\n---\n".join(memories[:3])
            )

        user_context = state.get("user_context") or ""
        context_block = f"\nAdditional user context: {user_context}" if user_context else ""

        llm = get_llm_with_fallback(temperature=0.1)

        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Task: {task}"
                f"{context_block}"
                f"{memory_context}"
                f"\n\nCreate the research plan now."
            ))
        ]

        response = await llm.ainvoke(messages)
        plan, reasoning = _parse_plan_response(response.content, task)

        tokens = getattr(response, "usage_metadata", {})
        tokens_used = tokens.get("total_tokens", 0) if tokens else 0

        step.metadata = {"plan": plan, "reasoning": reasoning, "subtask_count": len(plan)}
        logger.info("Plan created", subtask_count=len(plan), reasoning=reasoning)

        return {
            "plan": plan,
            "total_subtasks": len(plan),
            "current_subtask_index": 0,
            "agent_steps": [step],
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    except Exception as e:
        logger.error("Plan node failed", error=str(e))
        # Fallback: treat the whole task as one subtask
        fallback_plan = [task]
        return {
            "plan": fallback_plan,
            "total_subtasks": 1,
            "current_subtask_index": 0,
            "agent_steps": [step],
            "errors": [f"Planning failed, using fallback: {str(e)}"],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


def _parse_plan_response(content: str, task: str) -> tuple[list[str], str]:
    """Parse the PLAN node's JSON response. Falls back gracefully."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:-1])
    try:
        data = json.loads(cleaned)
        plan = data.get("plan", [])
        reasoning = data.get("reasoning", "")
        # Clamp to max 4 subtasks regardless of what LLM returns
        plan = [str(p) for p in plan[:4] if p]
        if not plan:
            plan = [task]
        return plan, reasoning
    except json.JSONDecodeError:
        logger.warning("Plan response was not JSON, using task as single subtask")
        return [task], "Fallback: single subtask plan"


# ── NODE 3: Route (Conditional Edge Function) ──────────────────────────────────

async def route_node(state: AgentState) -> dict:
    """
    Update state to point to the next subtask.
    
    IMPORTANT DISTINCTION:
    - route_node (this function) is a NODE — it updates state
    - routing_function (below) is the CONDITIONAL EDGE — it returns a string
    
    We need both because:
    1. The node sets current_subtask = plan[next_index] in state
    2. The edge reads state and returns which node to run next
    
    The node runs first, updates state, then the edge reads the updated state.
    """
    index = state.get("current_subtask_index", 0)
    plan = state.get("plan", [])

    # Advance to the next subtask after first pass
    # On first entry index=0 is already set by plan_node, so we only increment on re-entry
    # We detect re-entry by checking if current_subtask is already set to plan[index]
    current = state.get("current_subtask", "")
    if current and plan and index < len(plan) and current == plan[index]:
        # We've already processed this subtask — advance the index
        index = index + 1

    step = make_step(state, "ROUTE", f"Routing: subtask {index+1}/{state.get('total_subtasks', 1)}")

    if index < len(plan):
        next_subtask = plan[index]
        logger.info("Route: next subtask", index=index, subtask=next_subtask[:60])
        return {
            "current_subtask_index": index,
            "current_subtask": next_subtask,
            "agent_steps": [step],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }
    else:
        # All subtasks processed — signal completion
        logger.info("Route: all subtasks complete, moving to writer")
        return {
            "current_subtask_index": index,
            "agent_steps": [step],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


def routing_function(state: AgentState) -> str:
    """
    CONDITIONAL EDGE FUNCTION — returns the NAME of the next node.
    
    This is NOT a node. LangGraph calls this function after route_node
    completes, reads the return string, and routes to that node.
    
    Return values must match keys in add_conditional_edges() path_map.
    
    LOOP GUARD: steps_taken >= max_agent_steps forces exit.
    Without this, a bug in subtask tracking could loop forever.
    """
    steps_taken = state.get("steps_taken", 0)
    index = state.get("current_subtask_index", 0)
    total = state.get("total_subtasks", 1)
    is_complete = state.get("is_complete", False)

    # Hard loop guard — always check this first
    if steps_taken >= settings.max_agent_steps:
        logger.warning("Max steps reached, forcing exit", steps=steps_taken)
        return "writer"

    if is_complete:
        return "__end__"

    # If index is still within plan bounds, more subtasks to process
    plan = state.get("plan", [])
    if index < len(plan):
        return "researcher"
    else:
        return "writer"


# ── NODE 4: Validate ───────────────────────────────────────────────────────────

VALIDATE_SYSTEM_PROMPT = """You are a Quality Validator. Assess whether the output adequately answers the original task.

Score the output on:
1. Completeness: Does it address all aspects of the task? (0-1)
2. Accuracy: Are claims specific and sourced? (0-1)  
3. Clarity: Is it well-structured and readable? (0-1)

Respond ONLY with JSON:
{
  "confidence": 0.0-1.0,
  "completeness": 0.0-1.0,
  "accuracy": 0.0-1.0,
  "clarity": 0.0-1.0,
  "feedback": "One sentence on quality"
}"""


async def validate_node(state: AgentState) -> dict:
    """
    Quality gate — assesses the final output and sets confidence_score.
    
    If confidence < threshold: the output is still returned but flagged.
    We never silently return low-quality output as if it were good.
    
    LLM-as-a-Judge pattern: using an LLM to evaluate another LLM's output.
    This is a well-established eval technique in production LLM systems.
    """
    final_output = state.get("final_output", "")
    task = state.get("original_task", "")
    step = make_step(state, "VALIDATE", "Running quality validation on final output")

    # If no output exists, fail immediately
    if not final_output:
        logger.warning("Validate: no output to validate")
        return {
            "confidence_score": 0.0,
            "is_complete": True,
            "termination_reason": "error_no_output",
            "agent_steps": [step],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    try:
        llm = get_llm_with_fallback(temperature=0.0)  # 0 temp for consistent scoring

        messages = [
            SystemMessage(content=VALIDATE_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Original task: {task}\n\n"
                f"Output to validate:\n{final_output[:2000]}\n\n"
                f"Score this output now."
            ))
        ]

        response = await llm.ainvoke(messages)
        confidence, feedback = _parse_validate_response(response.content)

        tokens = getattr(response, "usage_metadata", {})
        tokens_used = tokens.get("total_tokens", 0) if tokens else 0

        termination = "completed" if confidence >= settings.confidence_threshold else "low_confidence"
        step.metadata = {"confidence": confidence, "feedback": feedback}

        logger.info(
            "Validation complete",
            confidence=confidence,
            threshold=settings.confidence_threshold,
            termination=termination,
        )

        return {
            "confidence_score": confidence,
            "is_complete": True,
            "termination_reason": termination,
            "agent_steps": [step],
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    except Exception as e:
        logger.error("Validate node failed", error=str(e))
        return {
            "confidence_score": 0.5,   # Assume moderate confidence on validator failure
            "is_complete": True,
            "termination_reason": "validator_error",
            "agent_steps": [step],
            "errors": [f"Validator error: {str(e)}"],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


def _parse_validate_response(content: str) -> tuple[float, str]:
    """Parse validator JSON response. Returns (confidence, feedback)."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:-1])
    try:
        data = json.loads(cleaned)
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp to valid range
        feedback = data.get("feedback", "")
        return confidence, feedback
    except (json.JSONDecodeError, ValueError):
        return 0.5, "Validator returned unstructured response"


# ── BUILD THE GRAPH ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Construct and compile the full LangGraph StateGraph.
    
    Called once at application startup — the compiled graph is reused
    for every task run. Compilation validates the graph structure
    (checks for disconnected nodes, missing edges, etc.)
    
    Returns the compiled runnable — call .ainvoke(state) to run a task.
    """
    # StateGraph(AgentState) tells LangGraph what TypedDict our state is
    # It uses this for type checking and for the operator.add merge logic
    graph = StateGraph(AgentState)

    # ── Register all nodes ────────────────────────────────────────────────────
    # add_node(name, function) — name is what routing_function returns
    graph.add_node("memory_load", memory_load_node)
    graph.add_node("plan",        plan_node)
    graph.add_node("route",       route_node)
    graph.add_node("researcher",  researcher_node)
    graph.add_node("summariser",  summariser_node)
    graph.add_node("writer",      writer_node)
    graph.add_node("validate",    validate_node)

    # ── Set entry point ───────────────────────────────────────────────────────
    # This is the first node executed after graph.ainvoke() is called
    graph.set_entry_point("memory_load")

    # ── Simple (unconditional) edges ──────────────────────────────────────────
    # These always run in sequence — no branching
    graph.add_edge("memory_load", "plan")
    graph.add_edge("plan",        "route")
    graph.add_edge("researcher",  "summariser")

    # After summariser completes, always go back to route
    # route_node will increment the index and routing_function decides what's next
    graph.add_edge("summariser",  "route")

    # Writer always leads to validate
    graph.add_edge("writer",      "validate")

    # Validate leads to END (the graph's terminal state)
    graph.add_edge("validate",    END)

    # ── Conditional edge ──────────────────────────────────────────────────────
    # After route_node runs, call routing_function(state) to get next node name
    # The path_map translates return strings → actual node names
    graph.add_conditional_edges(
        "route",              # FROM: after route_node runs
        routing_function,     # CALL: this function with state, get a string back
        {                     # MAP: string → node name (or END)
            "researcher": "researcher",
            "writer":     "writer",
            "__end__":    END,
        }
    )

    # compile() validates graph structure and returns the runnable
    # checkpoint=None means no persistence between steps (we handle this via SQLite)
    compiled = graph.compile()

    logger.info("LangGraph StateGraph compiled successfully")
    return compiled


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

# Singleton compiled graph — built once at import time
# All calls to run_task() reuse this same compiled graph object
_graph = None


def get_graph():
    """Lazy singleton for the compiled graph."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_task(state: AgentState) -> AgentState:
    """
    Public entry point — run a complete task through the graph.
    
    Args:
        state: Initial AgentState from create_initial_state()
    
    Returns:
        Final AgentState after all nodes have run.
    
    This is what main.py calls from its background task.
    The result is then written to SQLite for the client to poll.
    """
    graph = get_graph()
    logger.info("Graph run started", task_id=state.get("task_id"))

    # ainvoke() runs the entire graph asynchronously
    # Returns the FINAL state after the graph reaches END
    final_state = await graph.ainvoke(state)

    # After task completes — write summary to long-term memory
    # This is what makes the system smarter over time
    try:
        _write_to_memory(final_state)
    except Exception as e:
        logger.warning("Memory write after task failed (non-critical)", error=str(e))

    logger.info(
        "Graph run complete",
        task_id=state.get("task_id"),
        confidence=final_state.get("confidence_score", 0),
        steps=final_state.get("steps_taken", 0),
    )

    return final_state


def _write_to_memory(state: AgentState) -> None:
    """
    After a successful task, embed the task + output into long-term memory.
    
    We store: original_task + final_output (truncated)
    We retrieve by: semantic similarity to new task queries
    
    WHY TRUNCATE?
        Embedding models have token limits. More importantly, shorter, denser
        summaries retrieve better than full outputs — quality over quantity.
    """
    task = state.get("original_task", "")
    output = state.get("final_output", "")
    task_id = state.get("task_id", "unknown")
    confidence = state.get("confidence_score", 0.0)

    # Only store high-confidence outputs — don't poison memory with bad results
    if not output or confidence < settings.confidence_threshold:
        logger.info("Skipping memory write (low confidence or no output)", confidence=confidence)
        return

    # Compose the text to embed — task + key findings
    # Keep it under ~500 tokens for embedding quality
    memory_text = f"Task: {task}\n\nFindings: {output[:800]}"

    store = get_memory_store()
    store.write(
        text=memory_text,
        task_id=task_id,
        summary=f"{task[:80]}...",
    )
