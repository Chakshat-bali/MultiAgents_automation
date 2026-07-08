"""
agents/researcher.py — Researcher sub-agent node.

RESPONSIBILITY (single):
    Given a subtask string, gather raw evidence from web search and/or
    memory retrieval. Return structured evidence chunks. Do NOT summarise.
    Summarisation is the Summariser's job.

WHY SINGLE RESPONSIBILITY MATTERS FOR AGENTS:
    If the Researcher also summarised, a search failure would kill both
    capabilities. Separation means failures are isolated and each agent
    can be tested, replaced, or scaled independently.

NODE CONTRACT:
    Input:  AgentState with 'current_subtask' set
    Output: Partial AgentState dict updating 'subtask_results',
            'evidence_chunks', 'agent_steps', 'total_tokens_used'
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agents.providers import get_llm_with_fallback, get_llm_with_tools_and_fallback
from memory.short_term import make_step
from schemas.agent_state import AgentState
from schemas.task import AgentStep, EvidenceChunk, SubtaskResult
from tools.file_tool import read_file, write_file
from tools.retriever_tool import retrieve_from_memory
from tools.search_tool import web_search
from tools.apify_tool import apify_google_search, apify_g2_reviews, apify_scrape_page
from tools.crunchbase_tool import crunchbase_company_info, crunchbase_recent_funding
from tools.slack_tool import send_slack_digest
from tools.email_tool import send_email_digest

logger = structlog.get_logger(__name__)

# Tools this agent can use — passed to .bind_tools()
# CI tools added so researcher can scrape G2, Crunchbase, and send Slack digests
RESEARCHER_TOOLS = [
    web_search,
    retrieve_from_memory,
    read_file,
    apify_google_search,
    apify_g2_reviews,
    apify_scrape_page,
    crunchbase_company_info,
    crunchbase_recent_funding,
    send_slack_digest,
    send_email_digest,
]

# Create a mapping of tool names to functions for easy lookup in the node
TOOL_MAP = {t.name: t for t in RESEARCHER_TOOLS}

SYSTEM_PROMPT = """You are a Research Agent. Your only job is to GATHER EVIDENCE.

Given a research subtask, you must:
1. Decide whether to search the web, search memory, or both
2. Call the appropriate tools to gather information
3. Return ALL relevant findings as structured evidence

Rules:
- Gather facts, do NOT summarise or interpret yet
- Use web_search for current/external information
- Use retrieve_from_memory for information from past tasks
- If web_search fails, try retrieve_from_memory as fallback
- Always call at least one tool — do not answer from your training data alone
- Be thorough: gather more evidence than you think you need

