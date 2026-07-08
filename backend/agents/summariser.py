"""
agents/summariser.py — Summariser sub-agent node.

RESPONSIBILITY (single):
    Take raw evidence chunks from the Researcher and compress them into a
    structured, coherent summary. No tool calls needed — this is pure LLM
    reasoning on the evidence already gathered.

NODE CONTRACT:
    Input:  AgentState with 'evidence_chunks' and 'current_subtask' set
    Output: Partial state dict updating 'subtask_results', 'agent_steps'
"""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agents.providers import get_llm_with_fallback
from memory.short_term import make_step
from schemas.agent_state import AgentState
from schemas.task import EvidenceChunk, SubtaskResult

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a Summariser Agent. Your job is to compress raw evidence into structured insights.

Given a subtask and a list of evidence chunks, you must:
1. Identify the key facts, figures, and claims
2. Remove redundancy across sources
3. Preserve specific details (names, numbers, dates)
4. Structure the output clearly

Respond with a JSON object in this exact format:
{
  "summary": "A well-structured 2-4 paragraph summary of the evidence",
  "key_points": ["point 1", "point 2", "point 3"],
  "confidence": 0.0-1.0,
  "note": "Any caveats about evidence quality or gaps"
}

Confidence scoring guide:
- 0.9-1.0: Multiple corroborating sources, specific facts
- 0.7-0.9: Single good source, mostly specific
- 0.5-0.7: Limited or vague evidence
- Below 0.5: Very poor evidence, mostly inferences
"""


async def summariser_node(state: AgentState) -> dict:
    """LangGraph node for the Summariser sub-agent."""
    start_time = time.time()
    subtask = state.get("current_subtask", "")
    evidence_chunks: list[EvidenceChunk] = state.get("evidence_chunks", [])

    logger.info("Summariser node started", subtask=subtask[:60], evidence_count=len(evidence_chunks))

    step = make_step(state, "SUMMARISER", f"Summarising {len(evidence_chunks)} evidence chunks for: {subtask[:60]}")

    try:
        # Format evidence for the LLM — numbered list for clarity
        if evidence_chunks:
            evidence_text = "\n\n".join([
                f"[Source {i+1}: {chunk.source} | Relevance: {chunk.relevance_score:.2f}]\n{chunk.content}"
                for i, chunk in enumerate(evidence_chunks)
            ])
        else:
            evidence_text = "No evidence chunks available. Summarise based on the subtask description only."

        llm = get_llm_with_fallback(temperature=0.2)  # Slightly more temperature for writing

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Subtask: {subtask}\n\n"
                f"Evidence gathered:\n{evidence_text}\n\n"
                f"Produce the structured summary now."
            ))
        ]

        response = await llm.ainvoke(messages)
        content = response.content

        summary_text, key_points, confidence, note = _parse_summariser_response(content)

        duration_ms = int((time.time() - start_time) * 1000)
        tokens = getattr(response, "usage_metadata", {})
        tokens_used = tokens.get("total_tokens", 0) if tokens else 0

        # Build full output string for the Writer to receive
        formatted_output = summary_text
        if key_points:
            formatted_output += "\n\nKey Points:\n" + "\n".join(f"• {p}" for p in key_points)
        if note:
            formatted_output += f"\n\nNote: {note}"

        result = SubtaskResult(
            agent_name="summariser",
            subtask=subtask,
            output=formatted_output,
            evidence=evidence_chunks,
            success=True,
            tokens_used=tokens_used,
        )

        step.duration_ms = duration_ms
        step.metadata = {"confidence": confidence, "key_points_count": len(key_points)}

        logger.info("Summariser node complete", confidence=confidence, duration_ms=duration_ms)

        return {
            "subtask_results": [result],
            "agent_steps": [step],
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    except Exception as e:
        logger.error("Summariser node failed", error=str(e))
        error_result = SubtaskResult(
            agent_name="summariser",
            subtask=subtask,
            output="",
            success=False,
            error=f"Summariser failed: {str(e)}",
        )
        return {
            "subtask_results": [error_result],
            "agent_steps": [step],
            "errors": [f"Summariser error: {str(e)}"],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


def _parse_summariser_response(content: str) -> tuple[str, list[str], float, str]:
    """Parse summariser JSON response. Returns (summary, key_points, confidence, note)."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:-1])

    try:
        data = json.loads(cleaned)
        return (
            data.get("summary", content[:500]),
            data.get("key_points", []),
            float(data.get("confidence", 0.6)),
            data.get("note", ""),
        )
    except json.JSONDecodeError:
        # Fallback: treat raw content as the summary
        return content[:1000], [], 0.5, "Summary format was unstructured"
