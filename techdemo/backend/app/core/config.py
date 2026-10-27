from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = Field(min_length=1)
    db_port: int = Field(ge=1, le=65535)
    db_name: str = Field(min_length=1)
    db_user: str = Field(min_length=1)
    db_password: str = Field(min_length=1)
    app_environment: Literal["development", "production"] = "development"
    session_cookie_name: str = "techdemo_session"
    csrf_cookie_name: str = "techdemo_csrf"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_minutes: int = Field(default=480, ge=1, le=43_200)
    trusted_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:8001,"
        "http://127.0.0.1:8001"
    )
    openai_api_key: str | None = None
    rag_embedding_model: str = "text-embedding-3-small"
    rag_collection_name: str = "techdemo_policy_chunks"
    rag_persist_directory: str = ".chroma"
    rag_chunk_size: int = Field(default=1800, ge=256, le=12_000)
    rag_chunk_overlap: int = Field(default=200, ge=0, le=2_000)
    rag_embedding_batch_size: int = Field(default=32, ge=1, le=256)
    rag_retrieval_top_k: int = Field(default=5, ge=1, le=20)
    rag_distance_threshold: float | None = Field(default=None, ge=0)
    openai_agent_model: str = "gpt-4.1-mini"
    agent_max_tool_rounds: int = Field(default=3, ge=1, le=8)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=20)
    agent_tool_output_max_chars: int = Field(default=12_000, ge=1_000, le=50_000)
    agent_request_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    agent_max_output_tokens: int = Field(default=1_200, ge=100, le=4_000)
    agent_diagnostics_enabled: bool = False
    workflow_checkpoint_schema: str = Field(
        default="techdemo_workflow",
        pattern=r"^[a-z_][a-z0-9_]{0,62}$",
    )
    workflow_recursion_limit: int = Field(default=12, ge=4, le=64)
    workflow_dev_review_simulation_enabled: bool = False

    @property
    def cookie_secure(self) -> bool:
        """Always require HTTPS cookies in production."""
        return self.app_environment == "production" or self.session_cookie_secure

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset(
            origin.strip()
            for origin in self.trusted_origins.split(",")
            if origin.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return validated application settings once per process."""
    return Settings()
