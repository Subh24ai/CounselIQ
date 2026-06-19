"""Application configuration via pydantic-settings.

All settings are loaded from environment variables (or a local ``.env`` file).
The :class:`Settings` object is cached so it is instantiated exactly once per
process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT secrets that must never be used in production, regardless of length.
_INSECURE_SECRETS = {
    "secret",
    "changeme",
    "change-me",
    "change-me-in-production",
    "changeme123",
    "password",
    "your-secret-key",
    "supersecret",
}


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Core ---------------------------------------------------------------
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Database -----------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://counseliq:counseliq@postgres:5432/counseliq",
        description="SQLAlchemy async database URL.",
    )

    # --- Redis / Celery -----------------------------------------------------
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # --- AWS ----------------------------------------------------------------
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = "counseliq-documents"
    # Optional custom endpoint (e.g. LocalStack at http://localhost:4566).
    # When empty, boto3 talks to real AWS.
    AWS_ENDPOINT_URL: str = ""

    # --- LLM providers ------------------------------------------------------
    # Primary is Anthropic Claude; Groq Llama is the fallback. At least one key
    # must be configured (enforced below). ``LLM_PROVIDER`` forces a provider;
    # ``auto`` prefers Anthropic when its key is present.
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    LLM_PROVIDER: str = "auto"  # "auto" | "anthropic" | "groq"

    # --- Auth / JWT ---------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # --- Rate limiting ------------------------------------------------------
    # Disabled in the test suite so the broad set of auth calls is not throttled;
    # the dedicated rate-limit test re-enables it locally.
    RATE_LIMIT_ENABLED: bool = True

    # --- Frontend -----------------------------------------------------------
    # Public base URL of the Next.js app. Used to construct invitation links
    # (the token is stored; the link is built on read, never persisted).
    FRONTEND_URL: str = "http://localhost:3000"

    # --- CORS ---------------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS`` to be supplied as a comma-separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            # Support JSON-style lists transparently by deferring to pydantic.
            if stripped.startswith("["):
                return stripped
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def check_at_least_one_llm_key(self) -> Settings:
        """Fail fast at startup if no LLM provider is configured.

        Surfacing this as a configuration error (rather than a runtime error at
        first inference) means a misconfigured deployment never boots.
        """
        if not self.ANTHROPIC_API_KEY and not self.GROQ_API_KEY:
            raise ValueError(
                "At least one LLM key required: set ANTHROPIC_API_KEY or GROQ_API_KEY"
            )
        return self

    @model_validator(mode="after")
    def check_production_secrets(self) -> Settings:
        """Refuse to boot in production with a weak or default JWT secret.

        Only enforced when ``ENVIRONMENT=production`` so local/dev/test runs keep
        working with the placeholder default.
        """
        if self.ENVIRONMENT.lower() != "production":
            return self

        key = (self.JWT_SECRET_KEY or "").strip()
        if len(key) < 32:
            raise ValueError(
                "In production, JWT_SECRET_KEY must be set to a random value of "
                "at least 32 characters."
            )
        if key.lower() in _INSECURE_SECRETS:
            raise ValueError(
                "In production, JWT_SECRET_KEY must not be a common insecure "
                "default (e.g. 'secret', 'changeme')."
            )
        return self

    @property
    def active_llm_provider(self) -> str:
        """Resolve the provider to use: explicit override, else auto-select.

        In ``auto`` mode Anthropic wins when its key is present, otherwise Groq.
        """
        if self.LLM_PROVIDER != "auto":
            return self.LLM_PROVIDER
        return "anthropic" if self.ANTHROPIC_API_KEY else "groq"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


settings = get_settings()
