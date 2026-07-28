from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timezone

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "magicpin-vera-ai-challenge"
    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./vera.db"
    team_name: str = "Your Team Name"
    team_members: str = ""
    team_model: str = "rules-based-deterministic"
    contact_email: str = "team@example.com"
    submitted_at: datetime = Field(default_factory=lambda: datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc))
    api_prefix: str = "/v1"
    suppression_days: int = 7
    max_actions_per_tick: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
