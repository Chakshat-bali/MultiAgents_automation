"""
agents/providers.py — LLM provider abstraction layer.

WHY THIS FILE EXISTS:
    Every sub-agent needs an LLM. If each agent imported ChatGroq directly,
    switching providers (or adding fallback logic) would mean editing 3+ files.

    Instead: all agents call get_llm(). Provider logic lives in ONE place.
    This is the Open/Closed principle — agents are closed to provider changes,
    this file is open to extension (add Anthropic, Cohere, etc. here only).

HEALTH TRACKING:
    Health is tracked via a LangChain BaseCallbackHandler — the idiomatic way
    to observe LLM calls without wrapping the model object itself.
    The old HealthTrackingChatModel wrapper caused pydantic validation errors
    because it was not a Runnable, so .with_fallbacks() rejected it.
"""

from __future__ import annotations

import time
from typing import Any, Union
from uuid import UUID

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Global health tracker
# keys: model_name
# values: {"status": "ok"|"exhausted"|"error", "last_check": float, "message": str}
# ---------------------------------------------------------------------------
PROVIDER_HEALTH: dict[str, dict] = {}


def update_provider_health(model_name: str, status: str, message: str = "") -> None:
    PROVIDER_HEALTH[model_name] = {
        "status": status,
        "last_check": time.time(),
        "message": message,
    }


# ---------------------------------------------------------------------------
# Callback handler — attaches to a real BaseChatModel, no wrapping needed
# ---------------------------------------------------------------------------

class HealthTrackingCallback(BaseCallbackHandler):
    """
    LangChain callback handler that updates PROVIDER_HEALTH on every LLM call.

    Attach via:
        llm = ChatGroq(..., callbacks=[HealthTrackingCallback("groq-model")])

    This keeps the LLM object a genuine Runnable so .with_fallbacks() works.
    """

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self.model_name = model_name

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        update_provider_health(self.model_name, "ok", "Operational")

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        msg = str(error)
        status = (
            "exhausted"
            if any(kw in msg.lower() for kw in ("rate limit", "quota", "429"))
            else "error"
        )
        update_provider_health(self.model_name, status, msg)


# ---------------------------------------------------------------------------
# Internal factory — returns a real BaseChatModel (Runnable-compliant)
# ---------------------------------------------------------------------------

def _build_llm(model_name: str, temperature: float, api_key: str) -> BaseChatModel:
    """
    Build a LangChain BaseChatModel with a health-tracking callback attached.

    Returns a genuine Runnable — safe to pass to .with_fallbacks().
    """
    callback = HealthTrackingCallback(model_name)

    if "gemini" in model_name.lower():
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=temperature,
            max_retries=2,
            callbacks=[callback],
        )
    else:
        return ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_retries=2,
            callbacks=[callback],
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_llm(temperature: float = 0.1, use_fallback: bool = False) -> BaseChatModel:
    """Return the configured LLM — dynamically choosing provider."""
    model_name = settings.fallback_model if use_fallback else settings.primary_model
    api_key = (
        settings.google_api_key
        if "gemini" in model_name.lower()
        else settings.groq_api_key
    )
    logger.debug("Initialising LLM", model=model_name, is_fallback=use_fallback)
    return _build_llm(model_name, temperature, api_key)


def get_llm_with_fallback(temperature: float = 0.1) -> BaseChatModel:
    """
    Returns an LLM with RUNTIME fallback to the secondary provider.

    Both primary and fallback are genuine Runnables — .with_fallbacks() works
    because we no longer wrap them in a non-Runnable class.
    """
    primary = get_llm(temperature=temperature, use_fallback=False)

    if settings.groq_api_key and settings.google_api_key:
        fallback = get_llm(temperature=temperature, use_fallback=True)
        return primary.with_fallbacks(
            [fallback],
            exceptions_to_handle=(Exception,),
        )

    return primary


def get_llm_with_tools_and_fallback(tools: list, temperature: float = 0.1) -> BaseChatModel:
    """
    Returns an LLM with tools bound AND runtime fallback.

    We bind tools AFTER building the base model so that bind_tools() returns
    a RunnableBinding (still a Runnable), keeping .with_fallbacks() happy.
    """
    primary = get_llm(temperature=temperature, use_fallback=False).bind_tools(tools)

    if settings.groq_api_key and settings.google_api_key:
        fallback = get_llm(temperature=temperature, use_fallback=True).bind_tools(tools)
        return primary.with_fallbacks(
            [fallback],
            exceptions_to_handle=(Exception,),
        )

    return primary
