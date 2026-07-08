# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# WHY MULTI-STAGE?
# Stage 1 installs all build dependencies (gcc, headers for C extensions).
# Stage 2 copies only the final installed packages — no compilers in prod image.
# Result: production image is ~60% smaller and has a smaller attack surface.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for packages with C extensions (faiss, asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --user installs into ~/.local — we copy this into the final stage
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: Production image ─────────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Runtime dependency only — libpq for asyncpg PostgreSQL driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Copy installed Python packages from builder stage
COPY --chown=appuser:appuser --from=builder /root/.local /home/appuser/.local

# Copy application source
COPY --chown=appuser:appuser . .

# Create directories the app writes to at runtime
RUN mkdir -p /app/memory /app/agent_workspace /app/alembic/versions && chown -R appuser:appuser /app/memory /app/agent_workspace /app/alembic/versions

USER appuser

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run Alembic migrations then start uvicorn
# --host 0.0.0.0 is required to accept connections from outside the container
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
