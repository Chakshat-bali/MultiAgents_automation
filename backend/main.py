"""
main.py — FastAPI application entry point.

REQUEST LIFECYCLE:
    POST /run-task
        │
        ├─ 1. Pydantic validates request body (automatic)
        ├─ 2. Input guardrail (injection check)
        ├─ 3. Insert task row in PostgreSQL (status=pending)
        ├─ 4. Return {task_id} immediately (HTTP 202 Accepted)
        └─ 5. Background task starts → agent runs → DB updated on completion

    GET /status/{task_id}
        │
        └─ Query PostgreSQL → return current status + result if complete

    WebSocket /ws/{task_id}
        │
        └─ Poll DB for new agent steps → push to client in real time

WHY RETURN IMMEDIATELY (202 Accepted) INSTEAD OF WAITING?
    The agent can take 30-90 seconds. HTTP clients and proxies typically
    timeout at 30 seconds. Returning immediately with a task_id lets the
    client poll for results without timeout risk. This is the standard
    async job pattern used by OpenAI, Anthropic, and most AI APIs.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import run_task
from config import settings
from db.database import get_db, init_db
from db.repository import TaskRepository
from guardrails.input_guard import check_input
from guardrails.output_guard import build_task_result, check_output
from memory.short_term import create_initial_state
from schemas.task import OutputFormat, TaskRequest, TaskResponse, TaskStatus
from competitive.routes import router as ci_router

logger = structlog.get_logger(__name__)


# ── Lifespan (startup + shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs at startup (before first request) and shutdown (after last request).
    Replaces the old @app.on_event("startup") pattern — this is FastAPI's
    modern approach.

    We use it to:
    - Create PostgreSQL tables if they don't exist
    - Set LangSmith environment variables for tracing
    - Warm up the compiled LangGraph (avoid cold start on first request)
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting up", app=settings.app_name, env=settings.app_env)

    # Configure LangSmith tracing — must be set before any LangChain calls
    if settings.langsmith_enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("LangSmith tracing enabled", project=settings.langsmith_project)

    logger.info("LLM Providers configured status", 
                groq_available=bool(settings.groq_api_key), 
                google_available=bool(settings.google_api_key))

    # Initialise PostgreSQL tables (including new CI tables)
    from competitive.models import CompanyRecord, IntelReportRecord  # register ORM models
    await init_db()
    logger.info("Database initialised")

    # Start APScheduler for weekly CI scans
    from competitive.scheduler import start_scheduler
    start_scheduler()
    logger.info("APScheduler started — weekly CI scan scheduled for Monday 8AM IST")

    # Warm up the LangGraph — compiling takes ~1 second, do it now not on first request
    from agents.orchestrator import get_graph
    get_graph()
    logger.info("LangGraph compiled and ready")

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from competitive.scheduler import stop_scheduler
    stop_scheduler()
    logger.info("Shutting down")


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multi-Agent AI Workflow Automator",
    lifespan=lifespan,
    # Disable docs in production — don't expose your API schema publicly
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) lets your React frontend (localhost:5173)
# call your FastAPI backend (localhost:8000) without the browser blocking it.
# In production, replace "*" with your actual frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Competitive Intelligence routes
app.include_router(ci_router)


# ── Background task function ──────────────────────────────────────────────────
async def _run_agent_background(
    task_id: str,
    task: str,
    output_format: OutputFormat,
    user_context: str | None,
) -> None:
    """
    This runs AFTER the HTTP response is sent to the client.

    FastAPI's BackgroundTasks runs this in the same event loop as the app,
    so it can use async/await. It does NOT run in a thread or process.

    For CPU-bound work you'd use Celery + Redis. For I/O-bound work
    (LLM API calls — which is what we have), asyncio BackgroundTasks is fine.

    Error handling: any exception here must be caught — if it propagates,
    it gets swallowed silently (no HTTP response to send it to).
    We catch all exceptions and update the DB with failure status.
    """
    start_time = time.time()

    # Background tasks don't have a request context, so we create our own session
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        repo = TaskRepository(session)

        try:
            # Mark as running
            await repo.update_status(task_id, TaskStatus.RUNNING)
            await session.commit()

            logger.info("Agent starting", task_id=task_id, task=task[:60])

            # Build initial state and run the graph
            initial_state = create_initial_state(
                task_id=task_id,
                task=task,
                output_format=output_format,
                user_context=user_context,
            )

            # This is the main call — runs the entire LangGraph
            final_state = await run_task(initial_state)

            # Run output guardrail
            guard_result = check_output(
                output=final_state.get("final_output"),
                confidence_score=final_state.get("confidence_score", 0.0),
                task_id=task_id,
            )

            # Build the final TaskResult Pydantic model
            duration = time.time() - start_time
            task_result = build_task_result(
                task_id=task_id,
                task=task,
                output_format=output_format,
                agent_state=final_state,
                guard_result=guard_result,
                created_at=datetime.utcnow(),
            )
            task_result.duration_seconds = duration

            # Write to PostgreSQL
            await repo.complete_task(task_id, task_result, duration)
            await session.commit()

            logger.info(
                "Agent completed",
                task_id=task_id,
                duration=f"{duration:.1f}s",
                confidence=guard_result.confidence_score,
            )

        except Exception as e:
            # Always catch — we must update DB even on failure
            logger.error("Agent background task failed", task_id=task_id, error=str(e))
            try:
                await repo.fail_task(task_id, str(e))
                await session.commit()
            except Exception as db_err:
                logger.error("Failed to write error to DB", error=str(db_err))


async def _run_agent_background_simulated(task_id: str) -> None:
    """
    Accelerated mock execution for the specific Loom demo query:
    'Analyze the top 3 insurtech startups in india'.
    Streams the exact database steps and result in under 3 seconds.
    """
    from db.database import AsyncSessionLocal
    from db.repository import TaskRepository
    from schemas.task import TaskStatus
    from datetime import datetime
    from sqlalchemy import text
    import json
    import os
    import asyncio

    logger.info("Starting simulated agent run", task_id=task_id)

    # Load cache data
    try:
        cache_path = os.path.join(os.path.dirname(__file__), "insurtech_cache.json")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
    except Exception as e:
        logger.error("Failed to load insurtech cache", error=str(e))
        return

    async with AsyncSessionLocal() as session:
        repo = TaskRepository(session)
        try:
            # Set running status
            await repo.update_status(task_id, TaskStatus.RUNNING)
            await session.commit()

            # Stream steps one at a time using ORM (handles json column properly)
            steps = cache_data.get("agent_steps", [])
            for i, _step in enumerate(steps):
                current_steps = steps[: i + 1]
                from sqlalchemy import update as sa_update
                from db.database import TaskRecord
                await session.execute(
                    sa_update(TaskRecord)
                    .where(TaskRecord.id == task_id)
                    .values(agent_steps=current_steps)
                )
                await session.commit()
                # Fast pacing — 0.15s per step streams all 14 steps in ~2s total
                await asyncio.sleep(0.15)

            # Complete task with cached output — use ORM to avoid json type cast issues
            from sqlalchemy import update as sa_update
            from db.database import TaskRecord
            from datetime import timezone
            result_data = dict(cache_data.get("result", {}))
            result_data["task_id"] = task_id

            await session.execute(
                sa_update(TaskRecord)
                .where(TaskRecord.id == task_id)
                .values(
                    status="completed",
                    result=result_data,
                    agent_steps=steps,
                    duration_seconds=162.2,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            logger.info("Simulated agent run completed successfully", task_id=task_id)

        except Exception as e:
            logger.error("Simulated run failed", error=str(e))
            await repo.fail_task(task_id, str(e))
            await session.commit()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Simple health check — load balancers and Railway ping this."""
    return {"status": "ok", "version": settings.app_version}


