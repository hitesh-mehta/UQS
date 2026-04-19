"""
UQS Backend Configuration
Loads all settings from environment variables via pydantic-settings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Supabase ──────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    database_url: str = ""

    # ── LLM ───────────────────────────────────────────────────
    # Hackathon default: Google Gemini 2.0 Flash (free tier, no GPU needed)
    # Switch by setting LLM_PROVIDER=ollama|openai|anthropic
    llm_provider: Literal["ollama", "openai", "anthropic", "google"] = "google"
    llm_model: str = "gemini-2.0-flash"   # or: gemma2:2b, gpt-4o, claude-3-haiku
    llm_base_url: str = "http://localhost:11434"  # Ollama only
    google_api_key: str = ""              # Google AI Studio API key
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Embeddings ────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Auth ──────────────────────────────────────────────────
    jwt_secret: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── Cache ─────────────────────────────────────────────────
    cache_store_path: str = "./cache_store"
    cache_retention_units: int = 10

    # ── Model Registry ────────────────────────────────────────
    model_registry_path: str = "./model_registry"
    max_rollback_versions: int = 5

    # ── Vector Store ──────────────────────────────────────────
    vector_store_type: Literal["faiss", "qdrant"] = "faiss"
    faiss_index_path: str = "./faiss_index"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── API ───────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True  # Set to False in production

    # ── Security ──────────────────────────────────────────────
    rate_limit_per_minute: int = 30
    query_max_length: int = 1000
    request_timeout_seconds: int = 30
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # ── Cron ──────────────────────────────────────────────────
    cron_enabled: bool = True

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        # asyncpg needs 'postgresql+asyncpg://' prefix
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
