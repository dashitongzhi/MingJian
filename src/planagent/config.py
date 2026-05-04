import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAITargetConfig(BaseModel):
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class OpenAIConfig(BaseModel):
    shared_api_key: str | None = None
    shared_base_url: str | None = None
    timeout_seconds: float = 45.0
    primary: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    extraction: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    x_search: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    report: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_advocate: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_challenger: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_arbitrator: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)

    @model_validator(mode="before")
    @classmethod
    def collect_flat_env_target_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        data = dict(data)
        shared_aliases = {
            "api_key": "shared_api_key",
            "base_url": "shared_base_url",
        }
        target_names = (
            "primary",
            "extraction",
            "x_search",
            "report",
            "debate_advocate",
            "debate_challenger",
            "debate_arbitrator",
        )
        field_names = ("model", "api_key", "base_url")

        for alias, field_name in shared_aliases.items():
            if alias in data and field_name not in data:
                data[field_name] = data.pop(alias)

        for target_name in target_names:
            target_data = data.get(target_name)
            if not isinstance(target_data, dict):
                target_data = {}
            else:
                target_data = dict(target_data)

            for field_name in field_names:
                flat_key = f"{target_name}_{field_name}"
                if flat_key in data:
                    target_data[field_name] = data.pop(flat_key)

            if target_data:
                data[target_name] = target_data

        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLANAGENT_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
    )

    app_name: str = "PlanAgent"
    env: str = "development"
    database_url: str = "postgresql+psycopg://planagent:planagent@localhost:5432/planagent"
    redis_url: str = "redis://localhost:6379/0"
    event_bus_backend: str = "redis"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 300
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
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
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    x_bearer_token: str | None = None
    x_base_url: str = "https://api.x.com/2"
    linux_do_base_url: str = "https://linux.do"
    xhs_provider_base_url: str | None = None
    xhs_provider_api_key: str | None = None
    douyin_provider_base_url: str | None = None
    douyin_provider_api_key: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    debate_advocate_provider: str = "openai"
    debate_challenger_provider: str = "anthropic"
    debate_arbitrator_provider: str = "openai"
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

    @model_validator(mode="before")
    @classmethod
    def collect_flat_openai_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        data = dict(data)
        openai_data = data.get("openai")
        if not isinstance(openai_data, dict):
            openai_data = {}
        else:
            openai_data = dict(openai_data)

        shared_fields = {
            "openai_api_key": "shared_api_key",
            "openai_base_url": "shared_base_url",
            "openai_timeout_seconds": "timeout_seconds",
        }
        target_names = (
            "primary",
            "extraction",
            "x_search",
            "report",
            "debate_advocate",
            "debate_challenger",
            "debate_arbitrator",
        )
        field_names = ("model", "api_key", "base_url")

        for flat_key, nested_key in shared_fields.items():
            if flat_key in data:
                openai_data[nested_key] = data.pop(flat_key)

        for target_name in target_names:
            target_data = openai_data.get(target_name)
            if not isinstance(target_data, dict):
                target_data = {}
            else:
                target_data = dict(target_data)

            for field_name in field_names:
                flat_key = f"openai_{target_name}_{field_name}"
                if flat_key in data:
                    target_data[field_name] = data.pop(flat_key)

            if target_data:
                openai_data[target_name] = target_data

        if openai_data:
            data["openai"] = openai_data

        return data

    @property
    def openai_api_key(self) -> str | None:
        return self.openai.shared_api_key

    @property
    def openai_base_url(self) -> str | None:
        return self.openai.shared_base_url

    @property
    def openai_timeout_seconds(self) -> float:
        return self.openai.timeout_seconds

    @property
    def openai_primary_model(self) -> str:
        return self.openai.primary.model or "openai/gpt-5.2"

    @property
    def openai_primary_api_key(self) -> str | None:
        return self.openai.primary.api_key

    @property
    def openai_primary_base_url(self) -> str | None:
        return self.openai.primary.base_url

    @property
    def openai_extraction_model(self) -> str | None:
        return self.openai.extraction.model

    @property
    def openai_extraction_api_key(self) -> str | None:
        return self.openai.extraction.api_key

    @property
    def openai_extraction_base_url(self) -> str | None:
        return self.openai.extraction.base_url

    @property
    def openai_x_search_model(self) -> str | None:
        return self.openai.x_search.model

    @property
    def openai_x_search_api_key(self) -> str | None:
        return self.openai.x_search.api_key

    @property
    def openai_x_search_base_url(self) -> str | None:
        return self.openai.x_search.base_url

    @property
    def openai_report_model(self) -> str | None:
        return self.openai.report.model

    @property
    def openai_report_api_key(self) -> str | None:
        return self.openai.report.api_key

    @property
    def openai_report_base_url(self) -> str | None:
        return self.openai.report.base_url

    @property
    def openai_debate_advocate_model(self) -> str | None:
        return self.openai.debate_advocate.model

    @property
    def openai_debate_advocate_api_key(self) -> str | None:
        return self.openai.debate_advocate.api_key

    @property
    def openai_debate_advocate_base_url(self) -> str | None:
        return self.openai.debate_advocate.base_url

    @property
    def openai_debate_challenger_model(self) -> str | None:
        return self.openai.debate_challenger.model

    @property
    def openai_debate_challenger_api_key(self) -> str | None:
        return self.openai.debate_challenger.api_key

    @property
    def openai_debate_challenger_base_url(self) -> str | None:
        return self.openai.debate_challenger.base_url

    @property
    def openai_debate_arbitrator_model(self) -> str | None:
        return self.openai.debate_arbitrator.model

    @property
    def openai_debate_arbitrator_api_key(self) -> str | None:
        return self.openai.debate_arbitrator.api_key

    @property
    def openai_debate_arbitrator_base_url(self) -> str | None:
        return self.openai.debate_arbitrator.base_url

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
        if self.resolved_openai_debate_advocate_api_key:
            targets.append("debate_advocate")
        if self.resolved_openai_debate_challenger_api_key:
            targets.append("debate_challenger")
        if self.resolved_openai_debate_arbitrator_api_key:
            targets.append("debate_arbitrator")
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
    def resolved_openai_debate_advocate_model(self) -> str:
        return self.openai_debate_advocate_model or self.openai_primary_model

    @property
    def resolved_openai_debate_advocate_api_key(self) -> str | None:
        return self.openai_debate_advocate_api_key or self.resolved_openai_primary_api_key

    @property
    def resolved_openai_debate_advocate_base_url(self) -> str | None:
        return self.openai_debate_advocate_base_url or self.resolved_openai_primary_base_url

    @property
    def resolved_openai_debate_challenger_model(self) -> str:
        return self.openai_debate_challenger_model or self.resolved_openai_extraction_model

    @property
    def resolved_openai_debate_challenger_api_key(self) -> str | None:
        return self.openai_debate_challenger_api_key or self.resolved_openai_primary_api_key

    @property
    def resolved_openai_debate_challenger_base_url(self) -> str | None:
        return self.openai_debate_challenger_base_url or self.resolved_openai_extraction_base_url

    @property
    def resolved_openai_debate_arbitrator_model(self) -> str:
        return self.openai_debate_arbitrator_model or self.resolved_openai_report_model

    @property
    def resolved_openai_debate_arbitrator_api_key(self) -> str | None:
        return self.openai_debate_arbitrator_api_key or self.resolved_openai_primary_api_key

    @property
    def resolved_openai_debate_arbitrator_base_url(self) -> str | None:
        return self.openai_debate_arbitrator_base_url or self.resolved_openai_report_base_url

    @property
    def resolved_x_bearer_token(self) -> str | None:
        return self.x_bearer_token or os.getenv("X_BEARER_TOKEN")

    @property
    def resolved_anthropic_api_key(self) -> str | None:
        return self.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

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
        if target == "debate_advocate":
            if self.openai_debate_advocate_model:
                return "PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL"
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        if target == "debate_challenger":
            if self.openai_debate_challenger_model:
                return "PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL"
            if self.openai_extraction_model:
                return "PLANAGENT_OPENAI_EXTRACTION_MODEL"
            return "PLANAGENT_OPENAI_PRIMARY_MODEL"
        if target == "debate_arbitrator":
            if self.openai_debate_arbitrator_model:
                return "PLANAGENT_OPENAI_DEBATE_ARBITRATOR_MODEL"
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
                if os.getenv("PLANAGENT_OPENAI_SHARED_API_KEY"):
                    return "PLANAGENT_OPENAI_SHARED_API_KEY"
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
        if target == "debate_advocate":
            if self.openai_debate_advocate_api_key:
                return "PLANAGENT_OPENAI_DEBATE_ADVOCATE_API_KEY"
            return self.openai_api_key_source("primary")
        if target == "debate_challenger":
            if self.openai_debate_challenger_api_key:
                return "PLANAGENT_OPENAI_DEBATE_CHALLENGER_API_KEY"
            if self.openai_extraction_api_key:
                return "PLANAGENT_OPENAI_EXTRACTION_API_KEY"
            return self.openai_api_key_source("primary")
        if target == "debate_arbitrator":
            if self.openai_debate_arbitrator_api_key:
                return "PLANAGENT_OPENAI_DEBATE_ARBITRATOR_API_KEY"
            if self.openai_report_api_key:
                return "PLANAGENT_OPENAI_REPORT_API_KEY"
            return self.openai_api_key_source("primary")
        raise ValueError(f"Unsupported target: {target}")

    def openai_base_url_source(self, target: str) -> str:
        if target == "primary":
            if self.openai_primary_base_url:
                return "PLANAGENT_OPENAI_PRIMARY_BASE_URL"
            if self.openai_base_url:
                if os.getenv("PLANAGENT_OPENAI_SHARED_BASE_URL"):
                    return "PLANAGENT_OPENAI_SHARED_BASE_URL"
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
        if target == "debate_advocate":
            if self.openai_debate_advocate_base_url:
                return "PLANAGENT_OPENAI_DEBATE_ADVOCATE_BASE_URL"
            return self.openai_base_url_source("primary")
        if target == "debate_challenger":
            if self.openai_debate_challenger_base_url:
                return "PLANAGENT_OPENAI_DEBATE_CHALLENGER_BASE_URL"
            if self.openai_extraction_base_url:
                return "PLANAGENT_OPENAI_EXTRACTION_BASE_URL"
            return self.openai_base_url_source("primary")
        if target == "debate_arbitrator":
            if self.openai_debate_arbitrator_base_url:
                return "PLANAGENT_OPENAI_DEBATE_ARBITRATOR_BASE_URL"
            if self.openai_report_base_url:
                return "PLANAGENT_OPENAI_REPORT_BASE_URL"
            return self.openai_base_url_source("primary")
        raise ValueError(f"Unsupported target: {target}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