After gathering, respond with a JSON object in this exact format:
{
  "evidence": [
    {
      "source": "URL or 'memory' or 'file:filename'",
      "content": "The relevant text excerpt",
      "relevance_score": 0.0-1.0
    }
  ],
  "summary": "One sentence: what you found and from where",
  "tokens_used": 0
}
"""


async def researcher_node(state: AgentState) -> dict:
    """
    LangGraph node function for the Researcher sub-agent.
    
    This is an async function because LLM calls are I/O-bound —
    using async lets other tasks run while we wait for the API response.
    
    Args:
        state: Current AgentState — we read 'current_subtask' from it.
    
    Returns:
        Partial state dict — LangGraph merges this into the full state.
    """
    start_time = time.time()
    subtask = state.get("current_subtask", "")
    task_id = state.get("task_id", "unknown")

    logger.info("Researcher node started", subtask=subtask[:60], task_id=task_id)

    step = make_step(state, "RESEARCHER", f"Researching: {subtask[:80]}")

    try:
        # get_llm_with_tools_and_fallback binds tools on BOTH providers
        # and wraps with .with_fallbacks() — if Groq 429s, Gemini takes over
        llm_with_tools = get_llm_with_tools_and_fallback(RESEARCHER_TOOLS, temperature=0.1)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Research subtask: {subtask}\n\nGather evidence now.")
        ]

        # ainvoke() = async invoke — awaits the LLM response
        response = await llm_with_tools.ainvoke(messages)

        # --- Tool call handling ---
        # If the LLM decided to call tools, response.tool_calls will be non-empty.
        # We execute each tool call and feed results back to the LLM.
        tool_results = []

        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                logger.info("Tool call", tool=tool_name, args=str(tool_args)[:100])

                # Dynamically route to the correct tool function using TOOL_MAP
                tool_func = TOOL_MAP.get(tool_name)
                if tool_func:
                    # tool.invoke() is synchronous, which is fine for these tools
                    # but if they were async, we'd use await tool.ainvoke()
                    # Here we check if the tool is a LangChain tool which has .invoke()
                    try:
                        result = await tool_func.ainvoke(tool_args)
                    except Exception as e:
                        result = json.dumps({"status": "error", "message": str(e)})
                else:
                    result = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

                tool_results.append({
                    "tool": tool_name,
                    "result": result
                })

            # Feed tool results back to LLM for final synthesis
            tool_context = "\n\n".join([
                f"Tool: {tr['tool']}\nResult: {tr['result']}"
                for tr in tool_results
            ])

            final_messages = messages + [
                response,  # The LLM's tool-calling response
                HumanMessage(content=f"Tool results:\n{tool_context}\n\nNow format your findings as the required JSON.")
            ]

            final_response = await llm_with_tools.ainvoke(final_messages)
            content = final_response.content
        else:
            # LLM responded directly without calling tools
            content = response.content

        # --- Parse LLM JSON response ---
        evidence_chunks, summary = _parse_researcher_response(content, subtask)

        duration_ms = int((time.time() - start_time) * 1000)
        tokens = getattr(response, "usage_metadata", {})
        tokens_used = tokens.get("total_tokens", 0) if tokens else 0

        result = SubtaskResult(
            agent_name="researcher",
            subtask=subtask,
            output=summary,
            evidence=evidence_chunks,
            success=True,
            tokens_used=tokens_used,
        )

        step.duration_ms = duration_ms
        step.metadata = {
            "evidence_count": len(evidence_chunks),
            "tools_called": [tr["tool"] for tr in tool_results],
            "tokens_used": tokens_used,
        }

        logger.info(
            "Researcher node complete",
            evidence_count=len(evidence_chunks),
            duration_ms=duration_ms
        )

        # Return ONLY the fields this node changes — LangGraph merges the rest
        return {
            "subtask_results": [result],         # operator.add appends this
            "evidence_chunks": evidence_chunks,   # operator.add appends these
            "agent_steps": [step],                # operator.add appends this
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
            "steps_taken": state.get("steps_taken", 0) + 1,
        }

    except Exception as e:
        logger.error("Researcher node failed", error=str(e), subtask=subtask)

        error_result = SubtaskResult(
            agent_name="researcher",
            subtask=subtask,
            output="",
            success=False,
            error=f"Researcher failed: {str(e)}",
        )

        return {
            "subtask_results": [error_result],
            "agent_steps": [step],
            "errors": [f"Researcher error on '{subtask[:50]}': {str(e)}"],
            "steps_taken": state.get("steps_taken", 0) + 1,
        }


def _parse_researcher_response(
    content: str,
    subtask: str,
) -> tuple[list[EvidenceChunk], str]:
    """
    Parse the LLM's JSON response into EvidenceChunk objects.
    
    LLMs sometimes wrap JSON in markdown code fences (```json ... ```).
    We strip those before parsing.
    
    Falls back to a single EvidenceChunk with the raw text if JSON fails.
    This is the "graceful degradation" pattern — never crash, always return
    something the next agent can work with.
    """
    # Strip markdown code fences if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Remove first line (```json) and last line (```)
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])

    try:
        data = json.loads(cleaned)
        evidence_list = data.get("evidence", [])
        summary = data.get("summary", f"Research completed for: {subtask[:50]}")

        chunks = []
        for item in evidence_list:
            try:
                chunks.append(EvidenceChunk(
                    source=item.get("source", "unknown"),
                    content=str(item.get("content", ""))[:800],  # Cap content length
                    relevance_score=float(item.get("relevance_score", 0.5)),
                ))
            except Exception:
                continue  # Skip malformed individual evidence items

        if not chunks:
            # JSON parsed but no evidence items — use raw content as fallback
            chunks = [EvidenceChunk(
                source="llm_direct",
                content=content[:800],
                relevance_score=0.4,
            )]

        return chunks, summary

    except json.JSONDecodeError:
        # LLM didn't return valid JSON — wrap raw response as a single chunk
        logger.warning("Researcher returned non-JSON, using raw content as evidence")
        return [EvidenceChunk(
            source="llm_direct",
            content=content[:800],
            relevance_score=0.3,
        )], f"Research completed (unstructured): {subtask[:50]}"
