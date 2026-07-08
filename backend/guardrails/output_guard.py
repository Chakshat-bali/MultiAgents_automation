"""
guardrails/output_guard.py — Output validation, confidence gating, PII scrubbing.

WHY OUTPUT GUARDRAILS?
    Even with perfect input, the LLM can produce:
    - Confidently wrong information (hallucination)
    - Leaked PII from retrieved documents
    - Malformed output that breaks downstream parsing
    - Low-confidence results that should be flagged, not silently returned

OUTPUT GUARD PIPELINE:
    raw output
        │
        ▼
    ┌─────────────────┐
    │ Schema validate │  ← Does it match TaskResult structure?
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Confidence gate │  ← Is confidence >= threshold?
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │   PII scrub     │  ← Remove any PII from output text
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Length check    │  ← Not empty, not absurdly long
    └────────┬────────┘
             │
         safe output
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from config import settings
from schemas.task import (
    AgentStep, OutputFormat, SubtaskResult,
    TaskResult, TaskStatus,
)

logger = structlog.get_logger(__name__)

# ── PII scrubbing patterns ─────────────────────────────────────────────────────
# Same patterns as input_guard but used for REDACTION in output

_PII_REDACTION_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # (label, pattern, replacement)
    ("email",   re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL REDACTED]"),
    ("phone",   re.compile(r"\b(\+91|91|0)?[6-9]\d{9}\b"), "[PHONE REDACTED]"),
    ("pan",     re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"), "[PAN REDACTED]"),
    ("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[AADHAAR REDACTED]"),
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class OutputGuardResult:
    """Result of running the output guard pipeline."""
    is_valid: bool
    sanitised_output: str = ""        # PII-scrubbed version of the output
    confidence_score: float = 0.0
    confidence_passed: bool = True
    pii_redacted: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    fallback_used: bool = False


# ── Main guard function ───────────────────────────────────────────────────────

def check_output(
    output: str | None,
    confidence_score: float,
    task_id: str,
) -> OutputGuardResult:
    """
    Validate and sanitise the agent's final output.
    
    This is synchronous — no LLM call needed for output validation.
    We rely on the validate_node's LLM scoring for quality assessment;
    here we just enforce the rules mechanically.
    
    Args:
        output: The final_output string from AgentState.
        confidence_score: The confidence_score from validate_node (0-1).
        task_id: For logging.
    
    Returns:
        OutputGuardResult — caller decides what to do based on is_valid.
    """
    issues = []

    # ── Check 1: Output exists ─────────────────────────────────────────────
    if not output or not output.strip():
        logger.warning("Output guard: empty output", task_id=task_id)
        return OutputGuardResult(
            is_valid=False,
            sanitised_output=_fallback_response("Output was empty"),
            confidence_score=0.0,
            confidence_passed=False,
            issues=["Output is empty"],
            fallback_used=True,
        )

    # ── Check 2: Length sanity ─────────────────────────────────────────────
    if len(output) < 50:
        issues.append(f"Output suspiciously short ({len(output)} chars)")
        logger.warning("Output guard: very short output", task_id=task_id, length=len(output))

    if len(output) > 50_000:
        # Truncate — don't fail, just cap it
        output = output[:50_000] + "\n\n[Output truncated — exceeded maximum length]"
        issues.append("Output truncated to 50,000 characters")

    # ── Check 3: PII scrubbing ─────────────────────────────────────────────
    sanitised, pii_found = _scrub_pii(output)
    if pii_found:
        logger.info("PII scrubbed from output", types=pii_found, task_id=task_id)
        issues.append(f"PII redacted: {', '.join(pii_found)}")

    # ── Check 4: Confidence gate ───────────────────────────────────────────
    confidence_passed = confidence_score >= settings.confidence_threshold

    if not confidence_passed:
        logger.warning(
            "Output confidence below threshold",
            score=confidence_score,
            threshold=settings.confidence_threshold,
            task_id=task_id,
        )
        # We DON'T replace the output — we append a warning instead
        # Replacing silently would be worse than showing a flagged result
        sanitised = (
            f"⚠️ **Low Confidence Warning** (score: {confidence_score:.2f}, "
            f"threshold: {settings.confidence_threshold})\n\n"
            f"The following output may be incomplete or inaccurate:\n\n"
            + sanitised
        )
        issues.append(f"Confidence {confidence_score:.2f} below threshold {settings.confidence_threshold}")

    logger.info(
        "Output guard passed",
        task_id=task_id,
        confidence=confidence_score,
        confidence_passed=confidence_passed,
        pii_redacted=pii_found,
        issues_count=len(issues),
    )

    return OutputGuardResult(
        is_valid=True,         # Valid even if low confidence — we flag it, not block it
        sanitised_output=sanitised,
        confidence_score=confidence_score,
        confidence_passed=confidence_passed,
        pii_redacted=pii_found,
        issues=issues,
    )


def build_task_result(
    task_id: str,
    task: str,
    output_format: OutputFormat,
    agent_state: dict,
    guard_result: OutputGuardResult,
    created_at: datetime,
) -> TaskResult:
    """
    Assemble the final TaskResult Pydantic model from agent state + guard result.
    
    This is the object serialised to JSON and stored in SQLite,
    and later returned to the client via GET /status/{task_id}.
    """
    is_complete = agent_state.get("is_complete", False)
    errors = agent_state.get("errors", [])

    # Determine final status
    if not is_complete:
        status = TaskStatus.RUNNING
    elif not guard_result.is_valid or errors:
        status = TaskStatus.FAILED
    else:
        status = TaskStatus.COMPLETED

    # Deserialise subtask_results if they came back as dicts (SQLite round-trip)
    raw_results = agent_state.get("subtask_results", [])
    subtask_results = []
    for r in raw_results:
        if isinstance(r, SubtaskResult):
            subtask_results.append(r)
        elif isinstance(r, dict):
            try:
                subtask_results.append(SubtaskResult(**r))
            except Exception:
                pass

    # Same for agent_steps
    raw_steps = agent_state.get("agent_steps", [])
    agent_steps = []
    for s in raw_steps:
        if isinstance(s, AgentStep):
            agent_steps.append(s)
        elif isinstance(s, dict):
            try:
                agent_steps.append(AgentStep(**s))
            except Exception:
                pass

    return TaskResult(
        task_id=task_id,
        status=status,
        task=task,
        output=guard_result.sanitised_output if guard_result.is_valid else None,
        output_format=output_format,
        subtask_results=subtask_results,
        agent_steps=agent_steps,
        confidence_score=guard_result.confidence_score,
        total_tokens_used=agent_state.get("total_tokens_used", 0),
        duration_seconds=None,  # Set by caller who knows the start time
        error="; ".join(errors) if errors else None,
        created_at=created_at,
        completed_at=datetime.utcnow(),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scrub_pii(text: str) -> tuple[str, list[str]]:
    """
    Replace PII patterns in text with redaction placeholders.
    Returns (scrubbed_text, list_of_pii_types_found).
    """
    found = []
    for label, pattern, replacement in _PII_REDACTION_PATTERNS:
        if pattern.search(text):
            text = pattern.sub(replacement, text)
            found.append(label)
    return text, found


def _fallback_response(reason: str) -> str:
    """Standard fallback message when output cannot be returned."""
    return (
        f"The task could not be completed successfully.\n\n"
        f"Reason: {reason}\n\n"
        f"Please try again with a more specific task description, "
        f"or check that all API keys are correctly configured."
    )
