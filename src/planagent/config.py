import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLANAGENT_",
        extra="ignore",
    )

    app_name: str = "PlanAgent"
    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./planagent.db"
    redis_url: str = "redis://localhost:6379/0"
    event_bus_backend: str = "memory"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "planagent"
    minio_secret_key: str = "planagent123"
    inline_ingest_default: bool = True
    inline_simulation_default: bool = True
    api_cache_ttl_seconds: int = 300
    stream_maxlen: int = 10000
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_primary_model: str = "openai/gpt-5.2"
    openai_extraction_model: str | None = None
    openai_report_model: str | None = None
    openai_timeout_seconds: float = 45.0
    accepted_claim_confidence: float = 0.70
    review_claim_confidence_floor: float = 0.45
    source_snapshot_retention_days: int = 90
    report_retention_days: int = 30
    default_corporate_ticks: int = 6
    default_military_ticks: int = 8
    sql_echo: bool = False
    rules_dir: Path = Field(default=Path("rules"))

    @property
    def resolved_openai_api_key(self) -> str | None:
        return self.openai_api_key or os.getenv("OPENAI_API_KEY")

    @property
    def openai_enabled(self) -> bool:
        return bool(self.resolved_openai_api_key)

    @property
    def resolved_openai_extraction_model(self) -> str:
        return self.openai_extraction_model or self.openai_primary_model

    @property
    def resolved_openai_report_model(self) -> str:
        return self.openai_report_model or self.openai_primary_model


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
