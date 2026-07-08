"""
db/database.py — PostgreSQL async engine, session factory, and table definitions.

CONCEPTS TO KNOW:

Engine:
    The engine is the connection factory. It holds the connection pool and
    knows how to talk to PostgreSQL via asyncpg. One engine per application.
    Think of it as the "manager" that owns all connections.

Session:
    A session is one unit of work — a conversation with the database.
    You open a session, run queries, commit, close. SQLAlchemy tracks
    all changes made in a session and writes them together on commit.
    Using async sessions means your FastAPI endpoint doesn't block while
    waiting for the DB — other requests can run in that time.

Connection Pool:
    pool_size=10 means 10 persistent connections are kept alive.
    max_overflow=20 means up to 20 extra connections can be created
    under peak load, then discarded when demand drops.
    pool_pre_ping=True means SQLAlchemy checks if a connection is
    still alive before using it (prevents "server closed the connection"
    errors after idle periods).

AsyncSession + async with:
    Every DB operation uses 'async with get_db() as session:'
    This guarantees the session is closed even if an exception occurs.
    It's the async version of the context manager pattern.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON, Column, DateTime, Float, Integer,
    String, Text, func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings

# ── Engine (one per app, created at startup) ──────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    # Pool configuration
    pool_size=10,          # Persistent connections kept alive
    max_overflow=20,       # Extra connections allowed under peak load
    pool_pre_ping=True,    # Check connection health before use
    pool_recycle=3600,     # Recycle connections after 1 hour (prevents stale)
    # Logging — set echo=True to see every SQL query (useful for debugging)
    echo=settings.app_env == "development",
)

# ── Session factory ───────────────────────────────────────────────────────────
# async_sessionmaker creates AsyncSession objects with these defaults
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
                             # (lets you read attributes after committing)
    autocommit=False,        # We manage transactions explicitly
    autoflush=False,         # We flush explicitly — gives us control
)


# ── ORM Base ──────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    All ORM models inherit from this.
    DeclarativeBase is the SQLAlchemy 2.0 way — replaces the old
    declarative_base() function call pattern.
    """
    pass


# ── Tasks Table ORM Model ─────────────────────────────────────────────────────
class TaskRecord(Base):
    """
    Maps to the 'tasks' table in PostgreSQL.

    WHY JSON COLUMNS FOR result AND agent_steps?
        PostgreSQL has a native JSON/JSONB type — it stores structured data
        and you can query inside it (e.g. WHERE result->>'confidence' > '0.7').
        JSONB (binary JSON) is faster for reads. We use JSON here for
        simplicity — use JSONB in production for query performance.

    WHY NOT A SEPARATE TABLE FOR agent_steps?
        Each step is only meaningful in the context of its task.
        We never query steps independently of tasks.
        Storing them as JSON in the same row is simpler and faster
        than a JOIN across two tables for every status poll.
    """
    __tablename__ = "tasks"

    # Primary key — the UUID we return to the client immediately
    id = Column(String(36), primary_key=True, index=True)

    # Task content
    task = Column(Text, nullable=False)
    status = Column(String(20), default="pending", index=True)
                                # index=True — we query by status frequently
    output_format = Column(String(20), default="markdown")

    # Results — stored as PostgreSQL JSON
    result = Column(JSON, nullable=True)        # Full TaskResult dict
    agent_steps = Column(JSON, default=list)    # List of AgentStep dicts
    error = Column(Text, nullable=True)

    # Metrics
    confidence_score = Column(Float, nullable=True)
    total_tokens_used = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)

    # Timestamps — server_default uses DB server time (not Python time)
    # This is important: if your Python server and DB server are in different
    # timezones, using DB server time is always consistent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


# ── Dependency injection helper ────────────────────────────────────────────────
async def get_db():
    """
    FastAPI dependency — yields an AsyncSession for one request.

    Usage in a route:
        @app.get("/tasks")
        async def list_tasks(db: AsyncSession = Depends(get_db)):
            ...

    HOW IT WORKS:
        'async with AsyncSessionLocal() as session' opens a session.
        'yield session' gives it to the route handler.
        When the handler finishes (or raises), execution returns here.
        The 'async with' block then closes and returns the connection to pool.

    WHY YIELD INSTEAD OF RETURN?
        yield turns this into a generator. FastAPI runs the code before yield,
        injects the value, then runs the code after yield for cleanup.
        This guarantees cleanup even if the route handler raises an exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()   # Commit if no exception occurred
        except Exception:
            await session.rollback() # Roll back on any exception
            raise                    # Re-raise so FastAPI returns 500


async def init_db() -> None:
    """
    Create all tables if they don't exist.
    Called once at application startup in main.py.

    IMPORTANT: This uses CREATE TABLE IF NOT EXISTS under the hood.
    For production schema changes (adding columns, etc.) use Alembic
    migrations instead — this function can't handle schema evolution.
    """
    async with engine.begin() as conn:
        # run_sync runs the synchronous create_all in an async context
        await conn.run_sync(Base.metadata.create_all)
