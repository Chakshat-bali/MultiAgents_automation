# Multi-Agent AI Workflow Automator

A production-grade multi-agent system where natural language tasks are broken into subtasks, executed by specialist AI agents, and returned as structured output — with full observability, guardrails, and persistent memory.

## Architecture

```
POST /run-task
      │
      ▼
 Input Guard ──▶ [blocked] → 400
      │
      ▼
 PostgreSQL (status=pending)
      │
      ▼
 Background Task
      │
      ▼
┌─────────────────────────────────────┐
│         LangGraph StateGraph        │
│                                     │
│  MEMORY_LOAD → PLAN → ROUTE ──────┐ │
│                  ▲                │ │
│                  │                ▼ │
│               ROUTE ← SUMMARISER ← RESEARCHER
│                  │                  │
│                  ▼                  │
│               WRITER → VALIDATE → END
└─────────────────────────────────────┘
      │
      ▼
 Output Guard → PII scrub → confidence gate
      │
      ▼
 PostgreSQL (status=completed, result=JSON)
      │
      ▼
 GET /status/{task_id} ← React frontend polls
 WS  /ws/{task_id}     ← React frontend streams steps
```

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Agent Framework | LangGraph 0.2 | Explicit state graph, controllable, streamable |
| Primary LLM | Groq Llama-3.3-70B | Fast inference, generous free tier |
| Fallback LLM | Gemini 1.5 Flash | Provider abstraction — swap without code changes |
| Web Search | Tavily API | Purpose-built for LLM agents, returns clean text |
| Vector Store | FAISS + FastEmbed | Local, no API key, persistent long-term memory |
| Backend | FastAPI + asyncio | Async-first, background tasks, WebSocket |
| Database | PostgreSQL + SQLAlchemy 2.0 async | Production-grade, connection pooling, Alembic migrations |
| Frontend | React + Vite + TypeScript | WebSocket live log + polling result panel |
| Observability | LangSmith | Traces every LLM call, token usage, latency |
| Deployment | Docker + Railway + GitHub Actions | One-push CI/CD |

## Quick Start

```bash
# 1. Clone and configure
git clone <repo>
cp .env.example .env
# Fill in: GROQ_API_KEY, TAVILY_API_KEY, LANGSMITH_API_KEY

# 2. Start everything with Docker
docker compose up --build

# 3. Open the app
open http://localhost:3000

# Or test the API directly
curl -X POST http://localhost:8000/run-task \
  -H "Content-Type: application/json" \
  -d '{"task": "Research the top 3 insurtech companies in India and summarise their business models"}'
# → {"task_id": "uuid", "status": "pending"}

curl http://localhost:8000/status/{task_id}
# → {"status": "completed", "result": {"output": "..."}, "confidence_score": 0.87}
```

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/run-task` | Submit task, returns `task_id` immediately (202) |
| `GET` | `/status/{task_id}` | Poll for result |
| `GET` | `/tasks` | List recent tasks |
| `WS` | `/ws/{task_id}` | Stream live agent steps |
| `GET` | `/health` | Health check |

## Key Design Decisions

**Why LangGraph over CrewAI?**
Explicit graph structure — every node, edge, and routing decision is visible in code. CrewAI abstracts this away, making debugging hard. LangGraph integrates natively with LangSmith for full observability.

**Why return task_id immediately (202 Accepted)?**
Agents take 30-90 seconds. HTTP proxies and clients timeout at 30s. Async job pattern avoids timeouts and scales to concurrent requests without blocking.

**Why PostgreSQL over SQLite?**
Multiple FastAPI workers can write simultaneously. Railway/Render provide managed PostgreSQL. Alembic migrations enable schema evolution without data loss.

**Why two guardrail layers?**
Input guard catches injection attacks before they reach the agent. Output guard catches PII leaked via tool results (indirect injection) and enforces confidence thresholds. One layer is not sufficient.

**How does long-term memory work?**
After each completed task (confidence ≥ threshold), the task + output summary is embedded via FastEmbed (local, no API key) and stored in a FAISS index on disk. New tasks retrieve the top-3 similar past results and inject them into the planning prompt.

## Example Tasks

```
Research the top 3 insurtech companies in India and compare their funding rounds

Summarise the key differences between LangGraph and CrewAI for building multi-agent systems

What are the main AI trends in Indian healthcare in 2024? Write a one-page report.

Compare the business models of PhonePe, Razorpay, and Paytm
```


