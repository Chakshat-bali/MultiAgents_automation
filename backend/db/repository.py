"""
db/repository.py — Data access layer (Repository pattern).

WHY THE REPOSITORY PATTERN?
    Instead of writing raw SQL in route handlers, we centralise all DB
    operations here. Benefits:
    1. Route handlers stay clean — they call repo methods, not SQL
    2. If you switch from PostgreSQL to MongoDB, only this file changes
    3. Easy to mock in tests — inject a fake TaskRepository
    4. All DB logic is in one place, easier to audit and optimise

INTERVIEW ANSWER:
    "I used the repository pattern to decouple the data access layer from
    the business logic. Route handlers depend on TaskRepository, not on
    SQLAlchemy directly. This means I can swap the database or add caching
    without touching the API layer."
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import TaskRecord
from schemas.task import TaskListItem, TaskResult, TaskStatus

logger = structlog.get_logger(__name__)


class TaskRepository:
    """
    All database operations for the tasks table.
    Instantiated per-request with the current AsyncSession.
    """

    def __init__(self, session: AsyncSession) -> None:
        # The session is injected — this is dependency injection at the class level
        self.session = session

    async def create_task(
        self,
        task_id: str,
        task: str,
        output_format: str = "markdown",
    ) -> TaskRecord:
        """
        Insert a new task row with status=pending.
        Called immediately when POST /run-task is received,
        before the agent starts running.
        """
        record = TaskRecord(
            id=task_id,
            task=task,
            status=TaskStatus.PENDING.value,
            output_format=output_format,
            agent_steps=[],
        )
        self.session.add(record)
        await self.session.flush()  # Write to DB but don't commit yet
                                    # get_db() commits after the route handler returns
        logger.info("Task created in DB", task_id=task_id)
        return record

    async def get_task(self, task_id: str) -> TaskRecord | None:
        """
        Fetch one task by ID.
        Returns None if not found — callers handle the 404.
        """
        result = await self.session.execute(
            select(TaskRecord).where(TaskRecord.id == task_id)
        )
        return result.scalar_one_or_none()  # scalar_one_or_none: returns None vs raising

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> None:
        """Update just the status field — called when agent starts running."""
        await self.session.execute(
            update(TaskRecord)
            .where(TaskRecord.id == task_id)
            .values(status=status.value)
        )

    async def update_agent_steps(
        self,
        task_id: str,
        steps: list[dict],
    ) -> None:
        """
        Append new agent steps to the JSON column.
        Called periodically during streaming to update the live log.

        WHY PASS DICTS NOT PYDANTIC MODELS?
            JSON columns store plain dicts. We serialise AgentStep → dict
            before storing. On read we deserialise back. This is the standard
            pattern — ORM models don't know about Pydantic models.
        """
        await self.session.execute(
            update(TaskRecord)
            .where(TaskRecord.id == task_id)
            .values(agent_steps=steps)
        )

    async def complete_task(
        self,
        task_id: str,
        result: TaskResult,
        duration_seconds: float,
    ) -> None:
        """
        Write the final result when the agent finishes.

        TaskResult is a Pydantic model — we serialise it to a dict for
        the JSON column using model_dump().

        model_dump(mode='json') ensures datetime objects become ISO strings
        and Enum values become their string values — both JSON-serialisable.
        """
        result_dict = result.model_dump(mode="json")

        await self.session.execute(
            update(TaskRecord)
            .where(TaskRecord.id == task_id)
            .values(
                status=result.status.value,
                result=result_dict,
                agent_steps=result_dict.get("agent_steps", []),
                confidence_score=result.confidence_score,
                total_tokens_used=result.total_tokens_used,
                duration_seconds=duration_seconds,
                error=result.error,
                completed_at=datetime.now(timezone.utc),
            )
        )
        logger.info(
            "Task completed in DB",
            task_id=task_id,
            status=result.status.value,
            confidence=result.confidence_score,
        )

    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed with an error message."""
        await self.session.execute(
            update(TaskRecord)
            .where(TaskRecord.id == task_id)
            .values(
                status=TaskStatus.FAILED.value,
                error=error,
                completed_at=datetime.now(timezone.utc),
            )
        )
        logger.error("Task failed in DB", task_id=task_id, error=error[:100])

    async def list_tasks(self, limit: int = 20) -> list[TaskListItem]:
        """
        Return the N most recent tasks as lightweight TaskListItem objects.
        We don't return the full result JSON — too large for a list view.
        """
        result = await self.session.execute(
            select(TaskRecord)
            .order_by(TaskRecord.created_at.desc())
            .limit(limit)
        )
        records = result.scalars().all()

        items = []
        for r in records:
            items.append(TaskListItem(
                task_id=r.id,
                status=TaskStatus(r.status),
                task=r.task,
                confidence_score=r.confidence_score,
                created_at=r.created_at,
                completed_at=r.completed_at,
            ))
        return items
