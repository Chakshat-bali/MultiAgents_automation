"""
tools/retriever_tool.py — FAISS RAG retrieval tool.

This tool searches our LOCAL vector store (long-term memory) for relevant
information from past tasks. It complements web_search — web_search gets
fresh external info, this tool gets internal accumulated knowledge.

The agent uses this when:
- The task is similar to something we've done before
- We want to avoid redundant web searches
- We need to recall previous findings
"""

from __future__ import annotations

import json

import structlog
from langchain_core.tools import tool

from config import settings

logger = structlog.get_logger(__name__)

# Module-level reference — populated lazily on first use
_memory_store = None


def get_memory_store():
    """
    Lazy import to avoid circular imports and slow startup.
    memory/long_term.py imports this file's tool, so we can't import at module level.
    """
    global _memory_store
    if _memory_store is None:
        # Import here, not at top of file — avoids circular dependency
        from memory.long_term import LongTermMemory
        _memory_store = LongTermMemory()
    return _memory_store


@tool
def retrieve_from_memory(query: str, top_k: int = 3) -> str:
    """
    Search internal memory for information from previously completed tasks.
    
    Use this tool when:
    - You need context from similar tasks we've run before
    - Web search is unavailable or rate-limited
    - The task asks about something we may have researched previously
    
    Returns a JSON string with relevant memory chunks and their similarity scores.
    Returns empty results if no relevant memories exist yet.
    
    Args:
        query: What you're looking for in memory.
        top_k: How many memory chunks to retrieve (1-5, default 3).
    """
    try:
        top_k = max(1, min(5, top_k))
        store = get_memory_store()

        logger.info("retrieve_from_memory called", query=query, top_k=top_k)

        # retrieve() returns list of (text, score) tuples
        results = store.retrieve(query=query, top_k=top_k)

        if not results:
            return json.dumps({
                "status": "success",
                "message": "No relevant memories found. This appears to be a new topic.",
                "results": [],
            })

        formatted = [
            {"content": text, "similarity_score": round(score, 3)}
            for text, score in results
        ]

        logger.info("retrieve_from_memory success", results_found=len(formatted))

        return json.dumps({
            "status": "success",
            "results": formatted,
            "message": f"Found {len(formatted)} relevant memories from past tasks."
        }, indent=2)

    except Exception as e:
        logger.error("retrieve_from_memory failed", error=str(e))
        return json.dumps({
            "status": "error",
            "error_type": "retrieval_failed",
            "message": f"Memory retrieval failed: {str(e)}. Proceed without past context.",
        })
