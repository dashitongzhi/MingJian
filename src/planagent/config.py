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
    minio_secure: bool = False
    minio_bucket: str = "planagent-snapshots"
    source_snapshot_backend: str = "filesystem"
    source_snapshot_dir: Path = Field(default=Path("source_snapshots"))
    additional_rss_feeds: str = ""
    source_failure_degraded_threshold: int = 5
    backpressure_pending_threshold: int = 1000
    graph_embedding_dimensions: int = 64
    analysis_cache_enabled: bool = True
    inline_ingest_default: bool = True
    inline_simulation_default: bool = True
    api_cache_ttl_seconds: int = 300
    stream_maxlen: int = 10000
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_primary_model: str = "openai/gpt-5.2"
    openai_primary_api_key: str | None = None
    openai_primary_base_url: str | None = None
    openai_extraction_model: str | None = None
    openai_extraction_api_key: str | None = None
    openai_extraction_base_url: str | None = None
    openai_x_search_model: str | None = None
    openai_x_search_api_key: str | None = None
    openai_x_search_base_url: str | None = None
    openai_report_model: str | None = None
    openai_report_api_key: str | None = None
    openai_report_base_url: str | None = None
    openai_timeout_seconds: float = 45.0
    x_bearer_token: str | None = None
    x_base_url: str = "https://api.x.com/2"
    accepted_claim_confidence: float = 0.70
    review_claim_confidence_floor: float = 0.45
    source_snapshot_retention_days: int = 90
    report_retention_days: int = 30
    default_corporate_ticks: int = 6
    default_military_ticks: int = 8
    worker_lease_seconds: int = 60
    worker_max_attempts: int = 3
    stream_consumer_block_ms: int = 5000
    stream_consumer_count: int = 10
    sql_echo: bool = False
    rules_dir: Path = Field(default=Path("rules"))

    @property
    def resolved_openai_api_key(self) -> str | None:
        return self.openai_api_key or os.getenv("OPENAI_API_KEY")

    @property
    def openai_enabled(self) -> bool:
        return bool(self.configured_openai_targets)

    @property
    def configured_openai_targets(self) -> list[str]:
        targets: list[str] = []
        if self.resolved_openai_primary_api_key:
            targets.append("primary")
        if self.resolved_openai_extraction_api_key:
            targets.append("extraction")
        if self.resolved_openai_x_search_api_key:
            targets.append("x_search")
        if self.resolved_openai_report_api_key:
            targets.append("report")
        return targets

    @property
    def resolved_openai_primary_api_key(self) -> str | None:
        return self.openai_primary_api_key or self.resolved_openai_api_key

    @property
    def resolved_openai_primary_base_url(self) -> str | None:
        return self.openai_primary_base_url or self.openai_base_url

    @property
    def resolved_openai_extraction_model(self) -> str:
        return self.openai_extraction_model or self.openai_primary_model

    @property
    def resolved_openai_extraction_api_key(self) -> str | None:
        return self.openai_extraction_api_key or self.resolved_openai_primary_api_key

    @property
    def resolved_openai_extraction_base_url(self) -> str | None:
        return self.openai_extraction_base_url or self.resolved_openai_primary_base_url

    @property
    def resolved_openai_report_model(self) -> str:
        return self.openai_report_model or self.openai_primary_model

    @property
    def resolved_openai_report_api_key(self) -> str | None:
        return self.openai_report_api_key or self.resolved_openai_primary_api_key

    @property
    def resolved_openai_report_base_url(self) -> str | None:
        return self.openai_report_base_url or self.resolved_openai_primary_base_url

    @property
    def resolved_x_bearer_token(self) -> str | None:
        return self.x_bearer_token or os.getenv("X_BEARER_TOKEN")

    @property
    def x_enabled(self) -> bool:
        return bool(self.resolved_x_bearer_token or self.resolved_openai_x_search_api_key)

    @property
    def resolved_openai_x_search_model(self) -> str:
        return self.openai_x_search_model or self.resolved_openai_extraction_model

    @property
    def resolved_openai_x_search_api_key(self) -> str | None:
        return self.openai_x_search_api_key or self.resolved_openai_extraction_api_key

    @property
    def resolved_openai_x_search_base_url(self) -> str | None:
        return self.openai_x_search_base_url or self.resolved_openai_extraction_base_url

    def openai_model_source(self, target: str) -> str:
        if target == "primary":
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        if target == "extraction":
            if self.openai_extraction_model:
                return "PLANAGENT_OPENAI_EXTRACTION_MODEL"
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        if target == "x_search":
            if self.openai_x_search_model:
                return "PLANAGENT_OPENAI_X_SEARCH_MODEL"
            if self.openai_extraction_model:
                return "PLANAGENT_OPENAI_EXTRACTION_MODEL"
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        if target == "report":
            if self.openai_report_model:
                return "PLANAGENT_OPENAI_REPORT_MODEL"
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        raise ValueError(f"Unsupported target: {target}")

    def openai_api_key_source(self, target: str) -> str:
        shared_env_key = os.getenv("OPENAI_API_KEY")

        if target == "primary":
            if self.openai_primary_api_key:
                return "PLANAGENT_OPENAI_PRIMARY_API_KEY"
            if self.openai_api_key:
                return "PLANAGENT_OPENAI_API_KEY"
            if shared_env_key:
                return "OPENAI_API_KEY"
            return "unset"
        if target == "extraction":
            if self.openai_extraction_api_key:
                return "PLANAGENT_OPENAI_EXTRACTION_API_KEY"
            return self.openai_api_key_source("primary")
        if target == "x_search":
            if self.openai_x_search_api_key:
                return "PLANAGENT_OPENAI_X_SEARCH_API_KEY"
            if self.openai_extraction_api_key:
                return "PLANAGENT_OPENAI_EXTRACTION_API_KEY"
            return self.openai_api_key_source("primary")
        if target == "report":
            if self.openai_report_api_key:
                return "PLANAGENT_OPENAI_REPORT_API_KEY"
            return self.openai_api_key_source("primary")
        raise ValueError(f"Unsupported target: {target}")

    def openai_base_url_source(self, target: str) -> str:
        if target == "primary":
            if self.openai_primary_base_url:
                return "PLANAGENT_OPENAI_PRIMARY_BASE_URL"
            if self.openai_base_url:
                return "PLANAGENT_OPENAI_BASE_URL"
            return "unset"
        if target == "extraction":
            if self.openai_extraction_base_url:
                return "PLANAGENT_OPENAI_EXTRACTION_BASE_URL"
            return self.openai_base_url_source("primary")
        if target == "x_search":
            if self.openai_x_search_base_url:
                return "PLANAGENT_OPENAI_X_SEARCH_BASE_URL"
            if self.openai_extraction_base_url:
                return "PLANAGENT_OPENAI_EXTRACTION_BASE_URL"
            return self.openai_base_url_source("primary")
        if target == "report":
            if self.openai_report_base_url:
                return "PLANAGENT_OPENAI_REPORT_BASE_URL"
            return self.openai_base_url_source("primary")
        raise ValueError(f"Unsupported target: {target}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
