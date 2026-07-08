"""
schemas/task.py — HTTP boundary contracts for task submission and response.

These models validate everything coming IN from the user and going OUT to the user.
They are the FIRST line of defence — bad data never reaches agent logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    """
    Inheriting from str means TaskStatus.PENDING == "pending" is True.
    This lets FastAPI serialise it directly to JSON as a string — no extra
    conversion step needed. Always do this for Enums that cross HTTP boundaries.
    """
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class OutputFormat(str, Enum):
    """Controls what shape the final agent output takes."""
    TEXT     = "text"       # Plain prose
    MARKDOWN = "markdown"   # Formatted markdown
    JSON     = "json"       # Structured JSON object
    BULLET   = "bullet"     # Bullet-point list


# ── Request Model ─────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    """
    What the user POSTs to /run-task.
    
    Pydantic v2 validates this automatically when FastAPI receives the request.
    If any field fails validation, FastAPI returns a 422 Unprocessable Entity
    with detailed error messages — before our code even runs.
    """

    task: str = Field(
        ...,                          # Required — no default
        min_length=10,                # Too short = probably not a real task
        max_length=2000,              # Hard cap — prevents context overflow attacks
        description="Natural language task description",
        examples=["Research the top 3 insurtech companies in India and write a summary"]
    )

    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Desired format for the final output"
    )

    # Optional context the user can provide — injected into agent system prompt
    context: str | None = Field(
        default=None,
        max_length=500,
        description="Optional extra context (e.g. 'Focus on B2B companies only')"
    )

    # Webhook URL — if provided, POST result here when done (async notification)
    webhook_url: str | None = Field(
        default=None,
        description="Optional URL to POST result to when task completes"
    )

    @field_validator("task")
    @classmethod
    def task_must_be_meaningful(cls, v: str) -> str:
        """
        Basic sanity check BEFORE the input guardrail runs.
        We strip whitespace so '   ' (10 spaces) doesn't pass min_length.
        The real injection detection happens in guardrails/input_guard.py.
        """
        cleaned = v.strip()
        if len(cleaned) < 10:
            raise ValueError("Task must contain at least 10 non-whitespace characters")
        return cleaned

    @field_validator("webhook_url")
    @classmethod
    def webhook_must_be_https(cls, v: str | None) -> str | None:
        """
        In production, only allow HTTPS webhooks.
        We skip this check in development (handled by config.is_production).
        This validator runs regardless — but we keep the logic simple here.
        """
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("webhook_url must be a valid HTTP/HTTPS URL")
        return v


# ── Sub-task and Evidence models ──────────────────────────────────────────────

class EvidenceChunk(BaseModel):
    """
    A single piece of evidence returned by the Researcher sub-agent.
    Keeping evidence structured means the Summariser knows exactly what to expect.
    """
    source: str = Field(..., description="URL or file path of the source")
    content: str = Field(..., description="Relevant excerpt from the source")
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0,          # ge = greater-or-equal, le = less-or-equal
        description="How relevant this chunk is to the query (0-1)"
    )


class SubtaskResult(BaseModel):
    """
    What each sub-agent returns after completing its work.
    The Orchestrator's AGGREGATE node collects these into the final output.
    """
    agent_name: str = Field(..., description="Which sub-agent produced this (researcher/summariser/writer)")
    subtask: str   = Field(..., description="The specific subtask this agent was given")
    output: str    = Field(..., description="The agent's output text")
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    success: bool  = Field(default=True)
    error: str | None = Field(default=None, description="Error message if success=False")
    tokens_used: int = Field(default=0, description="LLM tokens consumed by this subtask")


# ── Agent Step Log ─────────────────────────────────────────────────────────────

class AgentStep(BaseModel):
    """
    One entry in the agent's execution trace — streamed to the frontend via WebSocket.
    The user sees these appear in real-time in the AgentLog component.
    """
    step_number: int
    node_name: str   = Field(..., description="Which LangGraph node ran (PLAN/ROUTE/RESEARCHER etc.)")
    description: str = Field(..., description="Human-readable description of what this step did")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int | None = Field(default=None, description="How long this step took in milliseconds")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Any extra data about this step")


# ── Response Models ────────────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    """
    What /run-task returns immediately — just the ID.
    
    WHY NOT RETURN THE RESULT DIRECTLY?
    The agent can take 30-60 seconds. HTTP requests time out at 30s in most
    clients/proxies. So we return immediately with an ID, run the agent in
    the background, and let the client poll /status/{task_id}.
    
    This is the "async job" pattern — universal in production APIs.
    """
    task_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID to poll for results"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    message: str = Field(default="Task accepted and queued")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskResult(BaseModel):
    """
    The full result returned by GET /status/{task_id} when status=completed.
    This is what the ResultPanel component renders.
    """
    task_id: str
    status: TaskStatus
    task: str                              # Echo back original task
    output: str | None = None             # The final formatted output
    output_format: OutputFormat
    subtask_results: list[SubtaskResult] = Field(default_factory=list)
    agent_steps: list[AgentStep]          = Field(default_factory=list)
    confidence_score: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Orchestrator's self-assessed confidence in the output"
    )
    total_tokens_used: int = Field(default=0)
    duration_seconds: float | None = None
    error: str | None = None              # Set if status=failed
    created_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def completed_tasks_must_have_output(self) -> TaskResult:
        """
        model_validator runs AFTER all field validators.
        It validates relationships BETWEEN fields.
        
        A completed task with no output is a bug — catch it at the schema level.
        This is pydantic v2's way of doing cross-field validation.
        """
        if self.status == TaskStatus.COMPLETED and self.output is None:
            raise ValueError("A completed task must have a non-null output field")
        if self.status == TaskStatus.FAILED and self.error is None:
            raise ValueError("A failed task must have a non-null error field")
        return self


class TaskListItem(BaseModel):
    """Lightweight summary for GET /tasks (list view — don't return full output)."""
    task_id: str
    status: TaskStatus
    task: str
    confidence_score: float | None = None
    created_at: datetime
    completed_at: datetime | None = None
