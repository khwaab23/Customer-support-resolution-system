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
