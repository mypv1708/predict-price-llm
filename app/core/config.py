from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def async_database_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url.removeprefix(prefix)
    return url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = Field(min_length=1)

    @property
    def sqlalchemy_url(self) -> str:
        return async_database_url(self.database_url)


class Settings(DatabaseSettings):
    api_token: str = Field(min_length=16)

    gemini_api_key: str = Field(min_length=1)
    gemini_api_model: str = "gemini-3.8-flash"
    gemini_api_version: str = "v1beta"
    gemini_fallback_models: str = "gemini-3.8-flash,gemini-3.6-flash"
    gemini_api_revision: str = "2026-05-20"
    gemini_attempts: int = Field(default=2, ge=1)
    gemini_retry_delay_seconds: float = Field(default=0.4, ge=0)
    gemini_request_timeout_seconds: float = Field(default=30, gt=0)
    gemini_total_timeout_seconds: float = Field(default=60, gt=0)

    db_pool_min: int = Field(default=1, ge=1)
    db_pool_max: int = Field(default=5, ge=1)
    max_upload_bytes: int = Field(default=2_000_000, ge=1)
    max_message_chars: int = Field(default=20_000, ge=1)

    dataset_path: Path = ROOT / "Dataset.csv"
    system_prompt_path: Path = ROOT / "system_prompt.txt"

    @model_validator(mode="after")
    def check_pool(self) -> Settings:
        if self.db_pool_max < self.db_pool_min:
            raise ValueError("DB_POOL_MAX must be greater than or equal to DB_POOL_MIN")
        return self

    @property
    def interactions_url(self) -> str:
        return f"https://generativelanguage.googleapis.com/{self.gemini_api_version}/interactions"

    @property
    def fallback_models(self) -> tuple[str, ...]:
        return tuple(
            name.strip() for name in self.gemini_fallback_models.split(",") if name.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
