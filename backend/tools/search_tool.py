"""
tools/search_tool.py — Tavily web search tool.

Tavily is purpose-built for LLM agents — it returns clean, pre-extracted text
rather than raw HTML, which means we don't need a scraper or HTML parser.
Free tier: 1000 searches/month, plenty for dev and demos.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool
from tavily import TavilyClient

from config import settings

logger = structlog.get_logger(__name__)


def _get_tavily_client() -> TavilyClient:
    """
    Lazy initialisation — only create the client when the tool is first called.
    This means the app starts even if TAVILY_API_KEY is empty (useful for tests).
    """
    if not settings.tavily_api_key:
        raise ValueError("TAVILY_API_KEY is not set in environment")
    return TavilyClient(api_key=settings.tavily_api_key)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for current information using Tavily.
    
    Use this tool when you need:
    - Recent news or events (after your training cutoff)
    - Specific facts about companies, people, or products
    - Market data, statistics, or research
    
    Returns a JSON string with a list of results, each containing
    'title', 'url', 'content', and 'score' fields.
    On failure, returns a JSON error object.
    
    Args:
        query: The search query string. Be specific for better results.
        max_results: Number of results to return (1-10, default 5).
    """
    # Note: The docstring above is what the LLM reads to decide when to call
    # this tool. It must be clear, specific, and describe the return format.

    try:
        # Clamp max_results to valid range — the LLM might pass weird values
        max_results = max(1, min(10, max_results))

        client = _get_tavily_client()

        logger.info("web_search called", query=query, max_results=max_results)

        # Tavily's search method — search_depth="advanced" does deeper scraping
        # but uses 2x credits. "basic" is fine for most tasks.
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,    # Tavily also provides a pre-summarised answer
        )

        # Format results into a clean structure for the agent
        results = []

        # Include Tavily's own pre-summarised answer if present
        if response.get("answer"):
            results.append({
                "title": "Direct Answer",
                "url": "tavily_synthesis",
                "content": response["answer"],
                "score": 1.0,
            })

        # Individual source results
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                # Tavily returns 'content' as the main text — already extracted
                "content": r.get("content", "")[:800],  # Cap at 800 chars per result
                "score": r.get("score", 0.0),
            })

        logger.info("web_search success", result_count=len(results))

        # Always return JSON string — the LLM receives this as a tool message
        # and parses it in context. Never return a Python object directly.
        return json.dumps({"status": "success", "results": results}, indent=2)

    except ValueError as e:
        # Configuration error (missing API key) — return structured error
        logger.error("web_search config error", error=str(e))
        return json.dumps({"status": "error", "error_type": "config", "message": str(e)})

    except Exception as e:
        # Network error, rate limit, etc. — agent will see this and can decide
        # to retry or fall back to retriever_tool
        logger.error("web_search failed", error=str(e), query=query)
        return json.dumps({
            "status": "error",
            "error_type": "search_failed",
            "message": f"Web search failed: {str(e)}. Try rephrasing the query or use the retriever tool instead.",
        })