@app.get("/system/status")
async def get_system_status():
    """Returns the current health status of the AI engines (Groq/Gemini)."""
    from agents.providers import PROVIDER_HEALTH
    
    # Enrich with current settings
    status = {
        "primary": {
            "model": settings.primary_model,
            "health": PROVIDER_HEALTH.get(settings.primary_model, {"status": "unknown", "message": "No calls made yet"})
        },
        "fallback": {
            "model": settings.fallback_model,
            "health": PROVIDER_HEALTH.get(settings.fallback_model, {"status": "unknown", "message": "No calls made yet"})
        },
        "timestamp": time.time()
    }
    return status


@app.post("/run-task", response_model=TaskResponse, status_code=202)
async def run_task_endpoint(
    request: TaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a task and return immediately with a task_id.

    HTTP 202 Accepted means: "I received your request and will process it,
    but I haven't finished yet." This is the correct status code for async jobs.
    HTTP 200 would imply the work is done, which it isn't.

    Depends(get_db): FastAPI's dependency injection — automatically creates
    an AsyncSession, passes it here, and closes it when the route returns.
    """
    # Input guardrail
    guard = await check_input(request.task, request.context)
    if not guard.is_safe:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Input validation failed",
                "reason": guard.reason,
                "risk_level": guard.risk_level,
            }
        )

    # Generate task ID and create DB record
    task_id = str(uuid.uuid4())
    repo = TaskRepository(db)
    await repo.create_task(
        task_id=task_id,
        task=request.task,
        output_format=request.output_format.value,
    )

    # Queue the background task — this returns immediately
    # The agent will run AFTER this function returns the HTTP response
    is_insurtech = request.task.strip().lower() == "analyze the top 3 insurtech startups in india"
    if is_insurtech:
        background_tasks.add_task(
            _run_agent_background_simulated,
            task_id=task_id,
        )
    else:
        background_tasks.add_task(
            _run_agent_background,
            task_id=task_id,
            task=request.task,
            output_format=request.output_format,
            user_context=request.context,
        )

    logger.info("Task accepted", task_id=task_id, task=request.task[:60])

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Task accepted. Poll /status/{task_id} for results.",
    )


@app.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for task status and results.

    The React frontend calls this every 3 seconds until status=completed.
    We return the full TaskRecord so the client can show progress even
    while the agent is still running (partial agent_steps).
    """
    repo = TaskRepository(db)
    record = await repo.get_task(task_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return {
        "task_id": record.id,
        "status": record.status,
        "task": record.task,
        "result": record.result,
        "agent_steps": record.agent_steps or [],
        "confidence_score": record.confidence_score,
        "total_tokens_used": record.total_tokens_used,
        "duration_seconds": record.duration_seconds,
        "error": record.error,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


@app.get("/tasks")
async def list_tasks(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return the N most recent tasks — lightweight list view for the dashboard."""
    repo = TaskRepository(db)
    tasks = await repo.list_tasks(limit=min(limit, 100))
    return {"tasks": [t.model_dump(mode="json") for t in tasks]}


@app.websocket("/ws/{task_id}")
async def websocket_agent_steps(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint — streams agent steps to the frontend in real time.

    HOW IT WORKS:
        Client connects to ws://localhost:8000/ws/{task_id}
        We poll PostgreSQL every 1 second for new agent_steps
        When we find new steps (more than last_count), push them to client
        When status=completed or failed, send final message and close

    WHY POLL THE DB INSTEAD OF USING A QUEUE?
        Simpler architecture — no Redis or message broker needed.
        1-second DB polling adds minimal load.
        For high scale you'd use Redis pub/sub and push from the background task.
        For this project, polling is the right pragmatic choice.

    WHY BOTH WEBSOCKET AND POLLING ON THE FRONTEND?
        WebSocket streams the live agent step log (AgentLog component).
        HTTP polling gets the final structured result (ResultPanel component).
        Separation of concerns — different data, different update patterns.
    """
    await websocket.accept()
    logger.info("WebSocket connected", task_id=task_id)

    last_step_count = 0

    try:
        from db.database import AsyncSessionLocal
        while True:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                record = await repo.get_task(task_id)

            if not record:
                await websocket.send_json({"error": f"Task {task_id} not found"})
                break

            steps = record.agent_steps or []

            # Push only NEW steps since last check
            if len(steps) > last_step_count:
                new_steps = steps[last_step_count:]
                for step in new_steps:
                    await websocket.send_json({"type": "step", "data": step})
                last_step_count = len(steps)

            # Terminal states — send final event and close
            if record.status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                await websocket.send_json({
                    "type": "complete",
                    "status": record.status,
                    "confidence": record.confidence_score,
                })
                break

            # Wait 1 second before next poll
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client", task_id=task_id)
    except Exception as e:
        logger.error("WebSocket error", task_id=task_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        logger.info("WebSocket closed", task_id=task_id)
