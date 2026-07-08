"""
agents/writer.py — Writer sub-agent node.

RESPONSIBILITY (single):
    Take all subtask results and format them into the final user-facing output
    in the requested format (markdown, JSON, bullet points, plain text).
    Also uses write_file tool to save the output to the workspace.

NODE CONTRACT:
    Input:  AgentState with 'subtask_results', 'original_task', 'output_format'
    Output: Partial state dict setting 'final_output', 'aggregated_content'
"""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agents.providers import get_llm_with_fallback
from memory.short_term import make_step
from schemas.agent_state import AgentState
from schemas.task import OutputFormat, SubtaskResult
from tools.file_tool import write_file

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a Writer Agent. Your job is to produce the final, polished output.

Given:
- The original task from the user
- Summaries and findings from research
- A required output format

You must produce a complete, well-structured final document.

Rules:
- Write for the end user — clear, professional, direct
- Include all important facts and figures from the research
- Do NOT add information not present in the summaries
- Match the exact output format requested
- For markdown: use headers, bold, bullet points appropriately
- For JSON: return valid JSON only, no surrounding text
- For bullet: use bullet points only, no paragraphs
- For text: plain prose, no markdown symbols

Return only the final output document. No preamble, no meta-commentary.
"""


async def writer_node(state: AgentState) -> dict:
    """LangGraph node for the Writer sub-agent."""
    start_time = time.time()
    task = state.get("original_task", "")
    output_format = state.get("output_format", OutputFormat.MARKDOWN)
    subtask_results: list[SubtaskResult] = state.get("subtask_results", [])

    logger.info("Writer node started", format=output_format, results_count=len(subtask_results))

    step = make_step(state, "WRITER", f"Formatting final output as {output_format}")

    try:
        # Aggregate all successful subtask outputs into one input block
        successful_results = [r for r in subtask_results if r.success and r.output]

        if not successful_results:
            # Nothing to write — return a graceful fallback
            fallback = "No research results were successfully gathered. Please try again with a more specific task."
            return {
                "final_output": fallback,
                "aggregated_content": fallback,
                "agent_steps": [step],
                "steps_taken": state.get("steps_taken", 0) + 1,
            }

        # Build context from all sub-agent results
        research_context = "\n\n---\n\n".join([
            f"[{r.agent_name.upper()} — {r.subtask}]\n{r.output}"
            for r in successful_results
        ])

        # Tell the LLM exactly what format to produce
        format_instruction = {
            OutputFormat.MARKDOWN: "Format: Markdown with headers (##), bold (**), and bullet points (-)",
            OutputFormat.JSON:     "Format: Valid JSON object only. No markdown, no surrounding text.",
            OutputFormat.BULLET:   "Format: Bullet points only (- item). No headers, no paragraphs.",
            OutputFormat.TEXT:     "Format: Plain text paragraphs. No markdown symbols.",
        }.get(output_format, "Format: Markdown")

        llm = get_llm_with_fallback(temperature=0.3)  # Higher temp = more natural writing

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Original task: {task}\n\n"
                f"{format_instruction}\n\n"
                f"Research and summaries:\n{research_context}\n\n"
                f"Write the final output now."
            ))
        ]

        response = await llm.ainvoke(messages)
        final_output = response.content.strip()

        # Optionally save output to file workspace for later retrieval
        try:
            safe_name = "".join(c if c.isalnum() else "_" for c in task[:30])
            write_file.invoke({
                "filename": f"outputs/{safe_name}.md",
                "content": final_output,
                "append": False,
            })
        except Exception:
            pass  # File write failure is non-critical

        duration_ms = int((time.time() - start_time) * 1000)
        tokens = getattr(response, "usage_metadata", {})
        tokens_used = tokens.get("total_tokens", 0) if tokens else 0

        step.duration_ms = duration_ms
        step.metadata = {"output_length": len(final_output), "format": str(output_format)}

        logger.info("Writer node complete", output_length=len(final_output), duration_ms=duration_ms)

        return {
            "final_output": final_output,
            "aggregated_content": research_context,
            "agent_steps": [step],
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    except Exception as e:
        logger.error("Writer node failed", error=str(e))
        return {
            "final_output": None,
            "agent_steps": [step],
            "errors": [f"Writer error: {str(e)}"],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }
