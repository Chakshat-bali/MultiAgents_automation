"""
config.py — Centralised application configuration using pydantic-settings.

WHY THIS FILE EXISTS:
    Instead of calling os.getenv("GROQ_API_KEY") scattered across 10 files,
    we define ONE Settings class. Every module imports `settings` from here.
    
    Benefits:
    1. Type safety — GROQ_API_KEY is guaranteed to be a str, not None
    2. Validation — app crashes at startup if a required key is missing
       (fail fast — better than crashing mid-request)
    3. Single source of truth — change a default in one place
    4. IDE autocomplete — settings.groq_api_key is discoverable

HOW pydantic-settings WORKS:
    BaseSettings reads fields from (in priority order):
    1. Environment variables (GROQ_API_KEY in shell)
    2. .env file (loaded automatically if you pass env_file in model_config)
    3. Default values defined in the class
"""

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application configuration in one place.
    
    pydantic-settings maps env var names to field names automatically.
    GROQ_API_KEY in .env → groq_api_key field (case-insensitive by default).
    """

    # ── Model configuration for pydantic-settings ────────────────────────────
    # This tells pydantic-settings WHERE to read env vars from.
    model_config = SettingsConfigDict(
        env_file=".env",          # Load from .env file in working directory
        env_file_encoding="utf-8",
        case_sensitive=False,     # GROQ_API_KEY matches groq_api_key
        extra="ignore",           # Ignore unknown env vars (don't raise error)
    )

    # ── LLM Provider Keys ─────────────────────────────────────────────────────
    # Field(...) means REQUIRED — app will not start without this.
    # We use default="" instead of ... so the app can start without keys
    # for local testing with mocks. Change to Field(...) for production.
    groq_api_key: str = Field(default="", description="Groq API key for Llama models")
    google_api_key: str = Field(default="", description="Google API key for Gemini fallback")

    # ── Tool Keys ─────────────────────────────────────────────────────────────
    tavily_api_key: str = Field(default="", description="Tavily web search API key")

    # ── Competitive Intelligence Extension ────────────────────────────────────
    # Apify: free $5/month credits — https://apify.com (no credit card for free tier)
    # Get token: https://console.apify.com/account/integrations
    apify_api_token: str = Field(default="", description="Apify API token for web scraping")

    # Crunchbase: free Basic API (200 req/month) — https://data.crunchbase.com/docs
    crunchbase_api_key: str = Field(default="", description="Crunchbase Basic API key (optional)")

    # Slack Incoming Webhook — completely free, no credit card
    # Setup: https://api.slack.com/apps → Incoming Webhooks → Add to Workspace
    slack_webhook_url: str = Field(default="", description="Slack Incoming Webhook URL for CI digests")

    # Email (SMTP) Configuration
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port (usually 587 for TLS)")
    smtp_user: str = Field(default="", description="SMTP username (often an email address)")
    smtp_password: str = Field(default="", description="SMTP password or app password")
    smtp_from_email: str = Field(default="", description="Sender email address")
    recipient_email: str = Field(default="", description="Default recipient for CI reports")

    # ── LangSmith Observability ───────────────────────────────────────────────
    langsmith_api_key: str = Field(default="", description="LangSmith tracing key")
    langsmith_project: str = Field(default="multi-agent-automator")
    # This env var name is what LangChain looks for — it auto-enables tracing
    langchain_tracing_v2: str = Field(default="false")

    # ── Model Names ───────────────────────────────────────────────────────────
    primary_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model — fastest, free tier generous"
    )
    fallback_model: str = Field(
        default="gemini-1.5-flash",
        description="Gemini model — used when Groq fails or rate-limits"
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="FastEmbed model — downloaded locally, no API key needed"
    )

    # ── Agent Behaviour ───────────────────────────────────────────────────────
    max_agent_steps: int = Field(
        default=10,
        description="Hard cap on ReAct loop iterations — prevents infinite loops"
    )
    confidence_threshold: float = Field(
        default=0.6,
        description="Min confidence score (0-1) — below this, return fallback response"
    )

    # ── Storage Paths ─────────────────────────────────────────────────────────
    # PostgreSQL connection string
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    # asyncpg is the async driver — SQLAlchemy uses it under the hood
    # For local Docker: postgresql+asyncpg://postgres:postgres@localhost:5432/automator
    # For Railway/Render: copy the DATABASE_URL from their dashboard
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/automator",
        description="PostgreSQL connection string with asyncpg driver"
    )
    faiss_index_path: str = Field(
        default="./memory/faiss_index",
        description="Directory where FAISS index files are persisted to disk"
    )

    # ── App Meta ──────────────────────────────────────────────────────────────
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    app_name: str = Field(default="Multi-Agent Automator")
    app_version: str = Field(default="0.2.0")

    # ── Derived Properties ────────────────────────────────────────────────────
    # @property works normally on pydantic models
    @property
    def is_production(self) -> bool:
        """Convenience check used in main.py to toggle debug mode."""
        return self.app_env == "production"

    @property
    def langsmith_enabled(self) -> bool:
        """True only if we have a key AND tracing is set to true."""
        return bool(self.langsmith_api_key) and self.langchain_tracing_v2 == "true"

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("confidence_threshold")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """
        field_validator runs at instantiation time.
        If someone sets CONFIDENCE_THRESHOLD=1.5 in .env, we catch it here
        instead of getting bizarre behaviour at runtime.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence_threshold must be between 0 and 1, got {v}")
        return v

    @field_validator("max_agent_steps")
    @classmethod
    def validate_max_steps(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError(f"max_agent_steps must be between 1 and 50, got {v}")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings singleton.
    
    WHY @lru_cache?
        Without it, every `from config import settings` would re-read and
        re-parse the .env file. With lru_cache(maxsize=1), the Settings object
        is constructed ONCE and reused everywhere.
    
    WHY A FUNCTION instead of module-level `settings = Settings()`?
        Because in tests, you can override get_settings() with a mock that
        returns a test-specific Settings object — without affecting other tests.
        This is the dependency injection pattern for configuration.
    
    USAGE:
        from config import get_settings
        settings = get_settings()
    """
    return Settings()


# Module-level convenience — most modules will do:
#   from config import settings
# This is fine for non-test code.
settings = get_settings()

